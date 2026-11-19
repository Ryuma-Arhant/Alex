"""Bulk calling: parse and validate an uploaded CSV of borrowers. Nothing is stored and no call is placed here.

Columns are matched by name (case, spaces and punctuation ignored, common aliases accepted). Required: name, phone,
amount and deadline. Optional: lender, currency, loan reference and notes. Dates are read day-first (05/11/2026 is
the 5th of November), as is usual in India. Every row is checked independently, so one bad row never hides the rest.
"""

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.errors import AppError
from app.services.collections_prompt import clean, normalize_phone

MAX_BYTES = 1024 * 1024
MAX_ROWS = 1000
MAX_AMOUNT = Decimal("1000000000")

# canonical field -> accepted header spellings (after normalisation: lowercase, non-alphanumerics removed)
ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("name", "borrowername", "borrower", "fullname", "customername", "customer", "personname"),
    "phone": (
        "phone",
        "phonenumber",
        "phoneno",
        "mobile",
        "mobilenumber",
        "mobileno",
        "mobilephone",
        "mobilephonenumber",
        "contact",
        "contactnumber",
        "contactno",
    ),
    "amount": (
        "amount",
        "amountdue",
        "dueamount",
        "outstanding",
        "outstandingamount",
        "overdueamount",
        "emi",
        "emiamount",
    ),
    "deadline": ("deadline", "duedate", "dueby", "payby", "paymentdeadline", "paymentduedate", "lastdate"),
    "lender": ("lender", "lendername", "bank", "bankname"),
    "currency": ("currency",),
    "loan_reference": (
        "loanreference",
        "loanid",
        "loanno",
        "loannumber",
        "loanaccount",
        "loanaccountnumber",
        "accountnumber",
        "reference",
    ),
    "notes": ("notes", "note", "remarks", "remark", "comments", "comment"),
}
REQUIRED = ("name", "phone", "amount", "deadline")
LABELS = {"name": "Name", "phone": "Phone", "amount": "Amount due", "deadline": "Deadline"}
_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d %b %Y", "%d %B %Y", "%d-%b-%Y", "%d-%B-%Y")


class BadCsv(AppError):
    status_code, code = 422, "bad_csv"


def _key(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", header.lower())


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")  # Excel's "CSV UTF-8" starts with a BOM
    except UnicodeDecodeError:
        return data.decode("cp1252")  # Excel's plain "CSV" on Windows


def parse_amount(raw: str) -> Decimal:
    text = re.sub(r"(?i)\b(rs|inr|usd|eur|gbp|aed)\b\.?|[₹$€£,\s]", "", raw)
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("amount must be a number, e.g. 5200 or 5200.50") from None
    if not value.is_finite() or value <= 0:
        raise ValueError("amount must be greater than zero")
    if value > MAX_AMOUNT:
        raise ValueError("amount is too large")
    if value != value.quantize(Decimal("0.01")):
        raise ValueError("amount can have at most 2 decimal places")
    return value.quantize(Decimal("0.01"))


def parse_date(raw: str) -> date:
    text = " ".join(raw.split())
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError("deadline must be a date such as 2026-11-05 or 05/11/2026 (day first)")


def _row(line: int, raw: dict[str, str]) -> dict[str, Any]:
    errors: list[str] = []
    out: dict[str, Any] = {
        "line": line,
        "name": clean(raw.get("name", ""), 80),
        "phone": raw.get("phone", "").strip(),
        "amount": raw.get("amount", "").strip(),
        "currency": (raw.get("currency", "").strip() or "INR").upper(),
        "deadline": raw.get("deadline", "").strip(),
        "lender": clean(raw.get("lender", ""), 80),
        "loan_reference": clean(raw.get("loan_reference", ""), 40),
        "notes": clean(raw.get("notes", ""), 300),
    }
    for f in REQUIRED:
        if not out[f]:
            errors.append(f"{LABELS[f]} is missing")
    if out["name"] and len(out["name"]) < 2:
        errors.append("Name is too short")
    if out["phone"]:
        try:
            out["phone"] = normalize_phone(out["phone"])
        except ValueError as e:
            errors.append(f"Phone: {e}")
    if out["amount"]:
        try:
            out["amount"] = str(parse_amount(out["amount"]))
        except ValueError as e:
            errors.append(f"Amount due: {e}")
    if out["deadline"]:
        try:
            out["deadline"] = parse_date(out["deadline"]).isoformat()
        except ValueError as e:
            errors.append(f"Deadline: {e}")
    if not re.fullmatch(r"[A-Z]{3}", out["currency"]):
        errors.append("Currency must be a 3-letter code such as INR")
    out["errors"] = errors
    out["warnings"] = []
    out["valid"] = not errors
    return out


def parse_csv(data: bytes) -> dict[str, Any]:
    if not data.strip():
        raise BadCsv("The file is empty.")
    text = _decode(data)
    try:
        dialect: Any = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    header = next(reader, None)
    if not header or not any(h.strip() for h in header):
        raise BadCsv("The first line must be a header row naming the columns.")

    columns: dict[str, int] = {}
    ignored: list[str] = []
    for i, h in enumerate(header):
        field = next((f for f, names in ALIASES.items() if _key(h) in names), None)
        if field is None or field in columns:
            if h.strip():
                ignored.append(h.strip())
            continue
        columns[field] = i
    missing = [LABELS[f] for f in REQUIRED if f not in columns]
    if missing:
        raise BadCsv(f"Missing required column(s): {', '.join(missing)}.")

    rows: list[dict[str, Any]] = []
    for cells in reader:
        if not any(c.strip() for c in cells):
            continue  # blank line
        if len(rows) >= MAX_ROWS:
            raise BadCsv(f"Too many rows: at most {MAX_ROWS} borrowers per file.")
        raw = {f: (cells[i] if i < len(cells) else "") for f, i in columns.items()}
        rows.append(_row(reader.line_num, raw))
    if not rows:
        raise BadCsv("The file has a header but no borrower rows.")

    first_seen: dict[str, int] = {}
    for r in rows:
        if not r["valid"]:
            continue
        if r["phone"] in first_seen:
            r["warnings"].append(f"Same phone number as line {first_seen[r['phone']]}")
        else:
            first_seen[r["phone"]] = r["line"]

    valid = sum(1 for r in rows if r["valid"])
    return {
        "total": len(rows),
        "valid": valid,
        "invalid": len(rows) - valid,
        "columns": {f: header[i].strip() for f, i in columns.items()},
        "ignored_columns": ignored,
        "rows": rows,
    }
