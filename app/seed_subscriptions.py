"""Seed known subscriptions into the database."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from database import init_db, SessionLocal, Subscription, Category

init_db()
session = SessionLocal()

# User's subscriptions
SUBS = [
    ("Tele2", 1220, "monthly", "tele2"),
    ("MTS", 860, "monthly", "мтс|mts"),
    ("Megafon", 890, "monthly", "мегафон|megafon"),
    ("ChatGPT", 2300, "monthly", "chatgpt|openai"),
    ("Cursor", 2600, "monthly", "cursor"),
    ("VPN Notebook", 390, "monthly", "vpn"),
    ("VPN", 150, "monthly", "vpn"),
    ("Яндекс Плюс", 399, "monthly", "yandex.*plus|яндекс.*плюс"),
    ("Окко", 299, "monthly", "okko|окко"),
    ("АльфаСмарт", 399, "monthly", "привилегий.*m|alfasmart|alfa.*smart"),
    ("HAPP", 89, "monthly", "happ"),
    ("F3", 350, "monthly", "f3"),
    ("Claude", 5000, "monthly", "claude|anthropic"),
]

# Check if already seeded
existing = session.query(Subscription).count()
if existing == 0:
    cat = session.query(Category).filter(Category.name == "Подписки").first()
    mob_cat = session.query(Category).filter(Category.name == "Мобильная связь").first()

    for name, amount, period, pattern in SUBS:
        is_mobile = name in ("Tele2", "MTS", "Megafon")
        session.add(Subscription(
            name=name,
            amount=amount,
            currency="RUB",
            period=period,
            category_id=mob_cat.id if is_mobile else cat.id,
            merchant_pattern=pattern,
        ))

    session.commit()
    print(f"Added {len(SUBS)} subscriptions")
else:
    print(f"Already have {existing} subscriptions, skipping")

session.close()
