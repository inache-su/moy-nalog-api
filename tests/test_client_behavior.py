"""Tests for token handling, session storage, and error propagation."""

import json
import logging
import os
import stat
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from moy_nalog import (
    AuthenticationError,
    DuplicateReceiptError,
    InvalidCredentialsError,
    MoyNalogClient,
    MoyNalogClientSync,
    NetworkError,
    RateLimitError,
    ReceiptCreationUnknownError,
    ReceiptError,
    ServiceItem,
    ServiceUnavailableError,
    TokenExpiredError,
    ValidationError,
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


VALID_RECEIPT_UUID = "11111111-1111-1111-1111-111111111111"


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
                await client.get_receipt(VALID_RECEIPT_UUID)

    async def test_reraises_token_expired(self):
        async with MoyNalogClient() as client:
            client.set_tokens("t", "r", "123456789012")
            client._request = AsyncMock(side_effect=TokenExpiredError("expired"))
            with pytest.raises(TokenExpiredError):
                await client.get_receipt(VALID_RECEIPT_UUID)

    async def test_returns_none_on_404(self):
        async with MoyNalogClient() as client:
            client.set_tokens("t", "r", "123456789012", expire_at=_future())
            _attach_http(
                client,
                get=AsyncMock(return_value=FakeResponse(404, {"message": "Not found"})),
            )

            assert await client.get_receipt(VALID_RECEIPT_UUID) is None

    async def test_reraises_generic_api_error(self):
        async with MoyNalogClient() as client:
            client.set_tokens("t", "r", "123456789012")
            client._request = AsyncMock(side_effect=MoyNalogError("server error"))

            with pytest.raises(MoyNalogError, match="server error"):
                await client.get_receipt(VALID_RECEIPT_UUID)


class TestReceiptUuidValidation:
    @pytest.mark.parametrize("value", ["", "   ", "abc123", "receipt-uuid"])
    def test_rejects_invalid_uuid(self, value):
        with pytest.raises(ValidationError, match="valid UUID"):
            MoyNalogClient._validate_receipt_uuid(value)

    def test_accepts_and_trims_valid_uuid(self):
        assert (
            MoyNalogClient._validate_receipt_uuid(f"  {VALID_RECEIPT_UUID}  ")
            == VALID_RECEIPT_UUID
        )


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

    async def test_service_unavailable_preserves_tokens_and_returns_false(self, caplog):
        expire_at = _future()
        async with MoyNalogClient() as client:
            client.set_tokens("access", "refresh", "123456789012", expire_at=expire_at)
            client._request = AsyncMock(
                side_effect=ServiceUnavailableError(
                    "Выполняются технические работы с 23:00 МСК до 02:00 МСК"
                )
            )

            with caplog.at_level(logging.WARNING, logger="moy_nalog.client"):
                assert await client.refresh_access_token() is False

            assert client.access_token == "access"
            assert client.refresh_token == "refresh"
            assert client.token_expires_at == expire_at
            assert "FNS is temporarily unavailable" in caplog.text
            assert "Failed to refresh token" not in caplog.text


class TestServiceUnavailableHandling:
    async def test_503_is_typed_and_not_retried(self):
        async with MoyNalogClient(max_retries=3) as client:
            http = _attach_http(
                client,
                get=AsyncMock(return_value=FakeResponse(503, {"message": "Try later"})),
            )

            with pytest.raises(ServiceUnavailableError) as exc_info:
                await client._request("GET", "/x")

            assert exc_info.value.message == "Try later"
            assert http.get.await_count == 1

    async def test_maintenance_message_is_typed_when_status_is_not_503(self):
        message = "Выполняются технические работы с 23:00 МСК до 02:00 МСК"
        async with MoyNalogClient() as client:
            _attach_http(
                client,
                get=AsyncMock(return_value=FakeResponse(500, {"message": message})),
            )

            with pytest.raises(ServiceUnavailableError) as exc_info:
                await client._request("GET", "/x")

            assert exc_info.value.message == message

    async def test_service_unavailable_code_is_typed(self):
        async with MoyNalogClient() as client:
            _attach_http(
                client,
                get=AsyncMock(
                    return_value=FakeResponse(
                        500,
                        {"message": "Try later", "code": "service_unavailable"},
                    )
                ),
            )

            with pytest.raises(ServiceUnavailableError) as exc_info:
                await client._request("GET", "/x")

            assert exc_info.value.code == "service_unavailable"

    async def test_unrelated_server_error_remains_generic(self):
        async with MoyNalogClient() as client:
            _attach_http(
                client,
                get=AsyncMock(return_value=FakeResponse(500, {"message": "Internal error"})),
            )

            with pytest.raises(MoyNalogError) as exc_info:
                await client._request("GET", "/x")

            assert type(exc_info.value) is MoyNalogError

    @pytest.mark.parametrize(
        ("method_name", "args"),
        [
            ("auth_by_password", ("123456789012", "password")),
            ("request_sms_code", ("79001234567",)),
            ("auth_by_sms", ("79001234567", "challenge", "123456")),
            ("create_receipt", ("Service", Decimal("100"))),
            ("cancel_receipt", (VALID_RECEIPT_UUID,)),
            ("get_receipt", (VALID_RECEIPT_UUID,)),
        ],
    )
    async def test_public_operations_preserve_typed_error(self, method_name, args):
        async with MoyNalogClient() as client:
            client.set_tokens("access", "refresh", "123456789012", expire_at=_future())
            client._request = AsyncMock(
                side_effect=ServiceUnavailableError("FNS is temporarily unavailable")
            )

            with pytest.raises(ServiceUnavailableError):
                await getattr(client, method_name)(*args)

    async def test_raw_receipt_download_raises_without_retry(self):
        async with MoyNalogClient(max_retries=3) as client:
            client.set_tokens("access", "refresh", "123456789012", expire_at=_future())
            http = _attach_http(
                client,
                get=AsyncMock(return_value=FakeResponse(503, {"message": "Try later"})),
            )

            with pytest.raises(ServiceUnavailableError):
                await client.download_receipt_raw(VALID_RECEIPT_UUID)

            assert http.get.await_count == 1


class TestRequestRetry:
    async def test_404_remains_generic_without_not_found_opt_in(self):
        async with MoyNalogClient() as client:
            _attach_http(
                client,
                get=AsyncMock(return_value=FakeResponse(404, {"message": "Not found"})),
            )

            with pytest.raises(MoyNalogError) as exc_info:
                await client._request("GET", "/x")

            assert type(exc_info.value) is MoyNalogError

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
                await client.download_receipt_raw(VALID_RECEIPT_UUID)

    async def test_raises_token_expired_when_refresh_unavailable(self):
        async with MoyNalogClient() as client:
            client.set_tokens("t", inn="123456789012", expire_at=_future())
            _attach_http(client, get=AsyncMock(return_value=FakeResponse(401)))
            with pytest.raises(TokenExpiredError):
                await client.download_receipt_raw(VALID_RECEIPT_UUID)

    async def test_refreshes_and_returns_content_on_retry(self):
        async with MoyNalogClient() as client:
            client.set_tokens("t", "refresh", "123456789012", expire_at=_future())
            client._do_refresh_token = AsyncMock(return_value=True)
            _attach_http(
                client,
                get=AsyncMock(side_effect=[FakeResponse(401), FakeResponse(200, content=b"PDF")]),
            )
            result = await client.download_receipt_raw(VALID_RECEIPT_UUID)
            assert result == b"PDF"
            client._do_refresh_token.assert_awaited_once()

    async def test_returns_none_on_404(self):
        async with MoyNalogClient() as client:
            client.set_tokens("t", "refresh", "123456789012", expire_at=_future())
            _attach_http(client, get=AsyncMock(return_value=FakeResponse(404)))
            assert await client.download_receipt_raw(VALID_RECEIPT_UUID) is None


class TestSyncLoopGuard:
    async def test_rejects_use_from_async_context(self):
        sync = MoyNalogClientSync()
        with pytest.raises(RuntimeError, match="async"):
            sync._get_loop()


class TestReceiptCreationOutcome:
    @pytest.mark.parametrize("multi", [False, True])
    async def test_accepted_receipt_lost_response_then_duplicate(self, multi):
        submissions = []
        registered = []
        item = ServiceItem(name="Service", amount=Decimal("100.00"))
        duplicate = {"code": "receipt.duplication", "message": "Receipt already exists"}

        def handle(request):
            if request.method == "POST":
                assert request.url.path == "/api/v1/income"
                submissions.append(request.content)
                if len(submissions) == 1:
                    registered.append({
                        **json.loads(request.content),
                        "approvedReceiptUuid": "abcd123456",
                    })
                    raise httpx.ReadTimeout("Response lost after registration", request=request)
                return httpx.Response(400, json=duplicate)
            assert request.url.path == "/api/v1/incomes"
            return httpx.Response(200, json={"content": registered})

        async with MoyNalogClient(max_retries=3) as client:
            client.set_tokens("test", inn="test-account")
            client._client = httpx.AsyncClient(transport=httpx.MockTransport(handle))

            async def retry_delay(*args):
                item.name = "Changed while waiting"

            client._retry_delay = AsyncMock(side_effect=retry_delay)
            with pytest.raises(DuplicateReceiptError) as exc_info:
                if multi:
                    await client.create_receipt_multi([item])
                else:
                    await client.create_receipt(item.name, item.amount)

            error = exc_info.value
            assert isinstance(error, ReceiptError)
            assert error.code == "receipt.duplication"
            assert error.response == duplicate
            assert len(submissions) == 2
            assert submissions[0] == submissions[1]
            assert error.payload == json.loads(submissions[0])
            changed_copy = error.payload
            changed_copy["services"][0]["name"] = "Changed by caller"
            assert error.payload["services"][0]["name"] == "Service"
            assert "operationTime" not in str(error)
            client._retry_delay.assert_awaited_once()

            candidates = await client.find_receipt_candidates(error.payload)
            assert [r.uuid for r in candidates] == ["abcd123456"]
            assert len(registered) == 1
            assert len(submissions) == 2

    @pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.ReadError])
    async def test_exhausted_network_attempts_have_unknown_outcome(self, failure):
        async with MoyNalogClient(max_retries=2) as client:
            client.set_tokens("test", inn="test-account")
            client._retry_delay = AsyncMock()
            http = _attach_http(client, post=AsyncMock(side_effect=failure("Response lost")))
            with pytest.raises(ReceiptCreationUnknownError) as exc_info:
                await client.create_receipt("Service", 100)
            assert type(exc_info.value) is ReceiptCreationUnknownError
            assert isinstance(exc_info.value.__cause__, NetworkError)
            assert http.post.await_count == 2
            assert exc_info.value.payload == http.post.call_args.kwargs["json"]

    @pytest.mark.parametrize("body", ["", "not-json", "[]", "{}", '{"approvedReceiptUuid": 123}'])
    @pytest.mark.parametrize("status", [200, 500])
    async def test_unusable_response_is_unknown_and_not_retried(self, body, status):
        async with MoyNalogClient() as client:
            client.set_tokens("test", inn="test-account")
            http = _attach_http(client, post=AsyncMock(return_value=httpx.Response(status, text=body)))
            with pytest.raises(ReceiptCreationUnknownError):
                await client.create_receipt("Service", 100)
            assert http.post.await_count == 1

    @pytest.mark.parametrize("lost_response", [False, True])
    @pytest.mark.parametrize(
        ("status", "code", "error_type"),
        [
            (400, "receipt.invalid", ReceiptError),
            (401, "unauthorized", TokenExpiredError),
            (429, "rate.limit", RateLimitError),
            (503, "service_unavailable", ServiceUnavailableError),
            (500, "internal.error", ReceiptCreationUnknownError),
            (400, "receipt.duplication", DuplicateReceiptError),
            (503, "receipt.duplication", DuplicateReceiptError),
        ],
    )
    async def test_api_failure_does_not_erase_a_lost_response(
        self, lost_response, status, code, error_type,
    ):
        responses = [FakeResponse(status, {"code": code, "message": "Rejected"})]
        if lost_response:
            responses.insert(0, httpx.ReadTimeout("Response lost"))
        expected = (
            ReceiptCreationUnknownError
            if lost_response and error_type is not DuplicateReceiptError
            else error_type
        )
        async with MoyNalogClient() as client:
            client.set_tokens("test", inn="test-account")
            client._retry_delay = AsyncMock()
            http = _attach_http(client, post=AsyncMock(side_effect=responses))
            with pytest.raises(expected) as exc_info:
                await client.create_receipt("Service", 100)
            assert type(exc_info.value) is expected
            assert http.post.await_count == 1 + int(lost_response)

    async def test_token_refresh_reuses_the_creation_payload(self):
        item = ServiceItem(name="Service", amount=Decimal("100"))

        async def refresh():
            item.name = "Changed while refreshing"
            return True

        async with MoyNalogClient() as client:
            client.set_tokens("test", "refresh", "test-account", expire_at=_future())
            client._do_refresh_token = AsyncMock(side_effect=refresh)
            http = _attach_http(client, post=AsyncMock(side_effect=[
                FakeResponse(401), FakeResponse(200, {"approvedReceiptUuid": "abcd123456"}),
            ]))
            receipt = await client.create_receipt_multi([item])
            assert receipt.uuid == "abcd123456"
            assert receipt.services[0]["name"] == "Service"
            assert http.post.call_args_list[0].kwargs["json"] == http.post.call_args_list[1].kwargs["json"]
            client._do_refresh_token.assert_awaited_once()

    def test_sync_preserves_duplicate_and_exposes_read_only_lookup(self):
        with MoyNalogClientSync() as client:
            client.set_tokens("test", inn="test-account")
            http = _attach_http(
                client._client,
                post=AsyncMock(return_value=FakeResponse(400, {"code": "receipt.duplication"})),
                get=AsyncMock(return_value=FakeResponse(200, {"content": []})),
            )
            with pytest.raises(DuplicateReceiptError) as exc_info:
                client.create_receipt("Service", 100)
            assert client.find_receipt_candidates(exc_info.value.payload) == []
            assert http.post.await_count == 1
            assert http.get.await_count == 1


