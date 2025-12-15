"""
Async client for Moy Nalog API (lknpd.nalog.ru).

The most complete and modern Python client for Russian self-employed tax service.
"""

import asyncio
import contextlib
import json
import logging
import random
import secrets
import string
from collections.abc import Coroutine
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import TracebackType
from typing import Any, TypeVar
from zoneinfo import ZoneInfo

import httpx

from .enums import CancelReason, PaymentType
from .exceptions import (
    AuthenticationError,
    InvalidCredentialsError,
    InvalidSMSCodeError,
    MoyNalogError,
    NetworkError,
    RateLimitError,
    ReceiptError,
    SMSError,
    SMSRateLimitError,
    TokenExpiredError,
    ValidationError,
)
from .models import (
    AuthResult,
    Client,
    IncomeList,
    Receipt,
    ServiceItem,
    SessionData,
    SMSChallenge,
    UserProfile,
)

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


class MoyNalogClient:
    """
    Async client for Moy Nalog API (self-employed tax service).

    Features:
    - Password and SMS authentication
    - Automatic token refresh
    - Session persistence (optional)
    - Retry with exponential backoff
    - Full type hints and Pydantic validation
    - Multiple receipt items support
    - Income list with pagination

    Example:
        async with MoyNalogClient() as client:
            await client.auth_by_password("1234567890", "password")
            receipt = await client.create_receipt(
                name="Consulting services",
                amount=Decimal("5000.00")
            )
            print(f"Receipt: {receipt.print_url}")
    """

    API_URL_V1 = "https://lknpd.nalog.ru/api/v1"
    API_URL_V2 = "https://lknpd.nalog.ru/api/v2"

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    DEFAULT_TIMEOUT = 30.0
    TOKEN_REFRESH_MARGIN = 60  # Refresh token 60 seconds before expiry

    def __init__(
        self,
        timezone: str = "Europe/Moscow",
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = 3,
        session_file: str | Path | None = None,
        auto_refresh_token: bool = True,
        proxy: str | None = None,
        verify_ssl: bool = True,
    ) -> None:
        """
        Initialize the API client.

        Args:
            timezone: Timezone for receipts (default: Europe/Moscow)
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts for failed requests
            session_file: Path to session file for persistence (optional)
            auto_refresh_token: Automatically refresh expired tokens
            proxy: Proxy URL for requests. Supports HTTP/HTTPS and SOCKS5 proxies.
                   Examples:
                   - "http://user:pass@proxy.example.com:8080"
                   - "https://proxy.example.com:8080"
                   - "socks5://user:pass@proxy.example.com:1080"
                   For SOCKS5 support, install with: pip install moy-nalog-api[socks]
            verify_ssl: Verify SSL certificates (default: True).
                   Set to False when using proxy servers that intercept SSL traffic.
        """
        self.timezone = timezone
        self.timeout = timeout
        self.max_retries = max_retries
        self.session_file = Path(session_file) if session_file else None
        self.auto_refresh_token = auto_refresh_token
        self.proxy = proxy
        self.verify_ssl = verify_ssl

        self._device_id = self._generate_device_id()
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expire_at: datetime | None = None
        self._inn: str | None = None
        self._client: httpx.AsyncClient | None = None

        # Load session if file exists
        if self.session_file:
            self._load_session()

    # ==================== PROPERTIES ====================

    @property
    def is_authenticated(self) -> bool:
        """Check if client is authenticated."""
        return self._access_token is not None

    @property
    def inn(self) -> str | None:
        """Get current user's INN."""
        return self._inn

    @property
    def access_token(self) -> str | None:
        """Get current access token."""
        return self._access_token

    @property
    def refresh_token(self) -> str | None:
        """Get current refresh token."""
        return self._refresh_token

    @property
    def token_expires_at(self) -> datetime | None:
        """Get token expiration time."""
        return self._token_expire_at

    @property
    def is_token_expired(self) -> bool:
        """Check if access token is expired or about to expire."""
        if not self._token_expire_at:
            return False
        margin = timedelta(seconds=self.TOKEN_REFRESH_MARGIN)
        # Ensure we compare aware datetimes
        expire_at = self._token_expire_at
        if expire_at.tzinfo is None:
            expire_at = expire_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= (expire_at - margin)

    # ==================== CONTEXT MANAGER ====================

    async def __aenter__(self) -> "MoyNalogClient":
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        await self.close()

    async def close(self) -> None:
        """Close HTTP client and save session."""
        if self._client:
            await self._client.aclose()
            self._client = None
        if self.session_file and self.is_authenticated:
            self._save_session()

    # ==================== INTERNAL METHODS ====================

    @staticmethod
    def _generate_device_id() -> str:
        """Generate unique device ID (21 characters)."""
        chars = string.ascii_letters + string.digits
        return "".join(secrets.choice(chars) for _ in range(21))

    def _get_tz(self) -> ZoneInfo:
        """Get timezone object."""
        return ZoneInfo(self.timezone)

    def _get_current_time(self) -> str:
        """Get current time in ISO 8601 format with timezone."""
        return datetime.now(self._get_tz()).isoformat()

    def _get_device_info(self) -> dict[str, Any]:
        """Get device info for API requests."""
        return {
            "sourceType": "WEB",
            "sourceDeviceId": self._device_id,
            "appVersion": "1.0.0",
            "metaDetails": {"userAgent": self.USER_AGENT},
        }

    def _get_headers(self, with_auth: bool = False) -> dict[str, str]:
        """Build request headers."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "User-Agent": self.USER_AGENT,
            "Referer": "https://lknpd.nalog.ru/",
        }
        if with_auth and self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    def _is_socks_proxy(self) -> bool:
        """Check if proxy is a SOCKS proxy."""
        if not self.proxy:
            return False
        return self.proxy.lower().startswith(("socks4://", "socks5://"))

    def _encode_proxy_url(self, proxy_url: str) -> str:
        """URL-encode username and password in proxy URL if needed."""
        from urllib.parse import quote, urlparse, urlunparse

        parsed = urlparse(proxy_url)

        # If no credentials, return as-is
        if not parsed.username:
            return proxy_url

        # URL-encode username and password
        encoded_username = quote(parsed.username, safe="")
        encoded_password = quote(parsed.password or "", safe="") if parsed.password else ""

        # Rebuild netloc with encoded credentials
        if encoded_password:
            credentials = f"{encoded_username}:{encoded_password}"
        else:
            credentials = encoded_username

        # Rebuild netloc: credentials@host:port
        if parsed.port:
            netloc = f"{credentials}@{parsed.hostname}:{parsed.port}"
        else:
            netloc = f"{credentials}@{parsed.hostname}"

        # Rebuild full URL
        return urlunparse((
            parsed.scheme,
            netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        ))

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            client_kwargs: dict[str, Any] = {
                "timeout": httpx.Timeout(self.timeout),
                "follow_redirects": True,
                "verify": self.verify_ssl,
            }

            if self.proxy:
                # URL-encode credentials in proxy URL
                encoded_proxy = self._encode_proxy_url(self.proxy)

                if self._is_socks_proxy():
                    # SOCKS proxy requires httpx-socks
                    try:
                        from httpx_socks import (  # type: ignore[import-not-found]
                            AsyncProxyTransport,
                        )
                    except ImportError as e:
                        raise ImportError(
                            "SOCKS proxy support requires httpx-socks. "
                            "Install with: pip install moy-nalog-api[socks]"
                        ) from e
                    transport = AsyncProxyTransport.from_url(encoded_proxy)
                    client_kwargs["transport"] = transport
                else:
                    # HTTP/HTTPS proxy - native httpx support
                    # ssl_context is only needed for https:// proxy connections
                    is_https_proxy = encoded_proxy.lower().startswith("https://")
                    if not self.verify_ssl and is_https_proxy:
                        # Create proxy with SSL verification disabled for HTTPS proxy
                        import ssl
                        ssl_context = ssl.create_default_context()
                        ssl_context.check_hostname = False
                        ssl_context.verify_mode = ssl.CERT_NONE
                        client_kwargs["proxy"] = httpx.Proxy(
                            url=encoded_proxy,
                            ssl_context=ssl_context,
                        )
                    else:
                        client_kwargs["proxy"] = encoded_proxy

            self._client = httpx.AsyncClient(**client_kwargs)
        return self._client

    async def _request(
        self,
        method: str,
        endpoint: str,
        payload: dict[str, Any] | None = None,
        with_auth: bool = False,
        api_version: str = "v1",
    ) -> dict[str, Any]:
        """
        Make HTTP request with retry logic.

        Raises:
            NetworkError: On network failures
            MoyNalogError: On API errors
        """
        # Auto-refresh token if needed
        if with_auth and self.auto_refresh_token and self.is_token_expired and self._refresh_token:
            await self._do_refresh_token()

        base_url = self.API_URL_V1 if api_version == "v1" else self.API_URL_V2
        url = f"{base_url}{endpoint}"
        headers = self._get_headers(with_auth)
        client = await self._get_client()

        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                if method == "GET":
                    response = await client.get(url, headers=headers, params=payload)
                else:
                    response = await client.post(url, headers=headers, json=payload)

                data = response.json() if response.text else {}

                # Check for API errors
                if response.status_code == 401:
                    raise TokenExpiredError("Access token expired", response=data)
                if response.status_code == 429:
                    raise RateLimitError("Rate limit exceeded", response=data)
                if response.status_code >= 400:
                    error_msg = data.get("message") or data.get("exceptionMessage") or f"HTTP {response.status_code}"
                    error_code = data.get("code")
                    raise MoyNalogError(error_msg, code=error_code, response=data)

                return data

            except httpx.TimeoutException as e:
                last_error = NetworkError(f"Request timeout: {e}")
            except httpx.RequestError as e:
                last_error = NetworkError(f"Network error: {e}")
            except (TokenExpiredError, RateLimitError, MoyNalogError):
                raise
            except Exception as e:
                last_error = MoyNalogError(f"Unexpected error: {e}")

            # Exponential backoff
            if attempt < self.max_retries - 1:
                delay = min(2 ** attempt, 8) + random.uniform(0, 1)
                logger.warning(f"Request failed, retrying in {delay:.1f}s: {last_error}")
                await asyncio.sleep(delay)

        if last_error is not None:
            raise last_error
        raise NetworkError("Request failed after retries")

    # ==================== SESSION MANAGEMENT ====================

    def _save_session(self) -> None:
        """Save session to file."""
        if not self.session_file or not self._access_token:
            return

        try:
            session = SessionData(
                access_token=self._access_token,
                refresh_token=self._refresh_token,
                inn=self._inn,
                device_id=self._device_id,
                token_expire_at=self._token_expire_at,
            )
            self.session_file.write_text(
                session.model_dump_json(indent=2),
                encoding="utf-8",
            )
            logger.debug(f"Session saved to {self.session_file}")
        except Exception as e:
            logger.warning(f"Failed to save session: {e}")

    def _load_session(self) -> bool:
        """Load session from file."""
        if not self.session_file or not self.session_file.exists():
            return False

        try:
            data = json.loads(self.session_file.read_text(encoding="utf-8"))
            session = SessionData.model_validate(data)

            self._access_token = session.access_token
            self._refresh_token = session.refresh_token
            self._inn = session.inn
            self._device_id = session.device_id
            self._token_expire_at = session.token_expire_at

            logger.debug(f"Session loaded from {self.session_file}")
            return True
        except Exception as e:
            logger.warning(f"Failed to load session: {e}")
            return False

    def clear_session(self) -> None:
        """Clear current session and delete session file."""
        self._access_token = None
        self._refresh_token = None
        self._inn = None
        self._token_expire_at = None

        if self.session_file and self.session_file.exists():
            with contextlib.suppress(Exception):
                self.session_file.unlink()

    def set_tokens(
        self,
        access_token: str,
        refresh_token: str | None = None,
        inn: str | None = None,
        expire_at: datetime | None = None,
    ) -> None:
        """Set tokens manually (for session restoration)."""
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._inn = inn
        self._token_expire_at = expire_at

    # ==================== AUTHENTICATION ====================

    async def auth_by_password(self, username: str, password: str) -> UserProfile:
        """
        Authenticate by INN/phone and password.

        Args:
            username: INN (10-12 digits) or phone number
            password: Password from nalog.ru

        Returns:
            UserProfile with user information

        Raises:
            InvalidCredentialsError: Wrong username or password
            AuthenticationError: Other auth errors
        """
        # Validate input
        username = username.strip()
        if not username:
            raise ValidationError("Username cannot be empty")

        payload = {
            "username": username,
            "password": password,
            "deviceInfo": self._get_device_info(),
        }

        try:
            data = await self._request("POST", "/auth/lkfl", payload)
        except MoyNalogError as e:
            if "password" in str(e).lower() or "credentials" in str(e).lower():
                raise InvalidCredentialsError(str(e), response=e.response) from e
            raise AuthenticationError(str(e), response=e.response) from e

        result = AuthResult.model_validate(data)
        self._access_token = result.access_token
        self._refresh_token = result.refresh_token
        self._token_expire_at = result.token_expire_in

        profile = result.profile or UserProfile.model_validate(data.get("profile", {}))
        self._inn = profile.inn

        if self.session_file:
            self._save_session()

        logger.info(f"Authenticated by password, INN: {self._inn}")
        return profile

    async def request_sms_code(self, phone: str) -> SMSChallenge:
        """
        Step 1: Request SMS verification code.

        Args:
            phone: Phone number (e.g., 79001234567 or +79001234567)

        Returns:
            SMSChallenge with challenge_token for verification

        Raises:
            SMSRateLimitError: Too many SMS requests
            SMSError: Other SMS errors
        """
        # Clean phone number
        phone = "".join(c for c in phone if c.isdigit())
        if len(phone) == 10:
            phone = "7" + phone
        if len(phone) != 11 or not phone.startswith("7"):
            raise ValidationError("Phone must be 11 digits starting with 7 (e.g., 79001234567)")

        payload = {
            "phone": phone,
            "requireTpToBeActive": True,
        }

        try:
            data = await self._request("POST", "/auth/challenge/sms/start", payload, api_version="v2")
        except MoyNalogError as e:
            if "limit" in str(e).lower() or "часто" in str(e).lower():
                raise SMSRateLimitError(str(e), response=e.response) from e
            raise SMSError(str(e), response=e.response) from e

        return SMSChallenge.model_validate(data)

    async def auth_by_sms(self, phone: str, challenge_token: str, code: str) -> UserProfile:
        """
        Step 2: Verify SMS code and authenticate.

        Args:
            phone: Phone number (same as in request_sms_code)
            challenge_token: Token from request_sms_code()
            code: 6-digit code from SMS

        Returns:
            UserProfile with user information

        Raises:
            InvalidSMSCodeError: Wrong verification code
            SMSError: Other SMS errors
        """
        # Clean inputs
        phone = "".join(c for c in phone if c.isdigit())
        if len(phone) == 10:
            phone = "7" + phone
        code = code.strip()

        if not code.isdigit() or len(code) != 6:
            raise ValidationError("SMS code must be 6 digits")

        payload = {
            "phone": phone,
            "code": code,
            "challengeToken": challenge_token,
            "deviceInfo": self._get_device_info(),
        }

        try:
            # Note: start uses v2, but verify uses v1 (API quirk)
            data = await self._request("POST", "/auth/challenge/sms/verify", payload, api_version="v1")
        except MoyNalogError as e:
            if "code" in str(e).lower() or "код" in str(e).lower():
                raise InvalidSMSCodeError(str(e), response=e.response) from e
            raise SMSError(str(e), response=e.response) from e

        result = AuthResult.model_validate(data)
        self._access_token = result.access_token
        self._refresh_token = result.refresh_token
        self._token_expire_at = result.token_expire_in

        profile = result.profile or UserProfile.model_validate(data.get("profile", {}))
        self._inn = profile.inn

        if self.session_file:
            self._save_session()

        logger.info(f"Authenticated by SMS, INN: {self._inn}")
        return profile

    async def _do_refresh_token(self) -> bool:
        """Refresh access token using refresh token."""
        if not self._refresh_token:
            return False

        payload = {
            "deviceInfo": self._get_device_info(),
            "refreshToken": self._refresh_token,
        }

        try:
            data = await self._request("POST", "/auth/token", payload)
            self._access_token = data.get("token")
            if new_refresh := data.get("refreshToken"):
                self._refresh_token = new_refresh
            if expire_in := data.get("tokenExpireIn"):
                with contextlib.suppress(ValueError, AttributeError):
                    self._token_expire_at = datetime.fromisoformat(expire_in.replace("Z", "+00:00"))

            if self.session_file:
                self._save_session()

            logger.debug("Access token refreshed")
            return True
        except Exception as e:
            logger.warning(f"Failed to refresh token: {e}")
            return False

    async def refresh_access_token(self) -> bool:
        """
        Manually refresh access token.

        Returns:
            True if refresh successful
        """
        return await self._do_refresh_token()

    # ==================== RECEIPTS ====================

    async def create_receipt(
        self,
        name: str,
        amount: Decimal | float | int,
        quantity: int = 1,
        client: Client | None = None,
        payment_type: PaymentType = PaymentType.CASH,
        operation_time: datetime | None = None,
    ) -> Receipt:
        """
        Create receipt with single item.

        Args:
            name: Service/product name
            amount: Amount in rubles
            quantity: Quantity (default 1)
            client: Client information
            payment_type: Payment type (CASH or WIRE)
            operation_time: Operation time (default: current)

        Returns:
            Receipt with print_url and json_url

        Raises:
            ReceiptError: Receipt creation failed
            AuthenticationError: Not authenticated
        """
        item = ServiceItem(name=name, amount=Decimal(str(amount)), quantity=quantity)
        return await self.create_receipt_multi([item], client, payment_type, operation_time)

    async def create_receipt_multi(
        self,
        items: list[ServiceItem],
        client: Client | None = None,
        payment_type: PaymentType = PaymentType.CASH,
        operation_time: datetime | None = None,
    ) -> Receipt:
        """
        Create receipt with multiple items.

        Args:
            items: List of ServiceItem
            client: Client information
            payment_type: Payment type
            operation_time: Operation time

        Returns:
            Receipt with print_url and json_url

        Raises:
            ReceiptError: Receipt creation failed
        """
        if not self.is_authenticated:
            raise AuthenticationError("Not authenticated")

        if not items:
            raise ValidationError("Items list cannot be empty")

        # Calculate total
        total_amount = sum(item.total for item in items)

        # Format times
        tz = self._get_tz()
        now = datetime.now(tz)
        op_time_dt = (operation_time or now).astimezone(tz)
        req_time_dt = now

        # Build client data
        client_data = (client or Client()).to_api_dict()

        payload = {
            "operationTime": op_time_dt.isoformat(),
            "requestTime": req_time_dt.isoformat(),
            "services": [item.to_api_dict() for item in items],
            "totalAmount": str(total_amount),
            "client": client_data,
            "paymentType": payment_type.value,
            "ignoreMaxTotalIncomeRestriction": False,
        }

        try:
            data = await self._request("POST", "/income", payload, with_auth=True)
        except MoyNalogError as e:
            raise ReceiptError(str(e), code=e.code, response=e.response) from e

        receipt_uuid = data.get("approvedReceiptUuid")
        if not receipt_uuid:
            raise ReceiptError("No receipt UUID in response", response=data)

        # Build receipt object
        receipt = Receipt(
            uuid=receipt_uuid,
            total_amount=total_amount,
            operation_time=op_time_dt,
            request_time=req_time_dt,
            payment_type=payment_type.value,
            services=[item.to_api_dict() for item in items],
        )
        receipt.print_url = f"{self.API_URL_V1}/receipt/{self._inn}/{receipt_uuid}/print"
        receipt.json_url = f"{self.API_URL_V1}/receipt/{self._inn}/{receipt_uuid}/json"

        logger.info(f"Receipt created: {receipt_uuid}, amount: {total_amount}")
        return receipt

    async def cancel_receipt(
        self,
        receipt_uuid: str,
        reason: CancelReason = CancelReason.REFUND,
        operation_time: datetime | None = None,
    ) -> Receipt:
        """
        Cancel (void) a receipt.

        Args:
            receipt_uuid: UUID of receipt to cancel
            reason: Cancellation reason (REFUND or MISTAKE)
            operation_time: Cancellation time

        Returns:
            Cancelled receipt

        Raises:
            ReceiptError: Cancellation failed
        """
        if not self.is_authenticated:
            raise AuthenticationError("Not authenticated")

        tz = self._get_tz()
        op_time = (operation_time or datetime.now(tz)).astimezone(tz).isoformat()
        req_time = datetime.now(tz).isoformat()

        payload = {
            "operationTime": op_time,
            "requestTime": req_time,
            "comment": reason.value,
            "receiptUuid": receipt_uuid,
            "partnerCode": None,
        }

        try:
            data = await self._request("POST", "/cancel", payload, with_auth=True)
        except MoyNalogError as e:
            raise ReceiptError(str(e), code=e.code, response=e.response) from e

        cancelled_uuid = data.get("approvedReceiptUuid") or receipt_uuid

        receipt = Receipt(
            uuid=cancelled_uuid,
            total_amount=Decimal("0"),
        )

        logger.info(f"Receipt cancelled: {cancelled_uuid}")
        return receipt

    async def get_receipt(self, receipt_uuid: str) -> dict[str, Any] | None:
        """
        Get receipt data as JSON.

        Args:
            receipt_uuid: Receipt UUID

        Returns:
            Receipt data dict or None
        """
        if not self.is_authenticated or not self._inn:
            raise AuthenticationError("Not authenticated")

        try:
            return await self._request("GET", f"/receipt/{self._inn}/{receipt_uuid}/json", with_auth=True)
        except MoyNalogError:
            return None

    def get_receipt_print_url(self, receipt_uuid: str) -> str:
        """Get URL for printable receipt form."""
        if not self._inn:
            raise AuthenticationError("Not authenticated (INN unknown)")
        return f"{self.API_URL_V1}/receipt/{self._inn}/{receipt_uuid}/print"

    # ==================== INCOMES ====================

    async def get_incomes(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        offset: int = 0,
        limit: int = 50,
        sort_by: str = "operation_time:desc",
    ) -> IncomeList:
        """
        Get list of incomes (receipts) with pagination.

        Args:
            from_date: Start date filter
            to_date: End date filter
            offset: Pagination offset
            limit: Page size (max 50)
            sort_by: Sort order

        Returns:
            IncomeList with items and pagination info
        """
        if not self.is_authenticated:
            raise AuthenticationError("Not authenticated")

        params = {
            "offset": offset,
            "limit": min(limit, 50),
            "sortBy": sort_by,
        }

        if from_date:
            params["from"] = from_date.strftime("%Y-%m-%dT00:00:00.000Z")
        if to_date:
            params["to"] = to_date.strftime("%Y-%m-%dT23:59:59.999Z")

        data = await self._request("GET", "/incomes", params, with_auth=True)
        return IncomeList.model_validate(data)

    # ==================== USER ====================

    async def get_user_profile(self) -> UserProfile:
        """
        Get current user's profile information.

        Returns:
            UserProfile with user data
        """
        if not self.is_authenticated:
            raise AuthenticationError("Not authenticated")

        data = await self._request("GET", "/user", with_auth=True)
        profile = UserProfile.model_validate(data)
        self._inn = profile.inn
        return profile


# ==================== SYNC WRAPPER ====================

class MoyNalogClientSync:
    """
    Synchronous wrapper for MoyNalogClient.

    For use in non-async code. Creates an event loop internally.
    Do not use from within async code - use MoyNalogClient directly instead.

    Accepts all the same arguments as MoyNalogClient, including proxy support.

    Example:
        client = MoyNalogClientSync()
        client.auth_by_password("1234567890", "password")
        receipt = client.create_receipt("Service", Decimal("1000"))
        client.close()

    Example with proxy:
        client = MoyNalogClientSync(proxy="http://proxy.example.com:8080")
        client.auth_by_password("1234567890", "password")
    """

    def __init__(self, **kwargs: Any) -> None:
        self._client = MoyNalogClient(**kwargs)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._owns_loop = False

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            # Check if we're in an async context
            try:
                asyncio.get_running_loop()
                raise RuntimeError(
                    "MoyNalogClientSync cannot be used from async code. "
                    "Use MoyNalogClient instead."
                )
            except RuntimeError as e:
                if "no running event loop" not in str(e):
                    raise
            # Create our own loop
            self._loop = asyncio.new_event_loop()
            self._owns_loop = True
        return self._loop

    def _run(self, coro: Coroutine[Any, Any, _T]) -> _T:
        return self._get_loop().run_until_complete(coro)

    def close(self) -> None:
        self._run(self._client.close())
        if self._owns_loop and self._loop and not self._loop.is_running():
            self._loop.close()
            self._loop = None

    def __enter__(self) -> "MoyNalogClientSync":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    # Proxy properties
    @property
    def is_authenticated(self) -> bool:
        return self._client.is_authenticated

    @property
    def inn(self) -> str | None:
        return self._client.inn

    @property
    def access_token(self) -> str | None:
        return self._client.access_token

    @property
    def refresh_token(self) -> str | None:
        return self._client.refresh_token

    @property
    def token_expires_at(self) -> datetime | None:
        return self._client.token_expires_at

    @property
    def is_token_expired(self) -> bool:
        return self._client.is_token_expired

    # Proxy methods
    def set_tokens(
        self,
        access_token: str,
        refresh_token: str | None = None,
        inn: str | None = None,
        expire_at: datetime | None = None,
    ) -> None:
        self._client.set_tokens(access_token, refresh_token, inn, expire_at)

    def auth_by_password(self, username: str, password: str) -> UserProfile:
        return self._run(self._client.auth_by_password(username, password))

    def request_sms_code(self, phone: str) -> SMSChallenge:
        return self._run(self._client.request_sms_code(phone))

    def auth_by_sms(self, phone: str, challenge_token: str, code: str) -> UserProfile:
        return self._run(self._client.auth_by_sms(phone, challenge_token, code))

    def create_receipt(self, name: str, amount: Decimal | float | int, **kwargs: Any) -> Receipt:
        return self._run(self._client.create_receipt(name, amount, **kwargs))

    def create_receipt_multi(self, items: list[ServiceItem], **kwargs: Any) -> Receipt:
        return self._run(self._client.create_receipt_multi(items, **kwargs))

    def cancel_receipt(self, receipt_uuid: str, **kwargs: Any) -> Receipt:
        return self._run(self._client.cancel_receipt(receipt_uuid, **kwargs))

    def get_receipt(self, receipt_uuid: str) -> dict[str, Any] | None:
        return self._run(self._client.get_receipt(receipt_uuid))

    def get_receipt_print_url(self, receipt_uuid: str) -> str:
        return self._client.get_receipt_print_url(receipt_uuid)

    def get_incomes(self, **kwargs: Any) -> IncomeList:
        return self._run(self._client.get_incomes(**kwargs))

    def get_user_profile(self) -> UserProfile:
        return self._run(self._client.get_user_profile())

    def refresh_access_token(self) -> bool:
        return self._run(self._client.refresh_access_token())

    def clear_session(self) -> None:
        self._client.clear_session()
