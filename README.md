# moy-nalog-api

[![GitHub](https://img.shields.io/badge/GitHub-inache--su%2Fmoy--nalog--api-181717?logo=github)](https://github.com/inache-su/moy-nalog-api)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PyPI version](https://badge.fury.io/py/moy-nalog-api.svg)](https://pypi.org/project/moy-nalog-api/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

**The most complete and modern Python client for Russian self-employed tax service (lknpd.nalog.ru).**

Unofficial Python client for "Moy Nalog" API (self-employed, NPD tax regime).

[Документация на русском](README.ru.md)

## Why moy-nalog-api?

There are several Python libraries for the Moy Nalog API. Here's why you should choose this one:

| Feature | moy-nalog-api | Others |
|---------|---------------|--------|
| **Async/await support** | Native httpx async | Often sync-only or requests-based |
| **Sync wrapper included** | Yes, for non-async code | Usually one or the other |
| **SMS authentication** | Full support (request + verify) | Often missing or broken |
| **Session persistence** | Built-in JSON file storage | Manual implementation required |
| **Auto token refresh** | Automatic before expiration | Manual refresh needed |
| **Type hints** | 100% typed, mypy-compatible | Partial or none |
| **Pydantic v2** | Full validation and serialization | Often dict-based or Pydantic v1 |
| **Modern Python** | 3.10+ with latest syntax | Often 3.7+ with legacy code |
| **Error handling** | Typed exception hierarchy | Generic exceptions |
| **Retry logic** | Exponential backoff built-in | Usually none |
| **Multiple items** | Native support for multi-item receipts | Single item only |
| **Documentation** | Comprehensive with examples | Often minimal |

## Features

- Async (httpx) and sync client support
- Password and SMS authentication
- Automatic token refresh with session persistence
- Retry with exponential backoff
- Full Pydantic v2 validation
- Multiple receipt items in single receipt
- All client types (individual, legal entity, foreign)
- Income list with pagination and filtering
- Receipt cancellation with reason
- Complete type hints for IDE support

## Installation

```bash
pip install moy-nalog-api
```

For development:
```bash
pip install moy-nalog-api[dev]
```

## Quick Start

### Async (Recommended)

```python
import asyncio
from decimal import Decimal
from moy_nalog import MoyNalogClient

async def main():
    # Create client with session persistence
    async with MoyNalogClient(session_file="session.json") as client:

        # First run: authenticate
        if not client.is_authenticated:
            await client.auth_by_password("your_inn", "your_password")

        # Create receipt
        receipt = await client.create_receipt(
            name="Consulting services",
            amount=Decimal("5000.00")
        )

        print(f"Receipt created: {receipt.print_url}")

asyncio.run(main())
```

### Sync

```python
from decimal import Decimal
from moy_nalog import MoyNalogClientSync

with MoyNalogClientSync(session_file="session.json") as client:
    if not client.is_authenticated:
        client.auth_by_password("your_inn", "your_password")

    receipt = client.create_receipt(
        name="Consulting services",
        amount=Decimal("5000.00")
    )

    print(f"Receipt created: {receipt.print_url}")
```

## Authentication

### Password Authentication

Use your INN (tax identification number) or phone and password from nalog.ru:

```python
profile = await client.auth_by_password(
    username="123456789012",  # INN (12 digits) or phone
    password="your_password"
)
print(f"Authenticated as: {profile.display_name}")
print(f"INN: {profile.inn}")
print(f"Status: {profile.status}")
```

### SMS Authentication

Two-step process for phone-based authentication:

```python
# Step 1: Request SMS code
phone = "79001234567"  # Format: 7XXXXXXXXXX (11 digits)
challenge = await client.request_sms_code(phone)
print(f"SMS sent! Code expires in {challenge.expire_in} seconds")

# Step 2: Enter code and authenticate
code = input("Enter 6-digit code from SMS: ")
profile = await client.auth_by_sms(phone, challenge.challenge_token, code)
print(f"Authenticated as: {profile.display_name}")
```

### Session Persistence

Save and restore authentication tokens automatically:

```python
# Session file stores tokens between runs
client = MoyNalogClient(session_file="session.json")

# Check if already authenticated from previous session
if client.is_authenticated:
    print("Session restored from file")
else:
    # Authenticate (tokens saved automatically)
    await client.auth_by_password(username, password)

# Tokens auto-refresh when expired
# Session auto-saves on close
```

Session file contains:
- Access token (for API requests)
- Refresh token (for token renewal)
- Token expiration time
- User INN and device ID

## Creating Receipts

### Simple Receipt

```python
from decimal import Decimal

receipt = await client.create_receipt(
    name="Web development",
    amount=Decimal("15000.00")
)

print(f"UUID: {receipt.uuid}")
print(f"Amount: {receipt.total_amount} RUB")
print(f"Print URL: {receipt.print_url}")
print(f"JSON URL: {receipt.json_url}")
```

### Multiple Items

```python
from decimal import Decimal
from moy_nalog import ServiceItem

items = [
    ServiceItem(name="Consulting", amount=Decimal("3000"), quantity=2),
    ServiceItem(name="Development", amount=Decimal("10000"), quantity=1),
    ServiceItem(name="Support", amount=Decimal("500"), quantity=4),
]

receipt = await client.create_receipt_multi(items)
# Total: 3000*2 + 10000*1 + 500*4 = 18000 RUB
print(f"Total: {receipt.total_amount} RUB")
```

### With Client Information

#### Individual Client (default)

```python
from moy_nalog import Client, IncomeType

client_info = Client(
    income_type=IncomeType.INDIVIDUAL,
    display_name="Ivan Petrov",
    contact_phone="+79001234567"
)

receipt = await client.create_receipt(
    name="Service",
    amount=Decimal("1000"),
    client=client_info
)
```

#### Legal Entity (Company)

```python
company = Client(
    income_type=IncomeType.LEGAL_ENTITY,
    display_name="OOO Romashka",
    inn="7712345678"  # 10 digits for companies
)

receipt = await client.create_receipt(
    name="B2B Service",
    amount=Decimal("50000"),
    client=company
)
```

#### Foreign Organization

```python
foreign = Client(
    income_type=IncomeType.FOREIGN_AGENCY,
    display_name="Acme Corporation",
    inn="9909123456"
)

receipt = await client.create_receipt(
    name="International consulting",
    amount=Decimal("100000"),
    client=foreign
)
```

### Payment Types

```python
from moy_nalog import PaymentType

# Cash or card payment (default)
receipt = await client.create_receipt(
    name="Service",
    amount=Decimal("1000"),
    payment_type=PaymentType.CASH
)

# Bank transfer (requires legal entity client with INN)
receipt = await client.create_receipt(
    name="Service",
    amount=Decimal("50000"),
    client=company,  # Must have INN
    payment_type=PaymentType.WIRE
)
```

## Canceling Receipts

Cancel a receipt within the same tax period:

```python
from moy_nalog import CancelReason

# Client requested refund
await client.cancel_receipt(
    receipt_uuid="abc123",
    reason=CancelReason.REFUND
)

# Receipt created by mistake
await client.cancel_receipt(
    receipt_uuid="abc123",
    reason=CancelReason.MISTAKE
)
```

## Viewing Receipts

### Get Income List

```python
from datetime import datetime

# Get recent receipts (default: last 50)
incomes = await client.get_incomes()

for receipt in incomes.items:
    status = "CANCELLED" if receipt.is_cancelled else "ACTIVE"
    print(f"{receipt.uuid}: {receipt.total_amount} RUB [{status}]")

print(f"Total count: {incomes.total}")
print(f"Has more: {incomes.has_more}")
```

### With Filters and Pagination

```python
incomes = await client.get_incomes(
    from_date=datetime(2024, 1, 1),
    to_date=datetime(2024, 12, 31),
    offset=0,
    limit=50
)

# Load more if needed
if incomes.has_more:
    more = await client.get_incomes(offset=50, limit=50)
```

### Get Receipt Details

```python
# Get full receipt data as dict
data = await client.get_receipt("receipt_uuid")
if data:
    print(f"Services: {data['services']}")
    print(f"Payment type: {data['paymentType']}")

# Get printable URL
url = client.get_receipt_print_url("receipt_uuid")
```

## Error Handling

```python
from moy_nalog import (
    MoyNalogError,
    AuthenticationError,
    InvalidCredentialsError,
    TokenExpiredError,
    SMSError,
    SMSRateLimitError,
    InvalidSMSCodeError,
    ReceiptError,
    ValidationError,
    NetworkError,
    RateLimitError,
)

try:
    await client.auth_by_password(username, password)
except InvalidCredentialsError:
    print("Wrong username or password")
except TokenExpiredError:
    print("Session expired, re-authenticate")
except AuthenticationError as e:
    print(f"Auth failed: {e.message}")

try:
    await client.request_sms_code(phone)
except SMSRateLimitError:
    print("Too many SMS requests, wait a minute")
except SMSError as e:
    print(f"SMS error: {e.message}")

try:
    await client.create_receipt("Service", Decimal("1000"))
except ReceiptError as e:
    print(f"Receipt error: {e.message}")
    print(f"Error code: {e.code}")
    print(f"API response: {e.response}")

try:
    # Network issues are retried automatically
    await client.get_incomes()
except NetworkError:
    print("Network unavailable after retries")
except RateLimitError:
    print("API rate limit exceeded")
```

## Configuration

```python
client = MoyNalogClient(
    # Timezone for receipt timestamps (default: Europe/Moscow)
    timezone="Europe/Moscow",

    # Request timeout in seconds (default: 30)
    timeout=30.0,

    # Retry attempts for failed requests (default: 3)
    max_retries=3,

    # Path to session file for persistence (optional)
    session_file="session.json",

    # Auto-refresh tokens before expiration (default: True)
    auto_refresh_token=True,
)
```

## User Profile

```python
profile = await client.get_user_profile()

print(f"ID: {profile.id}")
print(f"INN: {profile.inn}")
print(f"Phone: {profile.phone}")
print(f"Email: {profile.email}")
print(f"Name: {profile.display_name}")
print(f"Full name: {profile.full_name}")
print(f"Status: {profile.status}")
print(f"Registration date: {profile.registration_date}")
```

## Testing

### Unit Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run unit tests
pytest

# Run with coverage
pytest --cov=moy_nalog
```

### Integration Test

Interactive script for testing all API functionality with a real account.

```bash
python scripts/integration_test.py
```

**What it tests:**
- Password and SMS authentication
- Session persistence (save/restore tokens)
- Simple receipt creation (1 item, cash payment)
- Multi-item receipt (3 items with quantities)
- Receipt with individual client info
- Receipt with legal entity client (INN required)
- Receipt with bank transfer payment (WIRE)
- Income list retrieval with pagination
- Receipt data retrieval by UUID
- Receipt cancellation

**How it works:**
1. Choose authentication method (password or SMS)
2. Enter credentials
3. Script runs all tests sequentially
4. All created receipts are cancelled automatically
5. Detailed log and JSON report are saved to `test_output/` directory

**Output:**
- `test_output/<timestamp>/test_log_*.log` - detailed execution log
- `test_output/<timestamp>/test_report_*.json` - JSON report with results
- `test_output/<timestamp>/receipts/` - downloaded receipt files (JSON/HTML)

## Requirements

- Python 3.10+
- httpx >= 0.25.0
- pydantic >= 2.0.0

## Disclaimer

This is an **unofficial** client. The API may change without notice. Use at your own risk. The author is not responsible for any issues with tax authorities.

Always verify receipts in your personal cabinet at [lknpd.nalog.ru](https://lknpd.nalog.ru).

## Author

Kirill Nikulin (c) 2025 [kirodev.eu](https://kirodev.eu)

## License

MIT License - see [LICENSE](LICENSE) file.

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `pytest`
5. Run linting: `ruff check .`
6. Submit a pull request
