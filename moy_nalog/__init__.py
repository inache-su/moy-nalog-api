"""
Moy Nalog API Client - The most complete Python client for Russian self-employed tax service.

Features:
- Async (httpx) and sync support
- Password and SMS authentication
- Automatic token refresh
- Session persistence
- Retry with exponential backoff
- Full Pydantic validation
- Multiple receipt items
- Income list with pagination

Example (async):
    async with MoyNalogClient() as client:
        await client.auth_by_password("1234567890", "password")
        receipt = await client.create_receipt("Service", Decimal("1000"))
        print(receipt.print_url)

Example (sync):
    with MoyNalogClientSync() as client:
        client.auth_by_password("1234567890", "password")
        receipt = client.create_receipt("Service", Decimal("1000"))
        print(receipt.print_url)
"""

from .client import MoyNalogClient, MoyNalogClientSync
from .enums import CancelReason, IncomeType, PaymentType
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
    CancellationInfo,
    Client,
    IncomeList,
    Receipt,
    ServiceItem,
    SessionData,
    SMSChallenge,
    UserProfile,
)

__version__ = "1.0.2"
__author__ = "Kirill Nikulin"
__email__ = "me@kirodev.eu"

__all__ = [
    # Clients
    "MoyNalogClient",
    "MoyNalogClientSync",
    # Enums
    "CancelReason",
    "IncomeType",
    "PaymentType",
    # Models
    "AuthResult",
    "CancellationInfo",
    "Client",
    "IncomeList",
    "Receipt",
    "ServiceItem",
    "SessionData",
    "SMSChallenge",
    "UserProfile",
    # Exceptions
    "MoyNalogError",
    "AuthenticationError",
    "InvalidCredentialsError",
    "TokenExpiredError",
    "SMSError",
    "SMSRateLimitError",
    "InvalidSMSCodeError",
    "ReceiptError",
    "ValidationError",
    "NetworkError",
    "RateLimitError",
]
