"""Enums for Moy Nalog API."""

from enum import Enum


class IncomeType(str, Enum):
    """
    Client type for receipt (determines income source category).

    INDIVIDUAL: Payment from a physical person (default).
    LEGAL_ENTITY: Payment from a company or sole proprietor (requires client INN).
    FOREIGN_AGENCY: Payment from a foreign organization.
    """
    INDIVIDUAL = "FROM_INDIVIDUAL"
    LEGAL_ENTITY = "FROM_LEGAL_ENTITY"
    FOREIGN_AGENCY = "FROM_FOREIGN_AGENCY"


class CancelReason(str, Enum):
    """
    Receipt cancellation reason.

    REFUND: Client requested a refund.
    MISTAKE: Receipt was created by mistake (wrong amount, wrong service, etc.).
    """
    REFUND = "Возврат средств"
    MISTAKE = "Чек сформирован ошибочно"


class PaymentType(str, Enum):
    """
    Payment method for receipt.

    CASH: Cash or card payment (default for individuals).
    WIRE: Bank transfer (typically used with legal entities, requires client INN).
    """
    CASH = "CASH"
    WIRE = "WIRE"