class TestReceiptCandidateLookup:
    async def test_pagination_matching_and_utc_date(self):
        payload = {
            "operationTime": "2026-09-28T01:00:00+03:00",
            "requestTime": "2026-09-28T01:00:00+03:00",
            "services": [{"name": "Service", "amount": "100.00", "quantity": 1}],
            "totalAmount": "100.00",
            "paymentType": "CASH",
            "client": {"incomeType": "FROM_INDIVIDUAL"},
        }
        match = {**payload, "approvedReceiptUuid": "abcd123456"}
        others = [
            {**match, "totalAmount": "200"},
            {**match, "services": [{"name": "Other", "amount": "100", "quantity": 1}]},
            {**match, "services": []},
            {**match, "services": [{"name": "Service", "amount": "invalid"}]},
            {**match, "paymentType": "WIRE"},
            {**match, "incomeType": "FROM_LEGAL_ENTITY"},
            {**match, "operationTime": "2026-09-28T01:00:01+03:00"},
            {**match, "cancellationInfo": {"comment": "Mistake"}},
        ]
        async with MoyNalogClient() as client:
            client.set_tokens("test", inn="test-account")
            http = _attach_http(client, get=AsyncMock(side_effect=[
                FakeResponse(200, {"content": others, "hasMore": True, "currentOffset": 0}),
                FakeResponse(200, {"content": [
                    {**match, "totalAmount": "100", "operationTime": "2026-09-27T22:00:00Z"},
                    {**match, "approvedReceiptUuid": "efgh123456"},
                ], "currentOffset": len(others)}),
            ]))
            candidates = await client.find_receipt_candidates(payload)
            assert [r.uuid for r in candidates] == ["abcd123456", "efgh123456"]
            params = [call.kwargs["params"] for call in http.get.call_args_list]
            assert [p["offset"] for p in params] == [0, len(others)]
            assert params[0]["from"] == "2026-09-27T00:00:00.000Z"
            assert params[0]["to"] == "2026-09-27T23:59:59.999Z"
            http.post.assert_not_called()

    @pytest.mark.parametrize("payload", [{}, {"operationTime": None}, {"operationTime": "2026-09-28"}])
    async def test_invalid_payload_rejected_without_request(self, payload):
        async with MoyNalogClient() as client:
            client.get_incomes = AsyncMock()
            with pytest.raises(ValidationError):
                await client.find_receipt_candidates(payload)
            client.get_incomes.assert_not_awaited()

    async def test_incomplete_lookup_does_not_report_no_match(self):
        async with MoyNalogClient() as client:
            client.set_tokens("test", inn="test-account")
            http = _attach_http(client, post=AsyncMock(return_value=FakeResponse(400, {
                "code": "receipt.duplication",
            })), get=AsyncMock(return_value=FakeResponse(200, {"content": [], "hasMore": True})))
            with pytest.raises(DuplicateReceiptError) as exc_info:
                await client.create_receipt("Service", 100)
            with pytest.raises(ReceiptCreationUnknownError, match="pagination"):
                await client.find_receipt_candidates(exc_info.value.payload)
            assert http.get.await_count == 1


