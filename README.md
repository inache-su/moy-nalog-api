<p align="center">
  <img
    src="https://raw.githubusercontent.com/inache-su/moy-nalog-api/main/assets/readme/hero-en.svg"
    width="100%"
    alt="moy-nalog-api — typed async and sync Python access to authentication, sessions, and receipt operations for lknpd.nalog.ru"
  >
</p>

<p align="center">
  <a href="https://pypi.org/project/moy-nalog-api/"><img src="https://img.shields.io/pypi/v/moy-nalog-api?label=PyPI&color=EF5A5A" alt="PyPI version"></a>
  <a href="https://pypi.org/project/moy-nalog-api/"><img src="https://img.shields.io/pypi/pyversions/moy-nalog-api?color=3776AB" alt="Supported Python versions"></a>
  <a href="https://github.com/inache-su/moy-nalog-api/blob/main/LICENSE"><img src="https://img.shields.io/github/license/inache-su/moy-nalog-api?color=0D1117" alt="MIT license"></a>
  <img src="https://img.shields.io/badge/typed-Pydantic%20v2-EF5A5A" alt="Typed with Pydantic v2">
</p>

<p align="center">
  <a href="https://github.com/inache-su/moy-nalog-api/blob/main/README.ru.md">Русская версия</a>
  ·
  <a href="https://pypi.org/project/moy-nalog-api/">PyPI</a>
  ·
  <a href="https://github.com/inache-su/moy-nalog-api/blob/main/CHANGELOG.md">Changelog</a>
  ·
  <a href="https://github.com/inache-su/moy-nalog-api/tree/main/examples">Examples</a>
</p>

`moy-nalog-api` is an unofficial Python client for the Russian self-employed tax service at
`lknpd.nalog.ru`. It keeps authentication, token refresh, session persistence, transport retries,
and receipt models behind one typed async API, with a matching synchronous adapter.

