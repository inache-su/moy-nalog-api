"""Tests for token handling, session storage, and error propagation."""

import json
import os
import stat
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from moy_nalog import (
    AuthenticationError,
    InvalidCredentialsError,
    MoyNalogClient,
    MoyNalogClientSync,
    RateLimitError,
    TokenExpiredError,
)
from moy_nalog.exceptions import MoyNalogError, SMSError, SMSRateLimitError


class FakeResponse:
    def __init__(self, status_code: int, json_data: dict | None = None, content: bytes = b""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = json.dumps(self._json) if json_data is not None else ""
        self.content = content

    def json(self) -> dict:
        return self._json


def _future() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=1)


def _attach_http(client: MoyNalogClient, **mock_kwargs) -> MagicMock:
    fake = MagicMock()
    fake.is_closed = False
    fake.aclose = AsyncMock()
    for name, value in mock_kwargs.items():
        setattr(fake, name, value)
    client._client = fake
    return fake


class TestSessionFilePermissions:
    def test_save_session_creates_owner_only_file(self, tmp_path):
        if os.name == "nt":
            pytest.skip("POSIX permission bits not meaningful on Windows")
        session_file = tmp_path / "session.json"
        client = MoyNalogClient(session_file=session_file)
        client.set_tokens("access", "refresh", "123456789012", expire_at=_future())

        client._save_session()

        mode = stat.S_IMODE(os.stat(session_file).st_mode)
        assert mode == 0o600

    def test_save_session_tightens_preexisting_world_readable_file(self, tmp_path):
        if os.name == "nt":
            pytest.skip("POSIX permission bits not meaningful on Windows")
        session_file = tmp_path / "session.json"
        session_file.write_text("{}", encoding="utf-8")
        os.chmod(session_file, 0o644)

        client = MoyNalogClient(session_file=session_file)
        client.set_tokens("access", "refresh", "123456789012", expire_at=_future())
        client._save_session()

        mode = stat.S_IMODE(os.stat(session_file).st_mode)
        assert mode == 0o600

    def test_save_session_roundtrips_through_load(self, tmp_path):
        session_file = tmp_path / "session.json"
        client = MoyNalogClient(session_file=session_file)
        client.set_tokens("access", "refresh", "123456789012", expire_at=_future())
        client._save_session()

        reloaded = MoyNalogClient(session_file=session_file)
        assert reloaded.access_token == "access"
        assert reloaded.refresh_token == "refresh"
        assert reloaded.inn == "123456789012"


class TestInnGuard:
    async def test_create_receipt_without_inn_raises(self):
        async with MoyNalogClient() as client:
            client.set_tokens(access_token="token")
            with pytest.raises(AuthenticationError):
                await client.create_receipt("Service", Decimal("100"))

    async def test_create_receipt_multi_without_inn_raises(self):
        from moy_nalog import ServiceItem

        async with MoyNalogClient() as client:
            client.set_tokens(access_token="token")
            item = ServiceItem(name="Service", amount=Decimal("100"))
            with pytest.raises(AuthenticationError):
                await client.create_receipt_multi([item])


class TestGetReceiptErrorHandling:
    async def test_reraises_rate_limit(self):
        async with MoyNalogClient() as client:
            client.set_tokens("t", "r", "123456789012")
            client._request = AsyncMock(side_effect=RateLimitError("rate limited"))
            with pytest.raises(RateLimitError):
                await client.get_receipt("11111111-1111-1111-1111-111111111111")

    async def test_reraises_token_expired(self):
        async with MoyNalogClient() as client:
            client.set_tokens("t", "r", "123456789012")
            client._request = AsyncMock(side_effect=TokenExpiredError("expired"))
            with pytest.raises(TokenExpiredError):
                await client.get_receipt("11111111-1111-1111-1111-111111111111")

    async def test_returns_none_on_generic_error(self):
        async with MoyNalogClient() as client:
            client.set_tokens("t", "r", "123456789012")
            client._request = AsyncMock(side_effect=MoyNalogError("not found", code="404"))
            assert await client.get_receipt("11111111-1111-1111-1111-111111111111") is None


