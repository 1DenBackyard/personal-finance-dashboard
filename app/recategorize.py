"""One-time script to recategorize all transactions with improved logic."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from database import init_db, SessionLocal, Transaction, Category
from categorizer import categorize_transaction

init_db()
session = SessionLocal()

cat_map = {c.name: c.id for c in session.query(Category).all()}

txs = session.query(Transaction).all()
updated = 0

for t in txs:
    tx_dict = {
        "is_internal_transfer": t.is_internal_transfer,
        "mcc": t.mcc,
        "category_hint": None,  # re-derive from description
        "description": t.description or "",
        "raw_description": t.raw_description or "",
        "merchant": t.merchant or "",
        "amount": t.amount,
    }

    # Get bank category hint from raw description for Sber
    if t.source_file and "сбер" in t.source_file.lower():
        # Sber has good categories, trust them
        continue

    new_cat = categorize_transaction(tx_dict)
    new_id = cat_map.get(new_cat)
    if new_id and new_id != t.category_id:
        old_cat = next((name for name, id in cat_map.items() if id == t.category_id), "?")
        if old_cat == "Прочие расходы" or old_cat == "Прочие доходы":
            t.category_id = new_id
            updated += 1

session.commit()
print(f"Updated {updated} transactions")
session.close()