class TestFNSReceiptIdentifiers:
    @pytest.mark.parametrize("identifier", ["abcd123456", "ABCD123456", VALID_RECEIPT_UUID])
    async def test_identifier_works_for_all_receipt_operations(self, identifier):
        async with MoyNalogClient() as client:
            client.set_tokens("test", inn="test-account")
            http = _attach_http(
                client,
                get=AsyncMock(return_value=FakeResponse(200, {"ok": True}, content=b"receipt")),
                post=AsyncMock(return_value=FakeResponse(200, {})),
            )
            value = f"  {identifier}  "
            assert await client.get_receipt(value) == {"ok": True}
            assert http.get.call_args.args[0].endswith(f"/test-account/{identifier}/json")
            assert await client.download_receipt_raw(value) == b"receipt"
            assert http.get.call_args.args[0].endswith(f"/test-account/{identifier}/json")
            assert client.get_receipt_print_url(value).endswith(f"/test-account/{identifier}/print")
            assert (await client.cancel_receipt(value)).uuid == identifier
            assert http.post.call_args.kwargs["json"]["receiptUuid"] == identifier

    @pytest.mark.parametrize("value", [None, 123, "abc123", "abcdefghijk", "../abcdefg", "abcd?12345", "абвг123456"])
    async def test_invalid_identifier_never_reaches_http(self, value):
        async with MoyNalogClient() as client:
            client.set_tokens("test", inn="test-account")
            client._request = AsyncMock()
            client._get_client = AsyncMock()
            for method in (client.get_receipt, client.download_receipt_raw, client.cancel_receipt):
                with pytest.raises(ValidationError):
                    await method(value)
            with pytest.raises(ValidationError):
                client.get_receipt_print_url(value)
            client._request.assert_not_awaited()
            client._get_client.assert_not_awaited()
