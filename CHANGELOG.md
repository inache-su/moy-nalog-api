# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.4] - 2026-01-16

### Added
- New `device_id` property on both `MoyNalogClient` and `MoyNalogClientSync` for accessing the device identifier
- New `download_receipt_raw()` method for downloading receipt as raw bytes with retry support
- New `user_agent` parameter to customize User-Agent header in requests

### Changed
- Improved sync client cleanup with `__del__` method and `_closed` flag to prevent resource leaks
- Better error handling: safe JSON parsing, UUID validation for receipt IDs
- Internal refactoring: extracted `_normalize_phone`, `_parse_datetime`, `_validate_receipt_uuid` helper methods

## [1.0.3] - 2025-12-26

### Fixed
- `is_token_expired` now returns `True` when token expiration time is unknown (previously returned `False`, which could cause `TokenExpiredError` on requests with stale tokens)
- Added automatic retry with token refresh on 401 responses - if server returns 401, client will attempt to refresh the token and retry the request once before raising `TokenExpiredError`

### Changed
- Token refresh is now more aggressive: tokens with unknown expiration time are treated as expired to ensure proactive refresh

## [1.0.2] - 2025-12-15

### Added
- Proxy server support for all API requests
  - HTTP/HTTPS proxy (works out of the box)
  - SOCKS4/SOCKS5 proxy (requires `pip install moy-nalog-api[socks]`)
  - Proxy authentication support (user:password in URL)
- New `proxy` parameter in `MoyNalogClient` and `MoyNalogClientSync`
- New optional dependency `[socks]` for SOCKS proxy support (httpx-socks)

## [1.0.1] - 2025-12-14

### Fixed
- README cross-links for PyPI display
- Missing properties and methods in sync client

## [1.0.0] - 2025-12-14

### Added
- Initial release
- Async client (`MoyNalogClient`) with httpx
- Sync wrapper (`MoyNalogClientSync`) for non-async code
- Password authentication via nalog.ru credentials
- SMS authentication (request code + verify)
- Automatic token refresh before expiration
- Session persistence to JSON file
- Retry with exponential backoff
- Full Pydantic v2 validation
- Receipt creation (single and multiple items)
- Receipt cancellation with reason (refund/mistake)
- Income list with pagination and filtering
- User profile retrieval
- All client types support (individual, legal entity, foreign)
- Payment types (cash, wire transfer)
- Complete type hints (mypy compatible)
- Comprehensive documentation in English and Russian
