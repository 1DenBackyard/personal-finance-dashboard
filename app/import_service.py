"""Service for importing bank statements into the database."""
import os
from sqlalchemy.orm import Session
from database import (
    SessionLocal, Transaction, Account, Category,
    OWN_PHONES, OWN_PHONE_FRAGMENTS, OWN_ACCOUNTS, init_db
)
from parsers import parse_alfa, parse_sber, parse_ozon
from categorizer import categorize_transaction


def detect_bank(file_path: str) -> str | None:
    """Detect which bank the file belongs to based on filename."""
    name = os.path.basename(file_path).lower()
    if "альфа" in name or "alfa" in name:
        return "alfa"
    elif "сбер" in name or "sber" in name:
        return "sber"
    elif "озон" in name or "ozon" in name:
        return "ozon"
    return None


def import_file(file_path: str, bank: str | None = None) -> dict:
    """
    Import a bank statement file into the database.

    Returns dict with stats: total, imported, skipped, internal
    """
    if bank is None:
        bank = detect_bank(file_path)
    if bank is None:
        return {"error": "Cannot detect bank. Name file with bank prefix."}

    # Parse file
    if bank == "alfa":
        raw_txs = parse_alfa(file_path, OWN_PHONE_FRAGMENTS, OWN_ACCOUNTS)
    elif bank == "sber":
        raw_txs = parse_sber(file_path, OWN_PHONES, OWN_ACCOUNTS)
    elif bank == "ozon":
        raw_txs = parse_ozon(file_path, OWN_PHONE_FRAGMENTS, OWN_ACCOUNTS)
    else:
        return {"error": f"Unknown bank: {bank}"}

    session = SessionLocal()
    try:
        # Load category map
        categories = {c.name: c.id for c in session.query(Category).all()}

        # Load accounts for matching
        accounts = session.query(Account).all()

        imported = 0
        skipped = 0
        internal_count = 0

        for tx in raw_txs:
            # Dedup: check if transaction already exists
            if tx.get("external_id"):
                existing = session.query(Transaction).filter(
                    Transaction.external_id == tx["external_id"],
                    Transaction.source_file.contains(bank)
                ).first()
                if existing:
                    skipped += 1
                    continue

            # Find matching account
            account_id = None
            for acc in accounts:
                if tx.get("account_number") and acc.account_number == tx["account_number"]:
                    account_id = acc.id
                    break
                if tx.get("card_last4") and acc.card_last4 == tx["card_last4"] and acc.bank.lower().startswith(bank[:3]):
                    account_id = acc.id
                    break

            # Categorize
            category_name = categorize_transaction(tx)
            category_id = categories.get(category_name)

            if tx["is_internal_transfer"]:
                internal_count += 1

            t = Transaction(
                date=tx["date"],
                processed_date=tx.get("processed_date"),
                amount=tx["amount"],
                currency=tx.get("currency", "RUB"),
                description=tx.get("description", ""),
                raw_description=tx.get("raw_description", ""),
                category_id=category_id,
                account_id=account_id,
                is_internal_transfer=tx["is_internal_transfer"],
                source_file=os.path.basename(file_path),
                external_id=tx.get("external_id"),
                mcc=tx.get("mcc"),
                merchant=tx.get("merchant"),
                status=tx.get("status", "processed"),
            )
            session.add(t)
            imported += 1

        session.commit()
        return {
            "total": len(raw_txs),
            "imported": imported,
            "skipped": skipped,
            "internal": internal_count,
        }
    finally:
        session.close()
