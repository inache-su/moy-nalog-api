"""Exceptions for Moy Nalog API."""

from typing import Any


class MoyNalogError(Exception):
    """Base exception for Moy Nalog API."""

    def __init__(self, message: str, code: str | None = None, response: Any | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.response = response

    def __str__(self) -> str:
        if self.code:
            return f"[{self.code}] {self.message}"
        return self.message


class AuthenticationError(MoyNalogError):
    """Authentication failed."""
    pass


class TokenExpiredError(AuthenticationError):
    """Access token has expired."""
    pass


class InvalidCredentialsError(AuthenticationError):
    """Invalid username or password."""
    pass


class SMSError(MoyNalogError):
    """SMS verification error."""
    pass


class SMSRateLimitError(SMSError):
    """Too many SMS requests."""
    pass


class InvalidSMSCodeError(SMSError):
    """Invalid SMS verification code."""
    pass


class ReceiptError(MoyNalogError):
    """Receipt operation failed."""
    pass


class ValidationError(MoyNalogError):
    """Input validation failed."""
    pass


class NetworkError(MoyNalogError):
    """Network request failed."""
    pass


class RateLimitError(MoyNalogError):
    """API rate limit exceeded."""
    pass
