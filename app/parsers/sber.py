"""Parser for Sberbank XLSX statements."""
import re
import pandas as pd
from datetime import datetime

# Month name mapping for Sber date format "26 июн. 2025, 17:21"
MONTH_MAP = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4,
    "мая": 5, "май": 5, "июн": 6, "июл": 7, "авг": 8,
    "сен": 9, "сент": 9, "окт": 10, "ноя": 11, "нояб": 11, "дек": 12,
}


def _parse_sber_date(date_str: str):
    """Parse Sber date like '26 июн. 2025, 17:21'."""
    m = re.match(r"(\d{1,2})\s+(\w+)\.?\s+(\d{4})", date_str)
    if not m:
        return None
    day = int(m.group(1))
    month_str = m.group(2).lower().rstrip(".")
    year = int(m.group(3))
    month = MONTH_MAP.get(month_str)
    if month is None:
        return None
    try:
        return datetime(year, month, day).date()
    except ValueError:
        return None


# Owner name fragments come from config.py (gitignored)
try:
    from config import OWN_NAME_PATTERNS
except ImportError:
    OWN_NAME_PATTERNS = []


def _is_own_name(description: str) -> bool:
    """Check if description matches owner's name."""
    desc_lower = description.lower().strip().rstrip(".")
    for pattern in OWN_NAME_PATTERNS:
        if pattern in desc_lower:
            return True
    return False


def _parse_amount(val) -> float:
    """Parse amount to float."""
    if pd.isna(val):
        return 0.0
    s = str(val).replace("\xa0", "").replace(" ", "").replace(",", ".").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_sber(file_path: str, own_phones: list, own_accounts: list) -> list[dict]:
    """
    Parse Sberbank XLSX statement.

    Sber format columns (sheet 'data'):
      0: Номер, 1: Дата, 2: Тип операции, 3: Категория, 4: Сумма,
      5: Валюта, 6: Сумма в валюте, 7: Описание, 8: Состояние,
      9: Номер карты/Номер договора
    """
    df = pd.read_excel(file_path, sheet_name="data", header=0)
    # Rename columns for easier access (they may be garbled)
    cols = list(df.columns)

    transactions = []
    for _, row in df.iterrows():
        date_str = str(row.iloc[1]).strip() if not pd.isna(row.iloc[1]) else ""
        date = _parse_sber_date(date_str)
        if date is None:
            continue

        op_type = str(row.iloc[2]).strip() if not pd.isna(row.iloc[2]) else ""
        category_hint = str(row.iloc[3]).strip() if not pd.isna(row.iloc[3]) else ""
        amount_val = _parse_amount(row.iloc[4])
        currency = str(row.iloc[5]).strip() if not pd.isna(row.iloc[5]) else "RUB"
        description = str(row.iloc[7]).strip() if not pd.isna(row.iloc[7]) else ""
        status = str(row.iloc[8]).strip() if not pd.isna(row.iloc[8]) else ""
        card_info = str(row.iloc[9]).strip() if not pd.isna(row.iloc[9]) else ""

        card_match = re.search(r"\*{3,4}\s*(\d{4})", card_info)
        card_last4 = card_match.group(1) if card_match else None

        # Sber only shows expenses, so amount should be negative
        if op_type.lower() == "расходы" or op_type.lower() == "расход":
            amount = -abs(amount_val)
        elif op_type.lower() == "доходы" or op_type.lower() == "доход":
            amount = abs(amount_val)
        else:
            amount = -abs(amount_val)  # default to expense

        # Detect internal transfers
        is_internal = False
        desc_lower = description.lower()
        if category_hint == "Переводы людям":
            # Check if it's a transfer to own phone
            for phone_frag in [p.lstrip("+7") for p in own_phones]:
                if phone_frag in description.replace(" ", ""):
                    is_internal = True
                    break
            # Check for own account numbers
            for acc in own_accounts:
                if acc in description:
                    is_internal = True
                    break
            # Transfer to own name (Sber shows recipient name as description)
            if _is_own_name(description):
                is_internal = True

        if category_hint == "Переводы людям" and "пополнение" in desc_lower:
            is_internal = True

        # Also check for "Пополнение счёта" type operations
        if "пополнение" in desc_lower and "собственн" in desc_lower:
            is_internal = True

        # Extract merchant from description
        merchant = None
        parts = description.split()
        if parts and not any(kw in desc_lower for kw in ["перевод", "пополнение", "внесение"]):
            merchant = " ".join(parts[:3])  # first few words are usually merchant

        # Extract MCC
        mcc = None
        mcc_match = re.search(r"MCC:\s*(\d{4})", description)
        if mcc_match:
            mcc = mcc_match.group(1)

        transactions.append({
            "date": date,
            "processed_date": date,
            "amount": amount,
            "currency": currency,
            "description": description,
            "raw_description": description,
            "category_hint": category_hint,
            "is_internal_transfer": is_internal,
            "external_id": None,
            "mcc": mcc,
            "merchant": merchant,
            "source_file": str(file_path),
            "account_number": None,
            "card_last4": card_last4,
            "status": status,
        })

    return transactions
