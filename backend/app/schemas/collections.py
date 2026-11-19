from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.services.collections_prompt import NOTES_MAX, clean, normalize_phone


class SoloCallIn(BaseModel):
    """One borrower for one call. Phone and amount are required; the name and lender may instead be given in
    `context`, the operator's free-text notes about the borrower (loan history, past payments, earlier calls)."""

    borrower_name: str = Field(default="", max_length=80)
    phone: str = Field(min_length=10, max_length=20)
    amount: Decimal = Field(gt=0, le=Decimal("1000000000"), decimal_places=2)
    bank: str = Field(default="", max_length=80)
    currency: str = Field(default="INR", pattern="^[A-Z]{3}$")
    due_date: date | None = None
    context: str = Field(default="", max_length=NOTES_MAX)

    @field_validator("borrower_name", "bank")
    @classmethod
    def _one_line(cls, v: str) -> str:
        v = clean(v, 80)
        if 0 < len(v) < 2:
            raise ValueError("too short")
        return v

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        return normalize_phone(v)
