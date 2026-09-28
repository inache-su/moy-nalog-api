<p align="center">
  <img
    src="https://raw.githubusercontent.com/inache-su/moy-nalog-api/main/assets/readme/hero-ru.svg"
    width="100%"
    alt="moy-nalog-api — типизированный async- и sync-доступ из Python к аутентификации, сессиям и операциям с чеками lknpd.nalog.ru"
  >
</p>

<p align="center">
  <a href="https://pypi.org/project/moy-nalog-api/"><img src="https://img.shields.io/pypi/v/moy-nalog-api?label=PyPI&color=EF5A5A" alt="Версия на PyPI"></a>
  <a href="https://pypi.org/project/moy-nalog-api/"><img src="https://img.shields.io/pypi/pyversions/moy-nalog-api?color=3776AB" alt="Поддерживаемые версии Python"></a>
  <a href="https://github.com/inache-su/moy-nalog-api/blob/main/LICENSE"><img src="https://img.shields.io/github/license/inache-su/moy-nalog-api?color=0D1117" alt="Лицензия MIT"></a>
  <img src="https://img.shields.io/badge/typed-Pydantic%20v2-EF5A5A" alt="Типизация на Pydantic v2">
</p>

<p align="center">
  <a href="https://github.com/inache-su/moy-nalog-api/blob/main/README.md">English version</a>
  ·
  <a href="https://pypi.org/project/moy-nalog-api/">PyPI</a>
  ·
  <a href="https://github.com/inache-su/moy-nalog-api/blob/main/CHANGELOG.md">История изменений</a>
  ·
  <a href="https://github.com/inache-su/moy-nalog-api/tree/main/examples">Примеры</a>
</p>

`moy-nalog-api` — неофициальный Python-клиент для сервиса самозанятых
`lknpd.nalog.ru`. Он объединяет аутентификацию, обновление токенов, сохранение сессии,
повторные сетевые запросы и модели чеков в одном типизированном async API с аналогичной
синхронной обёрткой.