> **Unofficial client.** This project is not affiliated with the Federal Tax Service of Russia.
> The private API can change without notice. Always verify registered and cancelled receipts in the
> [personal cabinet](https://lknpd.nalog.ru).

## Install

```bash
python -m pip install moy-nalog-api
```

Add the optional extra only when you need SOCKS4/5:

```bash
python -m pip install "moy-nalog-api[socks]"
```

Requires Python 3.10+, `httpx` 0.25+, and Pydantic v2.

## Create your first receipt

```python
import asyncio
from decimal import Decimal

from moy_nalog import MoyNalogClient


async def main() -> None:
    async with MoyNalogClient(
        session_file=".moy-nalog-session.json",
    ) as client:
        if not client.is_authenticated:
            # Password login uses an INN, not a phone number.
            await client.auth_by_password("your_inn", "your_password")

        # This call registers a real receipt in the tax service.
        receipt = await client.create_receipt(
            name="Consulting services",
            amount=Decimal("5000.00"),
        )
        print(receipt.print_url)


asyncio.run(main())
```

> **Real-account operation.** `create_receipt()` changes a real tax account. Keep the returned receipt ID,
> verify the result in the personal cabinet, and cancel mistakes explicitly with
> `cancel_receipt()`.

## What the client handles

| Boundary | Concrete behavior |
| --- | --- |
| Client shape | `MoyNalogClient` is async-first; `MoyNalogClientSync` delegates to the same implementation |
| Authentication | Password login by INN, or a two-step phone + SMS challenge |
| Session lifecycle | Optional JSON persistence, proactive refresh, and one refresh-and-replay after a server `401` |
| Receipts | Single or multiple items, client type, payment type, creation, lookup, download, listing, and cancellation |
| Transport | Native HTTP/HTTPS proxies, optional SOCKS, configurable timeouts, and bounded network backoff |
| Failures | Public typed exceptions; validation and API failures are not flattened into transport errors |

The public API returns Pydantic models such as `UserProfile`, `Receipt`, `IncomeList`, and
`SMSChallenge`. Receipt amounts use `Decimal`.

## Authentication

### INN and password

Password authentication calls the personal-cabinet login flow and requires a 10- or 12-digit INN:

```python
profile = await client.auth_by_password(
    username="123456789012",
    password="your_password",
)

print(profile.display_name)
print(profile.inn)
```

Do not pass a phone number to `auth_by_password()`. Use the SMS flow for phone login.

### Phone and SMS

```python
phone = "79001234567"

challenge = await client.request_sms_code(phone)
code = input("SMS code: ")

profile = await client.auth_by_sms(
    phone=phone,
    challenge_token=challenge.challenge_token,
    code=code,
)
```

SMS start uses the service's v2 endpoint while verification uses v1; the client handles that API
quirk internally.

### Session persistence

Pass `session_file` to restore and save credentials automatically:

```python
async with MoyNalogClient(session_file=".moy-nalog-session.json") as client:
    if client.is_authenticated:
        profile = await client.get_user_profile()
    else:
        profile = await client.auth_by_password(username, password)
```

The file contains access and refresh tokens, the authenticated INN, the device ID, and token
timestamps. On POSIX systems it is written with owner-only permissions (`0o600`).

> **Sensitive session data.** Never commit, share, or log a session file. Add its exact path to
> `.gitignore`.

Manual session controls are available when credentials come from another trusted store:

```python
client.set_tokens(
    access_token="access_token",
    refresh_token="refresh_token",
    inn="123456789012",
)

refreshed = await client.refresh_access_token()
client.clear_session()
```

Both clients expose `is_authenticated`, `inn`, `access_token`, `refresh_token`,
`token_expires_at`, `is_token_expired`, and `device_id`.

Authentication validates the full response, including the profile, before replacing session data.
A malformed response leaves the existing tokens and profile unchanged.

## Receipt operations

### Multiple items

```python
from decimal import Decimal

from moy_nalog import ServiceItem

items = [
    ServiceItem(name="Consulting", amount=Decimal("3000"), quantity=2),
    ServiceItem(name="Development", amount=Decimal("10000")),
    ServiceItem(name="Support", amount=Decimal("500"), quantity=4),
]

receipt = await client.create_receipt_multi(items)
print(receipt.total_amount)  # 18000
```

### Client and payment type

```python
from decimal import Decimal

from moy_nalog import Client, IncomeType, PaymentType

company = Client(
    income_type=IncomeType.LEGAL_ENTITY,
    display_name="OOO Romashka",
    inn="7712345678",
)

receipt = await client.create_receipt(
    name="B2B service",
    amount=Decimal("50000"),
    client=company,
    payment_type=PaymentType.WIRE,
)
```

Available income sources are `INDIVIDUAL`, `LEGAL_ENTITY`, and `FOREIGN_AGENCY`. A wire transfer
requires legal-entity client data with an INN.

### List, inspect, and download

```python
from datetime import datetime

incomes = await client.get_incomes(
    from_date=datetime(2026, 1, 1),
    to_date=datetime(2026, 12, 31),
    offset=0,
    limit=50,
)

for item in incomes.items:
    print(item.uuid, item.total_amount, item.is_cancelled)

data = await client.get_receipt(incomes.items[0].uuid)
json_bytes = await client.download_receipt_raw(incomes.items[0].uuid, format="json")
print_bytes = await client.download_receipt_raw(incomes.items[0].uuid, format="print")
```

`get_receipt()` returns `None` only when the API reports `404`. By default, `download_receipt_raw()` returns
`None` for `404`, permanent client errors such as `403`, or exhausted network/server retries.
Permanent client errors stop after one attempt. On `401`, the client may refresh the
token and replay once; failed authorization raises `TokenExpiredError`. Other `4xx` responses,
except `404`, raise `MoyNalogError` or its subclasses when `strict_api_errors=True`.
Rate-limit responses raise `RateLimitError` in both modes. Maintenance responses raise
`ServiceUnavailableError` without retries. The `print` download is returned as raw bytes, normally
containing HTML; the API does not expose a response content type through this client.

With `strict_api_errors=True`, `get_incomes()` requires an explicit list of receipts and raises
`MoyNalogError` on malformed responses. `find_receipt_candidates()` always performs this check,
regardless of the setting; a malformed response cannot become an empty candidate list.
An explicit empty list remains valid in both modes.

### Cancel a receipt

```python
from moy_nalog import CancelReason

await client.cancel_receipt(
    receipt_uuid=receipt.uuid,
    reason=CancelReason.MISTAKE,
)
```

Use `CancelReason.REFUND` for a refund. Receipt IDs are validated before any request is sent.
The client accepts FNS receipt IDs with 10 ASCII letters/digits and retains support for standard UUIDs.
The public names `Receipt.uuid` and `receipt_uuid` are unchanged and accept either format.

The returned `Receipt` has `is_cancelled=True` and retains receipt fields supplied by the server.
If the response omits cancellation details, `cancellation_info` records the submitted reason and
operation time; it does not invent a server registration time. If the amount is absent, the return
value retains the existing `total_amount=0` fallback.

## Reliability and errors

Version 1.1.0 keeps the download/income fallbacks and creation-error wrappers from 1.0.6 by default.
Both clients accept
`strict_api_errors=True` to enable stricter handling after updating application error handlers:

| Operation | Default (`False`) | Strict mode (`True`) |
| --- | --- | --- |
| Permanent download errors such as `403` | Return `None` without retries | Raise `MoyNalogError` without retries |
| Income response missing its list | Preserve the empty `IncomeList` fallback | Raise `MoyNalogError` |
| Invalid income model fields | Preserve Pydantic validation errors | Raise `MoyNalogError` |
| Unrecovered `401` or `429` during creation, with no earlier lost response | Preserve the `ReceiptError` wrapper | Raise `TokenExpiredError`/`RateLimitError` |

Missing credentials still raise `AuthenticationError` before creation in both modes.
The new duplicate and unknown-outcome exceptions inherit from `ReceiptError`, so existing
`except ReceiptError` handlers still catch them. A failed candidate lookup always raises an error;
the default income-list fallback must not be used as proof that a receipt was never created.

Near-expiry tokens refresh proactively. If an authenticated request still receives `401`, the
client can refresh and replay that request once, even with `max_retries=1`. This replay does not
consume a network retry attempt. Concurrent operations on the same client share an in-flight token
refresh; cancelling one caller does not cancel the shared refresh. Network and timeout failures
use the configured bounded backoff. Authentication, rate-limit, maintenance, validation, and other
API failures keep their public exception types, with the creation wrappers described above.
Receipt creation has additional uncertainty
handling described below.

```python
from moy_nalog import (
    AuthenticationError,
    NetworkError,
    RateLimitError,
    ReceiptError,
    ReceiptCreationUnknownError,
    ServiceUnavailableError,
    ValidationError,
)

try:
    receipt = await client.create_receipt("Service", 1000)
except ReceiptCreationUnknownError as exc:
    candidates = await client.find_receipt_candidates(exc.payload)
    for candidate in candidates:
        print("Candidate for review:", candidate.uuid)
    raise  # Keep the operation unresolved until its receipt is verified.
except ServiceUnavailableError:
    print("The tax service is temporarily unavailable")
except RateLimitError:
    print("API rate limit exceeded")
except (AuthenticationError, ValidationError, ReceiptError, NetworkError) as exc:
    print(exc)
```

Authentication methods use typed failures such as `InvalidCredentialsError`,
`InvalidSMSCodeError`, and `SMSRateLimitError`.

All public exceptions derive from `MoyNalogError`. See
[`moy_nalog/exceptions.py`](https://github.com/inache-su/moy-nalog-api/blob/main/moy_nalog/exceptions.py) for the complete hierarchy.

### Lost creation responses and duplicates

`DuplicateReceiptError` identifies the exact FNS code `receipt.duplication`. It is a subclass of
`ReceiptCreationUnknownError`, which derives from `ReceiptError`. A duplicate response confirms
neither that this submission succeeded nor that another receipt should be created.

`ReceiptCreationUnknownError` also covers exhausted network attempts, an unusable success response,
and server errors other than separately classified maintenance responses. If an earlier attempt
lost its response, a later API rejection leaves creation uncertain; that response is retained in
`exc.response`. Neither exception triggers another creation request.

Within a creation call, retries reuse the original payload, including `operationTime`,
`requestTime`, and all line items. Both exceptions expose a copy through `exc.payload`; changing
that copy does not alter the saved payload. The SDK retains it in memory only. Store it with the
pending operation in private application storage if reconciliation must survive a restart.
A new `create_receipt()` call builds a new payload and is not an idempotent retry.

`find_receipt_candidates(exc.payload)` uses `get_incomes()` to scan every page for the operation's
UTC date on the same tax account. It compares the exact operation time, total, payment type, and
line items in order, including quantities. A conflicting income type, when returned, excludes the
receipt, as does cancellation. Both async and sync clients provide this read-only lookup.

Every result is a candidate requiring review, even when only one is found. Compare buyer details
from `get_receipt(candidate.uuid)` with the original payload and your payment records before
confirming the operation. An empty list, missing receipt fields, multiple candidates, or a lookup
failure does not prove that creation failed. Keep the operation unresolved; do not change its
timestamps or automatically create a replacement receipt.

## Configuration

```python
client = MoyNalogClient(
    timezone="Europe/Moscow",
    timeout=30.0,
    max_retries=3,
    session_file=".moy-nalog-session.json",
    auto_refresh_token=True,
    strict_api_errors=False,
    proxy="http://proxy.example.com:8080",
    verify_ssl=True,
    user_agent="MyApp/1.0",
)
```

| Option | Default | Purpose |
| --- | --- | --- |
| `timezone` | `"Europe/Moscow"` | Receipt operation timestamps |
| `timeout` | `30.0` | HTTP request timeout in seconds |
| `max_retries` | `3` | Bounded attempts for network and timeout failures |
| `session_file` | `None` | Optional persisted session path |
| `auto_refresh_token` | `True` | Refresh tokens near expiration |
| `strict_api_errors` | `False` | Opt into strict validation and specific creation/download errors |
| `proxy` | `None` | HTTP, HTTPS, SOCKS4, or SOCKS5 proxy URL |
| `verify_ssl` | `True` | TLS certificate verification |
| `user_agent` | browser-compatible default | Custom request `User-Agent` |

HTTP and HTTPS proxies use native `httpx`. SOCKS requires the `socks` extra:

```python
client = MoyNalogClient(proxy="socks5://user:password@proxy.example.com:1080")
```

Proxy credentials may be percent-encoded; existing escapes are preserved without double encoding.
IPv6 proxy addresses retain their brackets, for example `http://user:password@[::1]:8080`.

Keep `verify_ssl=True` unless a controlled intercepting proxy makes a different choice necessary.

## Synchronous client

The sync adapter mirrors the receipt, authentication, session, and profile methods:

```python
from decimal import Decimal

from moy_nalog import MoyNalogClientSync

with MoyNalogClientSync(session_file=".moy-nalog-session.json") as client:
    if not client.is_authenticated:
        client.auth_by_password("your_inn", "your_password")

    receipt = client.create_receipt(
        name="Consulting services",
        amount=Decimal("5000.00"),
    )
    print(receipt.print_url)
```

`MoyNalogClientSync` is not thread-safe and must not be called from an already-running async event
loop. Create one instance per thread, or use `MoyNalogClient` directly in async code.

## Public API at a glance

| Area | Methods |
| --- | --- |
| Authentication | `auth_by_password`, `request_sms_code`, `auth_by_sms`, `refresh_access_token` |
| Session | `set_tokens`, `clear_session` |
| Receipts | `create_receipt`, `create_receipt_multi`, `find_receipt_candidates`, `cancel_receipt`, `get_receipt` |
| Receipt output | `get_receipt_print_url`, `download_receipt_raw` |
| Account | `get_incomes`, `get_user_profile` |

Async methods are awaited on `MoyNalogClient`; the sync adapter exposes the same operations without
`await`.

## Development

```bash
python -m pip install -e ".[dev]"
pytest
pytest --cov=moy_nalog
ruff check .
mypy moy_nalog
```

The unit suite is offline. The interactive integration script is separate because it can touch a
real tax account:

```bash
python scripts/integration_test.py
```

Its default `auth_only` mode authenticates and fetches the profile. The optional `full` mode creates,
downloads, lists, and cancels real receipts. Cleanup is best-effort: inspect the personal cabinet
after every full run. Logs and artifacts are written under `test_output/` and can contain sensitive
account data.

## Compatibility and status

- Python 3.10+
- `httpx>=0.25.0`
- `pydantic>=2.0.0`
- HTTP/HTTPS proxies through `httpx`
- Optional SOCKS4/5 through `httpx-socks`

The package is a stable public library, but its upstream API is private and undocumented. Review
the [changelog](https://github.com/inache-su/moy-nalog-api/blob/main/CHANGELOG.md) before upgrading when your application depends on precise error or
retry behavior.

## Contributing

Focused issues and pull requests are welcome. Please keep async behavior authoritative, preserve
sync parity, avoid live API calls in unit tests, and run:

```bash
pytest
ruff check .
mypy moy_nalog
```

## License

[MIT](https://github.com/inache-su/moy-nalog-api/blob/main/LICENSE) © 2025–2026 [Kirill Nikulin](https://kirodev.eu)
