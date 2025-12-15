# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
