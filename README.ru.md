# moy-nalog-api

[![GitHub](https://img.shields.io/badge/GitHub-inache--su%2Fmoy--nalog--api-181717?logo=github)](https://github.com/inache-su/moy-nalog-api)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PyPI version](https://badge.fury.io/py/moy-nalog-api.svg)](https://pypi.org/project/moy-nalog-api/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

**Самый полный и современный Python-клиент для сервиса самозанятых (lknpd.nalog.ru).**

Неофициальный Python-клиент для API "Мой налог" (самозанятые, режим НПД).

[English version](https://github.com/inache-su/moy-nalog-api/blob/main/README.md)

## Почему moy-nalog-api?

Существует несколько Python-библиотек для API "Мой налог". Вот почему стоит выбрать эту:

| Возможность | moy-nalog-api | Другие |
|-------------|---------------|--------|
| **Async/await** | Нативный httpx async | Часто только sync или requests |
| **Sync-обёртка** | Да, для синхронного кода | Обычно или одно, или другое |
| **SMS-аутентификация** | Полная поддержка (запрос + подтверждение) | Часто отсутствует или сломана |
| **Сохранение сессии** | Встроенное хранение в JSON | Требуется ручная реализация |
| **Авто-обновление токена** | Автоматически до истечения | Требуется ручное обновление |
| **Type hints** | 100% типизация, совместимость с mypy | Частичная или отсутствует |
| **Pydantic v2** | Полная валидация и сериализация | Часто dict или Pydantic v1 |
| **Современный Python** | 3.10+ с новым синтаксисом | Часто 3.7+ с устаревшим кодом |
| **Обработка ошибок** | Типизированная иерархия исключений | Общие исключения |
| **Повторные попытки** | Встроенный exponential backoff | Обычно отсутствует |
| **Несколько позиций** | Нативная поддержка мульти-чеков | Только одна позиция |
| **Поддержка прокси** | HTTP, HTTPS, SOCKS4/5 | Часто отсутствует |
| **Документация** | Подробная с примерами | Часто минимальная |

## Возможности

- Async (httpx) и sync клиент
- Аутентификация по паролю и SMS
- Автоматическое обновление токена с сохранением сессии
- Повторные попытки с exponential backoff
- Полная валидация Pydantic v2
- Несколько позиций в одном чеке
- Все типы клиентов (физлицо, юрлицо, иностранная организация)
- Список доходов с пагинацией и фильтрацией
- Отмена чеков с указанием причины
- Поддержка HTTP/HTTPS и SOCKS прокси
- Полная типизация для поддержки IDE

## Установка

```bash
pip install moy-nalog-api
```

Для поддержки SOCKS-прокси:
```bash
pip install moy-nalog-api[socks]
```

Для разработки:
```bash
pip install moy-nalog-api[dev]
```

## Быстрый старт

### Async (рекомендуется)

```python
import asyncio
from decimal import Decimal
from moy_nalog import MoyNalogClient

async def main():
    # Создаём клиент с сохранением сессии
    async with MoyNalogClient(session_file="session.json") as client:

        # Первый запуск: аутентификация
        if not client.is_authenticated:
            await client.auth_by_password("ваш_инн", "ваш_пароль")

        # Создаём чек
        receipt = await client.create_receipt(
            name="Консультационные услуги",
            amount=Decimal("5000.00")
        )

        print(f"Чек создан: {receipt.print_url}")

asyncio.run(main())
```

### Sync

```python
from decimal import Decimal
from moy_nalog import MoyNalogClientSync

with MoyNalogClientSync(session_file="session.json") as client:
    if not client.is_authenticated:
        client.auth_by_password("ваш_инн", "ваш_пароль")

    receipt = client.create_receipt(
        name="Консультационные услуги",
        amount=Decimal("5000.00")
    )

    print(f"Чек создан: {receipt.print_url}")
```

## Аутентификация

### По паролю

Используйте ИНН или телефон и пароль от nalog.ru:

```python
profile = await client.auth_by_password(
    username="123456789012",  # ИНН (12 цифр) или телефон
    password="ваш_пароль"
)
print(f"Авторизован как: {profile.display_name}")
print(f"ИНН: {profile.inn}")
print(f"Статус: {profile.status}")
```

### По SMS

Двухэтапный процесс аутентификации по телефону:

```python
# Шаг 1: Запрос SMS-кода
phone = "79001234567"  # Формат: 7XXXXXXXXXX (11 цифр)
challenge = await client.request_sms_code(phone)
print(f"SMS отправлено! Код действителен {challenge.expire_in} секунд")

# Шаг 2: Ввод кода и аутентификация
code = input("Введите 6-значный код из SMS: ")
profile = await client.auth_by_sms(phone, challenge.challenge_token, code)
print(f"Авторизован как: {profile.display_name}")
```

### Сохранение сессии

Автоматическое сохранение и восстановление токенов:

```python
# Файл сессии хранит токены между запусками
client = MoyNalogClient(session_file="session.json")

# Проверка, авторизован ли клиент из предыдущей сессии
if client.is_authenticated:
    print("Сессия восстановлена из файла")
else:
    # Аутентификация (токены сохраняются автоматически)
    await client.auth_by_password(username, password)

# Токены обновляются автоматически при истечении
# Сессия сохраняется при закрытии
```

Файл сессии содержит:
- Access token (для API-запросов)
- Refresh token (для обновления токена)
- Время истечения токена
- ИНН пользователя и ID устройства

## Создание чеков

### Простой чек

```python
from decimal import Decimal

receipt = await client.create_receipt(
    name="Разработка сайта",
    amount=Decimal("15000.00")
)

print(f"UUID: {receipt.uuid}")
print(f"Сумма: {receipt.total_amount} руб.")
print(f"Ссылка для печати: {receipt.print_url}")
print(f"JSON: {receipt.json_url}")
```

### Несколько позиций

```python
from decimal import Decimal
from moy_nalog import ServiceItem

items = [
    ServiceItem(name="Консультация", amount=Decimal("3000"), quantity=2),
    ServiceItem(name="Разработка", amount=Decimal("10000"), quantity=1),
    ServiceItem(name="Поддержка", amount=Decimal("500"), quantity=4),
]

receipt = await client.create_receipt_multi(items)
# Итого: 3000*2 + 10000*1 + 500*4 = 18000 руб.
print(f"Итого: {receipt.total_amount} руб.")
```

### С информацией о клиенте

#### Физическое лицо (по умолчанию)

```python
from moy_nalog import Client, IncomeType

client_info = Client(
    income_type=IncomeType.INDIVIDUAL,
    display_name="Иван Петров",
    contact_phone="+79001234567"
)

receipt = await client.create_receipt(
    name="Услуга",
    amount=Decimal("1000"),
    client=client_info
)
```

#### Юридическое лицо

```python
company = Client(
    income_type=IncomeType.LEGAL_ENTITY,
    display_name="ООО Ромашка",
    inn="7712345678"  # 10 цифр для компаний
)

receipt = await client.create_receipt(
    name="B2B услуга",
    amount=Decimal("50000"),
    client=company
)
```

#### Иностранная организация

```python
foreign = Client(
    income_type=IncomeType.FOREIGN_AGENCY,
    display_name="Acme Corporation",
    inn="9909123456"
)

receipt = await client.create_receipt(
    name="Международный консалтинг",
    amount=Decimal("100000"),
    client=foreign
)
```

### Типы оплаты

```python
from moy_nalog import PaymentType

# Наличные или карта (по умолчанию)
receipt = await client.create_receipt(
    name="Услуга",
    amount=Decimal("1000"),
    payment_type=PaymentType.CASH
)

# Безналичный расчёт (требуется юрлицо с ИНН)
receipt = await client.create_receipt(
    name="Услуга",
    amount=Decimal("50000"),
    client=company,  # Должен быть ИНН
    payment_type=PaymentType.WIRE
)
```

## Отмена чеков

Отмена чека в текущем налоговом периоде:

```python
from moy_nalog import CancelReason

# Клиент запросил возврат
await client.cancel_receipt(
    receipt_uuid="abc123",
    reason=CancelReason.REFUND
)

# Чек создан по ошибке
await client.cancel_receipt(
    receipt_uuid="abc123",
    reason=CancelReason.MISTAKE
)
```

## Просмотр чеков

### Список доходов

```python
from datetime import datetime

# Получить последние чеки (по умолчанию: 50)
incomes = await client.get_incomes()

for receipt in incomes.items:
    status = "ОТМЕНЁН" if receipt.is_cancelled else "АКТИВЕН"
    print(f"{receipt.uuid}: {receipt.total_amount} руб. [{status}]")

print(f"Всего: {incomes.total}")
print(f"Есть ещё: {incomes.has_more}")
```

### С фильтрами и пагинацией

```python
incomes = await client.get_incomes(
    from_date=datetime(2024, 1, 1),
    to_date=datetime(2024, 12, 31),
    offset=0,
    limit=50
)

# Загрузить ещё при необходимости
if incomes.has_more:
    more = await client.get_incomes(offset=50, limit=50)
```

### Детали чека

```python
# Получить полные данные чека как dict
data = await client.get_receipt("receipt_uuid")
if data:
    print(f"Услуги: {data['services']}")
    print(f"Тип оплаты: {data['paymentType']}")

# Получить URL для печати
url = client.get_receipt_print_url("receipt_uuid")
```

### Скачивание чека

Скачивание чека в виде сырых байтов для сохранения или обработки:

```python
# Скачать как JSON
json_bytes = await client.download_receipt_raw("receipt_uuid", format="json")
with open("receipt.json", "wb") as f:
    f.write(json_bytes)

# Скачать как PNG изображение (для печати)
png_bytes = await client.download_receipt_raw("receipt_uuid", format="print")
with open("receipt.png", "wb") as f:
    f.write(png_bytes)
```

## Обработка ошибок

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
    print("Неверный логин или пароль")
except TokenExpiredError:
    print("Сессия истекла, авторизуйтесь заново")
except AuthenticationError as e:
    print(f"Ошибка авторизации: {e.message}")

try:
    await client.request_sms_code(phone)
except SMSRateLimitError:
    print("Слишком много SMS-запросов, подождите минуту")
except SMSError as e:
    print(f"Ошибка SMS: {e.message}")

try:
    await client.create_receipt("Услуга", Decimal("1000"))
except ReceiptError as e:
    print(f"Ошибка чека: {e.message}")
    print(f"Код ошибки: {e.code}")
    print(f"Ответ API: {e.response}")

try:
    # Сетевые ошибки повторяются автоматически
    await client.get_incomes()
except NetworkError:
    print("Сеть недоступна после повторных попыток")
except RateLimitError:
    print("Превышен лимит запросов API")
```

## Конфигурация

```python
client = MoyNalogClient(
    # Часовой пояс для временных меток чеков (по умолчанию: Europe/Moscow)
    timezone="Europe/Moscow",

    # Таймаут запроса в секундах (по умолчанию: 30)
    timeout=30.0,

    # Количество повторных попыток (по умолчанию: 3)
    max_retries=3,

    # Путь к файлу сессии (опционально)
    session_file="session.json",

    # Авто-обновление токенов до истечения (по умолчанию: True)
    auto_refresh_token=True,

    # URL прокси-сервера (опционально)
    proxy="http://proxy.example.com:8080",

    # Пользовательский User-Agent (опционально)
    user_agent="MyApp/1.0",
)
```

## Поддержка прокси

Клиент поддерживает HTTP, HTTPS и SOCKS прокси для всех API-запросов.

### HTTP/HTTPS прокси

```python
# HTTP прокси (работает из коробки)
client = MoyNalogClient(proxy="http://proxy.example.com:8080")

# С аутентификацией
client = MoyNalogClient(proxy="http://user:password@proxy.example.com:8080")

# HTTPS прокси
client = MoyNalogClient(proxy="https://proxy.example.com:8080")
```

### SOCKS прокси

Для SOCKS-прокси требуется дополнительная зависимость:

```bash
pip install moy-nalog-api[socks]
```

```python
# SOCKS5 прокси
client = MoyNalogClient(proxy="socks5://proxy.example.com:1080")

# SOCKS5 с аутентификацией
client = MoyNalogClient(proxy="socks5://user:password@proxy.example.com:1080")

# SOCKS4 прокси
client = MoyNalogClient(proxy="socks4://proxy.example.com:1080")
```

### Синхронный клиент

Синхронная обёртка также поддерживает прокси:

```python
client = MoyNalogClientSync(proxy="http://proxy.example.com:8080")
```

## Профиль пользователя

```python
profile = await client.get_user_profile()

print(f"ID: {profile.id}")
print(f"ИНН: {profile.inn}")
print(f"Телефон: {profile.phone}")
print(f"Email: {profile.email}")
print(f"Имя: {profile.display_name}")
print(f"Полное имя: {profile.full_name}")
print(f"Статус: {profile.status}")
print(f"Дата регистрации: {profile.registration_date}")
```

## Тестирование

### Unit-тесты

```bash
# Установка dev-зависимостей
pip install -e ".[dev]"

# Запуск unit-тестов
pytest

# С покрытием
pytest --cov=moy_nalog
```

### Интеграционный тест

Интерактивный скрипт для тестирования всего функционала API с реальным аккаунтом.

```bash
python scripts/integration_test.py
```

**Что тестируется:**
- Аутентификация по паролю и SMS
- Сохранение сессии (сохранение/восстановление токенов)
- Создание простого чека (1 позиция, наличные)
- Мульти-чек (3 позиции с количеством)
- Чек с информацией о физлице
- Чек с информацией о юрлице (требуется ИНН)
- Чек с безналичной оплатой (WIRE)
- Получение списка доходов с пагинацией
- Получение данных чека по UUID
- Отмена чека

**Как работает:**
1. Выберите метод аутентификации (пароль или SMS)
2. Введите учётные данные
3. Скрипт выполняет все тесты последовательно
4. Все созданные чеки отменяются автоматически
5. Подробный лог и JSON-отчёт сохраняются в директорию `test_output/`

**Результаты:**
- `test_output/<timestamp>/test_log_*.log` - подробный лог выполнения
- `test_output/<timestamp>/test_report_*.json` - JSON-отчёт с результатами
- `test_output/<timestamp>/receipts/` - скачанные файлы чеков (JSON/HTML)

## Требования

- Python 3.10+
- httpx >= 0.25.0
- pydantic >= 2.0.0

## Отказ от ответственности

Это **неофициальный** клиент. API может измениться без предупреждения. Используйте на свой риск. Автор не несёт ответственности за любые проблемы с налоговыми органами.

Всегда проверяйте чеки в личном кабинете на [lknpd.nalog.ru](https://lknpd.nalog.ru).

## Автор

Kirill Nikulin (c) 2025 [kirodev.eu](https://kirodev.eu)

## Лицензия

MIT License - см. файл [LICENSE](LICENSE).

## Участие в разработке

Вклад приветствуется! Пожалуйста:
1. Сделайте fork репозитория
2. Создайте feature-ветку
3. Внесите изменения
4. Запустите тесты: `pytest`
5. Запустите линтер: `ruff check .`
6. Отправьте pull request
