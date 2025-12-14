"""Pydantic models for Moy Nalog API."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import IncomeType

# ==================== INPUT MODELS ====================

class ServiceItem(BaseModel):
    """Receipt line item (service/product)."""
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=1000, description="Service/product name")
    amount: Decimal = Field(..., gt=0, description="Price per unit in rubles")
    quantity: int = Field(default=1, ge=1, description="Quantity")

    @field_validator("amount", mode="before")
    @classmethod
    def convert_amount(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float, str)):
            return Decimal(str(v))
        raise TypeError("amount must be Decimal, int, float, or str")

    @property
    def total(self) -> Decimal:
        """Total amount for this item."""
        return self.amount * self.quantity

    def to_api_dict(self) -> dict:
        """Convert to API format."""
        return {
            "name": self.name,
            "amount": str(self.amount),
            "quantity": self.quantity,
        }


class Client(BaseModel):
    """Client information for receipt."""
    model_config = ConfigDict(populate_by_name=True)

    income_type: IncomeType = Field(default=IncomeType.INDIVIDUAL, alias="incomeType")
    display_name: str | None = Field(default=None, max_length=1000, alias="displayName")
    contact_phone: str | None = Field(default=None, alias="contactPhone")
    inn: str | None = Field(default=None, description="Tax ID")

    @field_validator("inn")
    @classmethod
    def validate_inn(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v.isdigit():
                raise ValueError("INN must contain only digits")
            if len(v) not in (10, 12):
                raise ValueError("INN must be 10 or 12 digits")
        return v

    @field_validator("contact_phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is not None:
            v = "".join(c for c in v if c.isdigit() or c == "+")
        return v

    def to_api_dict(self) -> dict:
        """Convert to API format."""
        return {
            "incomeType": self.income_type.value,
            "displayName": self.display_name,
            "contactPhone": self.contact_phone,
            "inn": self.inn,
        }


# ==================== RESPONSE MODELS ====================

class UserProfile(BaseModel):
    """User profile information."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: int | None = None
    inn: str
    phone: str | None = None
    email: str | None = None
    display_name: str | None = Field(default=None, alias="displayName")
    first_name: str | None = Field(default=None, alias="firstName")
    last_name: str | None = Field(default=None, alias="lastName")
    middle_name: str | None = Field(default=None, alias="middleName")
    snils: str | None = None
    status: str | None = None
    registration_date: datetime | None = Field(default=None, alias="registrationDate")
    initial_registration_date: datetime | None = Field(default=None, alias="initialRegistrationDate")

    @property
    def full_name(self) -> str:
        """Full name from parts."""
        parts = [self.last_name, self.first_name, self.middle_name]
        return " ".join(p for p in parts if p) or self.display_name or ""


class CancellationInfo(BaseModel):
    """Receipt cancellation information."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    operation_time: datetime | None = Field(default=None, alias="operationTime")
    register_time: datetime | None = Field(default=None, alias="registerTime")
    tax_period_id: int | None = Field(default=None, alias="taxPeriodId")
    comment: str | None = None


class Receipt(BaseModel):
    """Receipt (income) information."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    uuid: str = Field(..., alias="approvedReceiptUuid")
    name: str | None = None
    total_amount: Decimal = Field(..., alias="totalAmount")
    operation_time: datetime | None = Field(default=None, alias="operationTime")
    request_time: datetime | None = Field(default=None, alias="requestTime")
    register_time: datetime | None = Field(default=None, alias="registerTime")
    payment_type: str | None = Field(default=None, alias="paymentType")
    income_type: str | None = Field(default=None, alias="incomeType")
    tax_period_id: int | None = Field(default=None, alias="taxPeriodId")
    services: list[dict[str, Any]] = Field(default_factory=list)
    cancellation_info: CancellationInfo | None = Field(default=None, alias="cancellationInfo")

    # URLs (set after creation)
    print_url: str | None = None
    json_url: str | None = None

    @property
    def is_cancelled(self) -> bool:
        """Check if receipt is cancelled."""
        return self.cancellation_info is not None


class IncomeList(BaseModel):
    """Paginated list of incomes/receipts."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    items: list[Receipt] = Field(default_factory=list, alias="content")
    has_more: bool = Field(default=False, alias="hasMore")
    offset: int = Field(default=0, alias="currentOffset")
    limit: int = Field(default=50, alias="currentLimit")
    total: int | None = Field(default=None, alias="totalCount")


class SMSChallenge(BaseModel):
    """SMS verification challenge."""
    challenge_token: str = Field(..., alias="challengeToken")
    expire_date: datetime | None = Field(default=None, alias="expireDate")
    expire_in: int | None = Field(default=None, alias="expireIn", description="Seconds until expiration")


class AuthResult(BaseModel):
    """Authentication result."""
    access_token: str = Field(..., alias="token")
    refresh_token: str | None = Field(default=None, alias="refreshToken")
    token_expire_in: datetime | None = Field(default=None, alias="tokenExpireIn")
    profile: UserProfile | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SessionData(BaseModel):
    """Saved session data."""
    access_token: str
    refresh_token: str | None = None
    inn: str | None = None
    device_id: str
    token_expire_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utc_now)
