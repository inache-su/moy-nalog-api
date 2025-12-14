"""Tests for MoyNalogClient."""

from decimal import Decimal

import pytest

from moy_nalog import (
    AuthenticationError,
    MoyNalogClient,
    MoyNalogClientSync,
    ValidationError,
)


class TestMoyNalogClient:
    def test_initialization(self):
        client = MoyNalogClient()
        assert client.timezone == "Europe/Moscow"
        assert client.timeout == 30.0
        assert client.max_retries == 3
        assert not client.is_authenticated

    def test_custom_config(self):
        client = MoyNalogClient(
            timezone="Asia/Yekaterinburg",
            timeout=60.0,
            max_retries=5,
        )
        assert client.timezone == "Asia/Yekaterinburg"
        assert client.timeout == 60.0
        assert client.max_retries == 5

    def test_device_id_generation(self):
        client = MoyNalogClient()
        assert len(client._device_id) == 21
        assert client._device_id.isalnum()

    def test_not_authenticated_by_default(self):
        client = MoyNalogClient()
        assert not client.is_authenticated
        assert client.inn is None
        assert client.access_token is None

    @pytest.mark.asyncio
    async def test_create_receipt_not_authenticated(self):
        async with MoyNalogClient() as client:
            with pytest.raises(AuthenticationError):
                await client.create_receipt("Test", Decimal("100"))

    @pytest.mark.asyncio
    async def test_cancel_receipt_not_authenticated(self):
        async with MoyNalogClient() as client:
            with pytest.raises(AuthenticationError):
                await client.cancel_receipt("test-uuid")

    @pytest.mark.asyncio
    async def test_get_incomes_not_authenticated(self):
        async with MoyNalogClient() as client:
            with pytest.raises(AuthenticationError):
                await client.get_incomes()

    def test_set_tokens(self):
        client = MoyNalogClient()
        client.set_tokens(
            access_token="test_token",
            refresh_token="test_refresh",
            inn="123456789012",
        )
        assert client.is_authenticated
        assert client.access_token == "test_token"
        assert client.refresh_token == "test_refresh"
        assert client.inn == "123456789012"

    def test_clear_session(self):
        client = MoyNalogClient()
        client.set_tokens("token", "refresh", "123")
        assert client.is_authenticated

        client.clear_session()
        assert not client.is_authenticated
        assert client.inn is None


class TestMoyNalogClientSync:
    def test_initialization(self):
        client = MoyNalogClientSync()
        assert not client.is_authenticated

    def test_context_manager(self):
        with MoyNalogClientSync() as client:
            assert not client.is_authenticated


class TestValidation:
    @pytest.mark.asyncio
    async def test_request_sms_invalid_phone(self):
        async with MoyNalogClient() as client:
            with pytest.raises(ValidationError):
                await client.request_sms_code("123")  # Too short

    @pytest.mark.asyncio
    async def test_auth_by_sms_invalid_code(self):
        async with MoyNalogClient() as client:
            with pytest.raises(ValidationError):
                await client.auth_by_sms("79001234567", "token", "abc")  # Not digits

    @pytest.mark.asyncio
    async def test_auth_by_password_empty_username(self):
        async with MoyNalogClient() as client:
            with pytest.raises(ValidationError):
                await client.auth_by_password("", "password")
