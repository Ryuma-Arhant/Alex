from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.services.collections_prompt import clean, normalize_phone


class SoloCallIn(BaseModel):
    borrower_name: str = Field(min_length=2, max_length=80)
    phone: str = Field(min_length=10, max_length=20)
    amount: Decimal = Field(gt=0, le=Decimal("1000000000"), decimal_places=2)
    bank: str = Field(min_length=2, max_length=80)
    currency: str = Field(default="INR", pattern="^[A-Z]{3}$")
    due_date: date | None = None

    @field_validator("borrower_name", "bank")
    @classmethod
    def _one_line(cls, v: str) -> str:
        v = clean(v, 80)
        if len(v) < 2:
            raise ValueError("too short")
        return v

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        return normalize_phone(v)
