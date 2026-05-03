"""Parser for Ozon Bank PDF statements."""
import re
import pdfplumber
from datetime import datetime

try:
    from config import OZON_ACCOUNT_NUMBER, OZON_CARD_LAST4, OWN_NAME_PATTERNS
except ImportError:
    OZON_ACCOUNT_NUMBER = ""
    OZON_CARD_LAST4 = ""
    OWN_NAME_PATTERNS = []


def _parse_amount(amount_str: str) -> float:
    """Parse amount like '- 1 500.00 ₽' or '+ 439.00 ₽'."""
    s = amount_str.replace("\u20bd", "").replace("₽", "").replace("\xa0", "").strip()
    s = re.sub(r"\s+", "", s)
    try:
        return float(s)
    except ValueError:
        return 0.0


def _detect_internal_transfer(description: str, own_phones: list) -> bool:
    """Detect internal transfers in Ozon descriptions."""
    desc_lower = description.lower()

    # Cashback is income, not an internal transfer
    if "кешбек" in desc_lower or "кэшбек" in desc_lower or "cashback" in desc_lower:
        return False

    if "перевод собственных средств" in desc_lower:
        return True

    # SBP transfers from own phones
    for phone in own_phones:
        phone_clean = phone.lstrip("+")
        if phone_clean in description.replace(" ", ""):
            if "перевод" in desc_lower:
                return True

    # Check for own name pattern in "Отправитель: ..." / "Получатель: ..."
    sender_match = re.search(r"(?:отправитель|получатель):\s*([^.]+)", desc_lower)
    if sender_match:
        recipient = sender_match.group(1).strip()
        for pattern in OWN_NAME_PATTERNS:
            if pattern in recipient:
                return True

    return False


def parse_ozon(file_path: str, own_phones: list, own_accounts: list) -> list[dict]:
    """
    Parse Ozon Bank PDF statement.

    PDF structure per page:
      - Header row: Дата операции | Документ | Назначение платежа | Сумма (₽) | Сумма (валюта)
      - Transactions span multiple lines, grouped by date + doc number
    """
    pdf = pdfplumber.open(file_path)
    transactions = []
    seen_ids = set()

    for page in pdf.pages:
        text = page.extract_text()
        if not text:
            continue

        lines = text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Try to match a transaction start line
            # Pattern: date time doc_number description [+/-] amount ₽ [+/-] amount ₽
            # Date format: DD.MM.YYYY
            date_match = re.match(r"(\d{2}\.\d{2}\.\d{4})\s+", line)
            if not date_match:
                i += 1
                continue

            date_str = date_match.group(1)
            try:
                date = datetime.strptime(date_str, "%d.%m.%Y").date()
            except ValueError:
                i += 1
                continue

            # Collect all text for this transaction (may span multiple lines)
            tx_text = line
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                # Stop if we hit a new date or header
                if re.match(r"\d{2}\.\d{2}\.\d{4}\s+", next_line):
                    break
                if next_line.startswith("Дата операции") or next_line.startswith("Сумма операции"):
                    break
                if next_line.startswith("Входящий остаток") or next_line.startswith("Исходящий остаток"):
                    break
                if next_line.startswith("Итого"):
                    break
                if not next_line:
                    j += 1
                    continue
                tx_text += " " + next_line
                j += 1
            i = j

            # Extract document number
            doc_match = re.search(r"(\d{10,})", tx_text)
            doc_id = doc_match.group(1) if doc_match else None

            # Dedup
            if doc_id and doc_id in seen_ids:
                continue
            if doc_id:
                seen_ids.add(doc_id)

            # Extract amounts — look for patterns like "+ 500.00 ₽" or "- 1 500.00 ₽"
            amount_matches = re.findall(r"([+-])\s*([\d\s]+\.\d{2})\s*₽", tx_text)
            if not amount_matches:
                # Try without ₽
                amount_matches = re.findall(r"([+-])\s*([\d\s]+\.\d{2})", tx_text)

            if not amount_matches:
                continue

            # First amount is in rubles
            sign = amount_matches[0][0]
            amt_str = amount_matches[0][1].replace(" ", "")
            try:
                amount = float(amt_str)
                if sign == "-":
                    amount = -amount
            except ValueError:
                continue

            # Build description (everything between doc_id and first amount)
            description = tx_text
            # Clean up the description
            description = re.sub(r"[+-]\s*[\d\s]+\.\d{2}\s*₽", "", description)
            description = re.sub(r"\d{2}\.\d{2}\.\d{4}", "", description, count=1)
            description = re.sub(r"\d{2}:\d{2}:\d{2}", "", description)
            if doc_id:
                description = description.replace(doc_id, "")
            description = re.sub(r"\s+", " ", description).strip()

            # Extract merchant from card operations
            merchant = None
            merchant_match = re.search(
                r"(?:карте\s+\d{4}\s+сумма\s+[\d.]+\s+в\s+)(.+?)(?:\s+\w{2}\s+дата|\s+RU\s+дата)",
                tx_text, re.IGNORECASE
            )
            if merchant_match:
                merchant = merchant_match.group(1).strip()

            # Extract MCC
            mcc = None
            mcc_match = re.search(r"MCC[:\s]*(\d{4})", tx_text)
            if mcc_match:
                mcc = mcc_match.group(1)

            is_internal = _detect_internal_transfer(tx_text, own_phones)

            # Determine category hint from description
            category_hint = None
            desc_lower = description.lower()
            if "кешбек" in desc_lower or "кэшбек" in desc_lower or "cashback" in desc_lower:
                category_hint = "Кэшбек"
            elif "перевод" in desc_lower and not is_internal:
                if amount > 0:
                    category_hint = "Переводы от людей"
                else:
                    category_hint = "Переводы людям"

            transactions.append({
                "date": date,
                "processed_date": date,
                "amount": amount,
                "currency": "RUB",
                "description": description,
                "raw_description": tx_text,
                "category_hint": category_hint,
                "is_internal_transfer": is_internal,
                "external_id": doc_id,
                "mcc": mcc,
                "merchant": merchant,
                "source_file": str(file_path),
                "account_number": OZON_ACCOUNT_NUMBER,
                "card_last4": OZON_CARD_LAST4,
                "status": "processed",
            })

    pdf.close()
    return transactions