class TestAuthErrorClassification:
    async def test_password_error_becomes_invalid_credentials(self):
        async with MoyNalogClient() as client:
            client._request = AsyncMock(side_effect=MoyNalogError("Wrong password", code="E1"))
            with pytest.raises(InvalidCredentialsError):
                await client.auth_by_password("123456789012", "bad")

    async def test_generic_error_becomes_authentication_error(self):
        async with MoyNalogClient() as client:
            client._request = AsyncMock(side_effect=MoyNalogError("Server is down", code="E2"))
            with pytest.raises(AuthenticationError):
                await client.auth_by_password("123456789012", "bad")

    async def test_classification_uses_code_field(self):
        async with MoyNalogClient() as client:
            client._request = AsyncMock(
                side_effect=MoyNalogError("Auth failed", code="invalid.credentials")
            )
            with pytest.raises(InvalidCredentialsError):
                await client.auth_by_password("123456789012", "bad")

    async def test_sms_limit_classified_as_rate_limit(self):
        async with MoyNalogClient() as client:
            client._request = AsyncMock(side_effect=MoyNalogError("SMS limit exceeded", code="E3"))
            with pytest.raises(SMSRateLimitError):
                await client.request_sms_code("79001234567")

    async def test_sms_generic_error_classified_as_sms_error(self):
        async with MoyNalogClient() as client:
            client._request = AsyncMock(side_effect=MoyNalogError("Service unavailable", code="E4"))
            with pytest.raises(SMSError):
                await client.request_sms_code("79001234567")

    async def test_error_message_code_prefix_not_duplicated(self):
        async with MoyNalogClient() as client:
            client._request = AsyncMock(
                side_effect=MoyNalogError("INN is invalid", code="authentication.failed")
            )
            with pytest.raises(AuthenticationError) as exc_info:
                await client.auth_by_password("123456789012", "bad")

            assert str(exc_info.value) == "[authentication.failed] INN is invalid"
            assert str(exc_info.value).count("[authentication.failed]") == 1
            assert exc_info.value.code == "authentication.failed"


class TestRefreshTokenErrorHandling:
    async def test_programming_error_propagates(self):
        async with MoyNalogClient() as client:
            client.set_tokens("t", "refresh", "123456789012")
            client._request = AsyncMock(side_effect=AttributeError("bug"))
            with pytest.raises(AttributeError):
                await client._do_refresh_token()

    async def test_api_error_returns_false(self):
        async with MoyNalogClient() as client:
            client.set_tokens("t", "refresh", "123456789012")
            client._request = AsyncMock(side_effect=MoyNalogError("server error"))
            assert await client._do_refresh_token() is False


class TestRequestRetry:
    async def test_401_refreshes_and_retries_in_loop(self):
        async with MoyNalogClient() as client:
            client.set_tokens("t", "refresh", "123456789012", expire_at=_future())
            client._do_refresh_token = AsyncMock(return_value=True)
            _attach_http(
                client,
                get=AsyncMock(side_effect=[FakeResponse(401), FakeResponse(200, {"ok": True})]),
            )

            result = await client._request("GET", "/x", with_auth=True)

            assert result == {"ok": True}
            client._do_refresh_token.assert_awaited_once()
            assert client._client.get.await_count == 2

    async def test_401_refresh_attempted_only_once(self):
        async with MoyNalogClient() as client:
            client.set_tokens("t", "refresh", "123456789012", expire_at=_future())
            client._do_refresh_token = AsyncMock(return_value=True)
            _attach_http(client, get=AsyncMock(return_value=FakeResponse(401)))

            with pytest.raises(TokenExpiredError):
                await client._request("GET", "/x", with_auth=True)

            client._do_refresh_token.assert_awaited_once()

    async def test_unexpected_error_raises_without_retry(self):
        async with MoyNalogClient() as client:
            _attach_http(client, get=AsyncMock(side_effect=ValueError("boom")))
            with pytest.raises(MoyNalogError):
                await client._request("GET", "/x")
            assert client._client.get.await_count == 1


class TestDownloadReceiptRaw:
    async def test_raises_rate_limit_on_429(self):
        async with MoyNalogClient() as client:
            client.set_tokens("t", "refresh", "123456789012", expire_at=_future())
            _attach_http(client, get=AsyncMock(return_value=FakeResponse(429)))
            with pytest.raises(RateLimitError):
                await client.download_receipt_raw("11111111-1111-1111-1111-111111111111")

    async def test_raises_token_expired_when_refresh_unavailable(self):
        async with MoyNalogClient() as client:
            client.set_tokens("t", inn="123456789012", expire_at=_future())
            _attach_http(client, get=AsyncMock(return_value=FakeResponse(401)))
            with pytest.raises(TokenExpiredError):
                await client.download_receipt_raw("11111111-1111-1111-1111-111111111111")

    async def test_refreshes_and_returns_content_on_retry(self):
        async with MoyNalogClient() as client:
            client.set_tokens("t", "refresh", "123456789012", expire_at=_future())
            client._do_refresh_token = AsyncMock(return_value=True)
            _attach_http(
                client,
                get=AsyncMock(side_effect=[FakeResponse(401), FakeResponse(200, content=b"PDF")]),
            )
            result = await client.download_receipt_raw("11111111-1111-1111-1111-111111111111")
            assert result == b"PDF"
            client._do_refresh_token.assert_awaited_once()

    async def test_returns_none_on_404(self):
        async with MoyNalogClient() as client:
            client.set_tokens("t", "refresh", "123456789012", expire_at=_future())
            _attach_http(client, get=AsyncMock(return_value=FakeResponse(404)))
            assert await client.download_receipt_raw("11111111-1111-1111-1111-111111111111") is None


class TestSyncLoopGuard:
    async def test_rejects_use_from_async_context(self):
        sync = MoyNalogClientSync()
        with pytest.raises(RuntimeError, match="async"):
            sync._get_loop()
