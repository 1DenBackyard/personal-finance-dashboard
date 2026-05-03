"""Parser for Alfa-Bank XLSX statements."""
import re
import pandas as pd
from datetime import datetime


def _parse_amount(val) -> float:
    """Parse Alfa amount like '1 234,56' or '-9 910' to float."""
    if pd.isna(val):
        return 0.0
    s = str(val).replace("\xa0", "").replace(" ", "").replace(",", ".").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def _extract_mcc(description: str) -> str | None:
    """Extract MCC code from description if present."""
    m = re.search(r"MCC:\s*(\d{4})", description)
    return m.group(1) if m else None


def _extract_merchant(description: str) -> str | None:
    """Extract merchant name from card operation description."""
    # Pattern: "Оплата по карте: ..., место совершения операции: RU/CITY/MERCHANT, MCC:"
    m = re.search(r"операции:\s*\S+/\S+/([^,]+)", description)
    if m:
        return m.group(1).strip()
    return None


def _detect_internal_transfer(description: str, own_phones: list, own_accounts: list) -> bool:
    """Detect if transaction is an internal transfer between own accounts."""
    desc_lower = description.lower()

    # Direct internal bank transfer
    if "внутрибанковский перевод между счетами" in desc_lower:
        return True

    # Transfer to/from own phone via SBP
    for phone in own_phones:
        if phone in description:
            # Check it's a transfer, not a phone bill
            if "перевод" in desc_lower and "мобильная связь" not in desc_lower and "платеж" not in desc_lower.split("перевод")[0]:
                return True

    # Transfer mentioning own account numbers
    for acc in own_accounts:
        if acc in description:
            return True

    # Cashback / bonus operations
    if "cashback" in desc_lower or "кешбэк" in desc_lower or "кэшбек" in desc_lower:
        return False  # not a transfer, it's income

    # "Перевод собственных средств"
    if "перевод собственных средств" in desc_lower:
        return True

    return False


def parse_alfa(file_path: str, own_phones: list, own_accounts: list) -> list[dict]:
    """
    Parse Alfa-Bank XLSX statement.

    Returns list of dicts with keys:
        date, processed_date, amount, currency, description, raw_description,
        category_hint, is_internal_transfer, external_id, mcc, merchant,
        source_file, account_number, card_last4
    """
    df = pd.read_excel(file_path, sheet_name="Sheet1", header=None)

    # Extract account info from header
    account_number = str(df.iloc[7, 2]).strip() if not pd.isna(df.iloc[7, 2]) else None
    account_type = str(df.iloc[10, 2]).strip() if not pd.isna(df.iloc[10, 2]) else None

    # Find data start row (row with headers "Дата операции")
    data_start = None
    for i in range(15, 25):
        val = str(df.iloc[i, 0]) if not pd.isna(df.iloc[i, 0]) else ""
        if "дата" in val.lower() and "операц" in val.lower():
            data_start = i + 1
            break
    if data_start is None:
        data_start = 20

    transactions = []
    for i in range(data_start, df.shape[0]):
        date_str = str(df.iloc[i, 0]).strip() if not pd.isna(df.iloc[i, 0]) else ""
        if not re.match(r"\d{2}\.\d{2}\.\d{4}", date_str):
            continue

        proc_date_str = str(df.iloc[i, 1]).strip() if not pd.isna(df.iloc[i, 1]) else date_str
        ext_id = str(df.iloc[i, 3]).strip() if not pd.isna(df.iloc[i, 3]) else None
        category_hint = str(df.iloc[i, 4]).strip() if not pd.isna(df.iloc[i, 4]) else None
        description = str(df.iloc[i, 11]).strip() if not pd.isna(df.iloc[i, 11]) else ""
        amount = _parse_amount(df.iloc[i, 12])
        status = str(df.iloc[i, 14]).strip() if not pd.isna(df.iloc[i, 14]) else ""

        # Extract card number from description
        card_match = re.search(r"\*{4,6}(\d{4})", description)
        card_last4 = card_match.group(1) if card_match else None

        try:
            date = datetime.strptime(date_str, "%d.%m.%Y").date()
        except ValueError:
            continue
        try:
            processed_date = datetime.strptime(proc_date_str, "%d.%m.%Y").date()
        except ValueError:
            processed_date = date

        mcc = _extract_mcc(description)
        merchant = _extract_merchant(description)
        is_internal = _detect_internal_transfer(description, own_phones, own_accounts)

        transactions.append({
            "date": date,
            "processed_date": processed_date,
            "amount": amount,
            "currency": "RUB",
            "description": description,
            "raw_description": description,
            "category_hint": category_hint,
            "is_internal_transfer": is_internal,
            "external_id": ext_id,
            "mcc": mcc,
            "merchant": merchant,
            "source_file": str(file_path),
            "account_number": account_number,
            "card_last4": card_last4,
            "status": status,
        })

    return transactions