> **Неофициальный клиент.** Проект не связан с Федеральной налоговой службой России. Закрытый API
> может измениться без предупреждения. Всегда проверяйте зарегистрированные и аннулированные чеки в
> [личном кабинете](https://lknpd.nalog.ru).

## Установка

```bash
python -m pip install moy-nalog-api
```

Дополнительный extra нужен только для SOCKS4/5:

```bash
python -m pip install "moy-nalog-api[socks]"
```

Требуются Python 3.10+, `httpx` 0.25+ и Pydantic v2.

## Первый чек

```python
import asyncio
from decimal import Decimal

from moy_nalog import MoyNalogClient


async def main() -> None:
    async with MoyNalogClient(
        session_file=".moy-nalog-session.json",
    ) as client:
        if not client.is_authenticated:
            # Для входа по паролю нужен ИНН, а не номер телефона.
            await client.auth_by_password("your_inn", "your_password")

        # Этот вызов регистрирует реальный чек в налоговом сервисе.
        receipt = await client.create_receipt(
            name="Консультационные услуги",
            amount=Decimal("5000.00"),
        )
        print(receipt.print_url)


asyncio.run(main())
```

> **Операция с реальным аккаунтом.** `create_receipt()` изменяет реальный налоговый аккаунт.
> Сохраните идентификатор чека, проверьте результат в личном кабинете и явно аннулируйте ошибочный чек через
> `cancel_receipt()`.

## Что берёт на себя клиент

| Граница | Конкретное поведение |
| --- | --- |
| Устройство клиента | `MoyNalogClient` — основная async-реализация; `MoyNalogClientSync` делегирует ей операции |
| Аутентификация | Вход по ИНН и паролю или двухэтапная проверка по телефону и СМС |
| Жизненный цикл сессии | Опциональное хранение в JSON, проактивное обновление и одно обновление с повтором после ответа `401` |
| Чеки | Одна или несколько позиций, тип клиента, вид оплаты, создание, просмотр, скачивание, список и аннулирование |
| Транспорт | Нативные HTTP/HTTPS-прокси, опциональный SOCKS, настраиваемые таймауты и ограниченный backoff |
| Ошибки | Публичная типизированная иерархия; ошибки валидации и API не маскируются под сетевые |

Публичный API возвращает Pydantic-модели `UserProfile`, `Receipt`, `IncomeList`,
`SMSChallenge` и другие. Суммы в чеках представлены типом `Decimal`.

## Аутентификация

### ИНН и пароль

Вход по паролю использует поток личного кабинета и требует 10- или 12-значный ИНН:

```python
profile = await client.auth_by_password(
    username="123456789012",
    password="your_password",
)

print(profile.display_name)
print(profile.inn)
```

Не передавайте номер телефона в `auth_by_password()`. Для входа по телефону используйте
СМС-поток.

### Телефон и СМС

```python
phone = "79001234567"

challenge = await client.request_sms_code(phone)
code = input("Код из СМС: ")

profile = await client.auth_by_sms(
    phone=phone,
    challenge_token=challenge.challenge_token,
    code=code,
)
```

Запрос СМС использует v2-эндпоинт сервиса, а проверка — v1. Клиент скрывает эту особенность API.

### Сохранение сессии

Передайте `session_file`, чтобы автоматически восстанавливать и сохранять учётные данные:

```python
async with MoyNalogClient(session_file=".moy-nalog-session.json") as client:
    if client.is_authenticated:
        profile = await client.get_user_profile()
    else:
        profile = await client.auth_by_password(username, password)
```

Файл содержит access- и refresh-токены, ИНН аутентифицированного пользователя, идентификатор
устройства и время жизни токенов. В POSIX-системах файл записывается с правами только для
владельца (`0o600`).

> **Чувствительные данные сессии.** Никогда не коммитьте, не передавайте и не логируйте файл
> сессии. Добавьте точный путь к нему в `.gitignore`.

Если данные получены из другого доверенного хранилища, сессией можно управлять вручную:

```python
client.set_tokens(
    access_token="access_token",
    refresh_token="refresh_token",
    inn="123456789012",
)

refreshed = await client.refresh_access_token()
client.clear_session()
```

Оба клиента предоставляют свойства `is_authenticated`, `inn`, `access_token`, `refresh_token`,
`token_expires_at`, `is_token_expired` и `device_id`.

При входе клиент проверяет весь ответ, включая профиль, до замены данных сессии.
Некорректный ответ оставляет прежние токены и профиль без изменений.

## Операции с чеками

### Несколько позиций

```python
from decimal import Decimal

from moy_nalog import ServiceItem

items = [
    ServiceItem(name="Консультация", amount=Decimal("3000"), quantity=2),
    ServiceItem(name="Разработка", amount=Decimal("10000")),
    ServiceItem(name="Поддержка", amount=Decimal("500"), quantity=4),
]

receipt = await client.create_receipt_multi(items)
print(receipt.total_amount)  # 18000
```

### Клиент и вид оплаты

```python
from decimal import Decimal

from moy_nalog import Client, IncomeType, PaymentType

company = Client(
    income_type=IncomeType.LEGAL_ENTITY,
    display_name="ООО Ромашка",
    inn="7712345678",
)

receipt = await client.create_receipt(
    name="Услуга для компании",
    amount=Decimal("50000"),
    client=company,
    payment_type=PaymentType.WIRE,
)
```

Доступные источники дохода: `INDIVIDUAL`, `LEGAL_ENTITY` и `FOREIGN_AGENCY`. Для безналичного
перевода нужны данные юридического лица с ИНН.

### Список, просмотр и скачивание

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

`get_receipt()` возвращает `None` только при ответе API `404`. По умолчанию `download_receipt_raw()` возвращает
`None` при `404`, постоянных клиентских ошибках вроде `403` или после исчерпания повторов
при сетевых и серверных ошибках. Постоянные клиентские ошибки останавливают повторы после первой
попытки. При `401` возможны
одно обновление токена и повтор запроса; если авторизация не удалась, клиент вызывает
`TokenExpiredError`. Остальные ответы `4xx`, кроме `404`, вызывают `MoyNalogError` или его подклассы
при `strict_api_errors=True`. Превышение лимита запросов вызывает `RateLimitError` в обоих режимах.
Ответы о технических работах вызывают `ServiceUnavailableError` без повторов. Скачивание в формате
`print` возвращает сырые байты, обычно с HTML; клиент не предоставляет Content-Type ответа API.

При `strict_api_errors=True` метод `get_incomes()` требует явного списка чеков в ответе
и вызывает `MoyNalogError` при некорректном ответе. `find_receipt_candidates()` выполняет эту
проверку при любом значении настройки: повреждённый ответ не превращается в пустой список кандидатов.
Явный пустой список остаётся допустимым ответом в обоих режимах.

### Аннулирование чека

```python
from moy_nalog import CancelReason

await client.cancel_receipt(
    receipt_uuid=receipt.uuid,
    reason=CancelReason.MISTAKE,
)
```

Для возврата используйте `CancelReason.REFUND`. Идентификатор чека проверяется до отправки запроса.
Клиент принимает идентификаторы ФНС из 10 латинских букв и цифр, а также стандартные UUID.
Публичные имена `Receipt.uuid` и `receipt_uuid` сохранены для обоих форматов.

Возвращаемый `Receipt` имеет `is_cancelled=True` и сохраняет поля чека, полученные от сервера.
Если ответ не содержит сведений об аннулировании, `cancellation_info` хранит переданные причину
и время операции; время регистрации на сервере не подставляется. При отсутствии суммы
сохраняется прежнее значение по умолчанию `total_amount=0`.

## Надёжность и ошибки

Версия 1.1.0 по умолчанию сохраняет возвраты скачивания и списка доходов при ошибках, а также
обёртки ошибок создания из 1.0.6. Оба клиента принимают
`strict_api_errors=True`: включайте строгий режим после обновления обработчиков ошибок приложения.

| Операция | По умолчанию (`False`) | Строгий режим (`True`) |
| --- | --- | --- |
| Постоянные ошибки скачивания, например `403` | Вернуть `None` без повторов | Вызвать `MoyNalogError` без повторов |
| В ответе со списком доходов нет самого списка | Сохранить пустой `IncomeList` | Вызвать `MoyNalogError` |
| Некорректные поля модели доходов | Сохранить ошибки валидации Pydantic | Вызвать `MoyNalogError` |
| Неустранённый `401` или `429` при создании, если ранее ответ не был потерян | Сохранить обёртку `ReceiptError` | Вызвать `TokenExpiredError`/`RateLimitError` |

Отсутствие учётных данных по-прежнему вызывает `AuthenticationError` до создания чека в обоих режимах.
Новые исключения дубликата и неопределённого результата наследуются от `ReceiptError`, поэтому
существующие обработчики `except ReceiptError` продолжают их перехватывать. Ошибка поиска кандидатов
всегда вызывает исключение; пустой список доходов по умолчанию не доказывает, что чек не был создан.

Токены обновляются проактивно незадолго до истечения. Если аутентифицированный запрос всё же
получает `401`, клиент может один раз обновить токен и повторить запрос даже при `max_retries=1`.
Этот повтор не расходует попытку для сетевых ошибок. Параллельные операции одного клиента ждут
общее обновление токена; отмена одного вызова не отменяет это обновление. Сетевые ошибки
и таймауты используют настроенный ограниченный backoff. Ошибки аутентификации, rate limit,
технических работ, валидации и другие ответы API сохраняют публичные типы исключений с учётом
описанных выше обёрток при создании чека.
Для создания чека дополнительно учитывается неопределённость результата, описанная ниже.

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
    receipt = await client.create_receipt("Услуга", 1000)
except ReceiptCreationUnknownError as exc:
    candidates = await client.find_receipt_candidates(exc.payload)
    for candidate in candidates:
        print("Кандидат для проверки:", candidate.uuid)
    raise  # До сверки чека результат операции остаётся неопределённым.
except ServiceUnavailableError:
    print("Налоговый сервис временно недоступен")
except RateLimitError:
    print("Превышен лимит запросов API")
except (AuthenticationError, ValidationError, ReceiptError, NetworkError) as exc:
    print(exc)
```

Методы аутентификации используют типизированные ошибки `InvalidCredentialsError`,
`InvalidSMSCodeError` и `SMSRateLimitError`.

Все публичные исключения наследуются от `MoyNalogError`. Полная иерархия находится в
[`moy_nalog/exceptions.py`](https://github.com/inache-su/moy-nalog-api/blob/main/moy_nalog/exceptions.py).

### Потерянный ответ и дубликат чека

`DuplicateReceiptError` соответствует точному коду ФНС `receipt.duplication` и наследуется от
`ReceiptCreationUnknownError`, который наследуется от `ReceiptError`. Ответ о дубликате
не подтверждает успех этой попытки и не означает, что нужно создать ещё один чек.

`ReceiptCreationUnknownError` также возникает после исчерпания сетевых попыток, при непригодном
ответе об успехе и серверных ошибках, кроме отдельно распознанных технических работ.
Если ответ предыдущей попытки потерян, последующий отказ API оставляет результат создания
неопределённым; последующий ответ сохраняется в `exc.response`. Оба исключения останавливают
повторы создания.

В пределах одного вызова создания повторы используют исходный payload, включая `operationTime`,
`requestTime` и все позиции чека. Оба исключения предоставляют его копию через `exc.payload`;
изменение копии не затрагивает сохранённые данные. SDK хранит payload только в памяти.
Для сверки после перезапуска сохраните его вместе с незавершённой операцией в закрытом хранилище
приложения. Новый вызов `create_receipt()` формирует новый payload и не является идемпотентным
повтором.

`find_receipt_candidates(exc.payload)` перебирает через `get_incomes()` все страницы за дату
операции в UTC в том же налоговом аккаунте. Сверяются точное время операции, сумма, вид оплаты
и позиции в исходном порядке, включая количество. Чеки с отличающимся типом дохода, если ФНС
вернула это поле, и аннулированные чеки исключаются. Метод только читает данные и доступен
в async- и sync-клиентах.

Каждый результат требует проверки, даже если найден один кандидат. До подтверждения операции
сравните данные покупателя из `get_receipt(candidate.uuid)` с исходным payload и своими данными
о платеже. Пустой список, недостающие поля чека, несколько кандидатов или ошибка поиска
не доказывают, что создание не состоялось. Оставьте операцию неразрешённой; не меняйте её
временные метки и не создавайте замену автоматически.

## Конфигурация

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

| Параметр | Значение по умолчанию | Назначение |
| --- | --- | --- |
| `timezone` | `"Europe/Moscow"` | Временная зона операций с чеками |
| `timeout` | `30.0` | Таймаут HTTP-запроса в секундах |
| `max_retries` | `3` | Ограниченное число попыток при сетевых ошибках и таймаутах |
| `session_file` | `None` | Опциональный путь к сохранённой сессии |
| `auto_refresh_token` | `True` | Обновление токенов перед истечением |
| `strict_api_errors` | `False` | Строгая валидация и конкретные ошибки создания/скачивания |
| `proxy` | `None` | URL HTTP-, HTTPS-, SOCKS4- или SOCKS5-прокси |
| `verify_ssl` | `True` | Проверка TLS-сертификатов |
| `user_agent` | браузероподобное значение | Пользовательский заголовок `User-Agent` |

HTTP- и HTTPS-прокси работают через нативный `httpx`. Для SOCKS нужен extra `socks`:

```python
client = MoyNalogClient(proxy="socks5://user:password@proxy.example.com:1080")
```

Учётные данные прокси можно передавать с percent-encoding: готовые escape-последовательности
не кодируются повторно. Скобки IPv6-адресов сохраняются, например `http://user:password@[::1]:8080`.

Оставляйте `verify_ssl=True`, если контролируемый перехватывающий прокси не требует другого
решения.

## Синхронный клиент

Sync-адаптер повторяет методы для чеков, аутентификации, сессии и профиля:

```python
from decimal import Decimal

from moy_nalog import MoyNalogClientSync

with MoyNalogClientSync(session_file=".moy-nalog-session.json") as client:
    if not client.is_authenticated:
        client.auth_by_password("your_inn", "your_password")

    receipt = client.create_receipt(
        name="Консультационные услуги",
        amount=Decimal("5000.00"),
    )
    print(receipt.print_url)
```

`MoyNalogClientSync` не является потокобезопасным и не должен вызываться внутри уже работающего
async event loop. Создавайте отдельный экземпляр для каждого потока или используйте
`MoyNalogClient` в асинхронном коде.

## Краткая карта публичного API

| Область | Методы |
| --- | --- |
| Аутентификация | `auth_by_password`, `request_sms_code`, `auth_by_sms`, `refresh_access_token` |
| Сессия | `set_tokens`, `clear_session` |
| Чеки | `create_receipt`, `create_receipt_multi`, `find_receipt_candidates`, `cancel_receipt`, `get_receipt` |
| Вывод чека | `get_receipt_print_url`, `download_receipt_raw` |
| Аккаунт | `get_incomes`, `get_user_profile` |

Асинхронные методы `MoyNalogClient` вызываются с `await`; sync-адаптер предоставляет те же операции без
`await`.

## Разработка

```bash
python -m pip install -e ".[dev]"
pytest
pytest --cov=moy_nalog
ruff check .
mypy moy_nalog
```

Unit-тесты работают без обращения к живому API. Интерактивный интеграционный скрипт вынесен
отдельно, потому что может изменить реальный налоговый аккаунт:

```bash
python scripts/integration_test.py
```

Режим по умолчанию `auth_only` аутентифицируется и получает профиль. Опциональный режим `full`
создаёт, скачивает, перечисляет и аннулирует реальные чеки. Очистка выполняется в режиме
best-effort: после каждого полного запуска проверьте личный кабинет. Логи и артефакты сохраняются
в `test_output/` и могут содержать чувствительные данные аккаунта.

## Совместимость и статус

- Python 3.10+
- `httpx>=0.25.0`
- `pydantic>=2.0.0`
- HTTP/HTTPS-прокси через `httpx`
- Опциональный SOCKS4/5 через `httpx-socks`

Пакет предоставляет стабильный публичный API, но использует закрытый и недокументированный
upstream API. Если приложение зависит от точного поведения ошибок или повторов, перед обновлением
прочитайте [историю изменений](https://github.com/inache-su/moy-nalog-api/blob/main/CHANGELOG.md).

## Участие в разработке

Приветствуются сфокусированные issues и pull requests. Сохраняйте async-реализацию основной,
поддерживайте паритет sync-обёртки, не обращайтесь к живому API в unit-тестах и запускайте:

```bash
pytest
ruff check .
mypy moy_nalog
```

## Лицензия

[MIT](https://github.com/inache-su/moy-nalog-api/blob/main/LICENSE) © 2025–2026 [Кирилл Никулин](https://kirodev.eu)
