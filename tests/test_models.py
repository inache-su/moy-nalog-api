"""Tests for Pydantic models."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from moy_nalog import (
    Client,
    IncomeType,
    Receipt,
    ServiceItem,
    UserProfile,
)


class TestServiceItem:
    def test_creation(self):
        item = ServiceItem(name="Test", amount=Decimal("100.00"))
        assert item.name == "Test"
        assert item.amount == Decimal("100.00")
        assert item.quantity == 1

    def test_total(self):
        item = ServiceItem(name="Test", amount=Decimal("100.00"), quantity=3)
        assert item.total == Decimal("300.00")

    def test_amount_conversion(self):
        item = ServiceItem(name="Test", amount=100.50)
        assert item.amount == Decimal("100.5")

    def test_to_api_dict(self):
        item = ServiceItem(name="Test", amount=Decimal("100"), quantity=2)
        d = item.to_api_dict()
        assert d["name"] == "Test"
        assert d["amount"] == "100"
        assert d["quantity"] == 2

    def test_empty_name_fails(self):
        with pytest.raises(ValidationError):
            ServiceItem(name="", amount=Decimal("100"))

    def test_zero_amount_fails(self):
        with pytest.raises(ValidationError):
            ServiceItem(name="Test", amount=Decimal("0"))

    def test_negative_amount_fails(self):
        with pytest.raises(ValidationError):
            ServiceItem(name="Test", amount=Decimal("-100"))


class TestClient:
    def test_defaults(self):
        client = Client()
        assert client.income_type == IncomeType.INDIVIDUAL
        assert client.display_name is None

    def test_with_values(self):
        client = Client(
            income_type=IncomeType.LEGAL_ENTITY,
            display_name="OOO Test",
            inn="7712345678"
        )
        assert client.income_type == IncomeType.LEGAL_ENTITY
        assert client.inn == "7712345678"

    def test_inn_validation_10_digits(self):
        client = Client(inn="1234567890")
        assert client.inn == "1234567890"

    def test_inn_validation_12_digits(self):
        client = Client(inn="123456789012")
        assert client.inn == "123456789012"

    def test_inn_validation_wrong_length(self):
        with pytest.raises(ValidationError):
            Client(inn="12345")

    def test_inn_validation_non_digits(self):
        with pytest.raises(ValidationError):
            Client(inn="12345abc90")

    def test_phone_cleaning(self):
        client = Client(contact_phone="+7 (900) 123-45-67")
        assert client.contact_phone == "+79001234567"

    def test_to_api_dict(self):
        client = Client(
            income_type=IncomeType.LEGAL_ENTITY,
            display_name="Company",
            inn="7712345678"
        )
        d = client.to_api_dict()
        assert d["incomeType"] == "FROM_LEGAL_ENTITY"
        assert d["displayName"] == "Company"
        assert d["inn"] == "7712345678"


class TestReceipt:
    def test_from_api_response(self):
        data = {
            "approvedReceiptUuid": "abc123",
            "totalAmount": "1000.50",
            "paymentType": "CASH",
            "services": [{"name": "Test", "amount": "1000.50", "quantity": 1}],
        }
        receipt = Receipt.model_validate(data)
        assert receipt.uuid == "abc123"
        assert receipt.total_amount == Decimal("1000.50")

    def test_is_cancelled(self):
        receipt = Receipt(
            approvedReceiptUuid="abc",
            totalAmount=Decimal("100"),
            cancellationInfo=None,
        )
        assert not receipt.is_cancelled

        from moy_nalog import CancellationInfo
        receipt2 = Receipt(
            approvedReceiptUuid="abc",
            totalAmount=Decimal("100"),
            cancellationInfo=CancellationInfo(comment="Test"),
        )
        assert receipt2.is_cancelled


class TestUserProfile:
    def test_from_api_response(self):
        data = {
            "inn": "123456789012",
            "phone": "+79001234567",
            "displayName": "Test User",
            "firstName": "Test",
            "lastName": "User",
        }
        profile = UserProfile.model_validate(data)
        assert profile.inn == "123456789012"
        assert profile.display_name == "Test User"

    def test_full_name(self):
        profile = UserProfile(
            inn="123",
            firstName="Ivan",
            lastName="Petrov",
            middleName="Sergeevich",
        )
        assert profile.full_name == "Petrov Ivan Sergeevich"

    def test_full_name_fallback(self):
        profile = UserProfile(inn="123", displayName="Display Name")
        assert profile.full_name == "Display Name"
