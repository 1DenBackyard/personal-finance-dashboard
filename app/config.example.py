"""
Personal configuration. Copy this file to config.py and fill in your data.
config.py is gitignored — never commit your real numbers.
"""

# Owner name fragments (lowercase) for detecting self-transfers in bank statements
# Sber and other banks show recipient name in transfer descriptions.
# Add variations: short form, full name, etc.
OWN_NAME_PATTERNS = [
    # "ivanov i",
    # "иван иванович и",
    # "иванов иван",
]

# Your phone numbers (used for SBP self-transfer detection)
# Both formats are checked: +7XXXXXXXXXX and various spacings
OWN_PHONES = [
    # "+79991234567",
]

# Your bank account numbers (20 digits) for internal transfer detection
OWN_ACCOUNTS = [
    # "40817810XXXXXXXXXXXX",  # Bank A current
    # "40817810XXXXXXXXXXXX",  # Bank A salary
    # "40817810XXXXXXXXXXXX",  # Bank B
]

# Default accounts seeded into DB on first run
# (bank, name, account_number, card_last4, currency)
DEFAULT_ACCOUNTS = [
    # ("Альфа-Банк", "Текущий счёт", "40817810XXXXXXXXXXXX", "1234", "RUB"),
    # ("Сбербанк",   "Дебетовая карта", None,                "5678", "RUB"),
    # ("Озон Банк",  "Дебетовая карта", "40817810XXXXXXXXXXXX", "9012", "RUB"),
]

# Map account_number -> default Ozon-like accounts when parsed file lacks it
# (e.g. Ozon PDF — fixed account)
OZON_ACCOUNT_NUMBER = ""  # "40817810XXXXXXXXXXXX"
OZON_CARD_LAST4 = ""      # "1234"
