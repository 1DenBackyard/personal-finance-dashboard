"""Database models and initialization."""
import datetime as dt
from pathlib import Path
from sqlalchemy import (
    create_engine, Column, Integer, Float, String, Date, DateTime,
    Boolean, ForeignKey, Text, Enum as SAEnum
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DB_PATH = Path(__file__).parent / "finance.db"
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Account(Base):
    """Bank account / card."""
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True)
    bank = Column(String, nullable=False)          # Альфа, Сбер, Озон
    name = Column(String, nullable=False)           # "Текущий", "Зарплатный"
    account_number = Column(String, unique=True)    # 40817...
    card_last4 = Column(String)                     # last 4 digits of card
    currency = Column(String, default="RUB")
    is_active = Column(Boolean, default=True)
    transactions = relationship("Transaction", back_populates="account")


class Category(Base):
    """Unified expense/income category."""
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    icon = Column(String)
    is_income = Column(Boolean, default=False)
    parent_id = Column(Integer, ForeignKey("categories.id"))


class Transaction(Base):
    """Single financial transaction."""
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    processed_date = Column(Date)
    amount = Column(Float, nullable=False)          # positive=income, negative=expense
    currency = Column(String, default="RUB")
    description = Column(Text)
    raw_description = Column(Text)                  # original from bank
    category_id = Column(Integer, ForeignKey("categories.id"))
    category = relationship("Category")
    account_id = Column(Integer, ForeignKey("accounts.id"))
    account = relationship("Account", back_populates="transactions")
    is_internal_transfer = Column(Boolean, default=False)
    transfer_pair_id = Column(Integer, ForeignKey("transactions.id"))
    source_file = Column(String)                    # which import file
    external_id = Column(String)                    # bank's doc number for dedup
    mcc = Column(String)
    merchant = Column(String)
    status = Column(String, default="processed")    # processed / pending


class Goal(Base):
    """Financial goal."""
    __tablename__ = "goals"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    target_amount = Column(Float, nullable=False)
    current_amount = Column(Float, default=0)
    currency = Column(String, default="RUB")
    deadline = Column(Date)
    is_active = Column(Boolean, default=True)
    notes = Column(Text)
    # For goals like "car": offset_amount = sale price of current car
    offset_amount = Column(Float, default=0)
    offset_description = Column(String)             # "Продажа текущей машины"


class Reserve(Base):
    """Emergency fund balance per currency."""
    __tablename__ = "reserves"
    id = Column(Integer, primary_key=True)
    currency = Column(String, nullable=False)       # RUB, USD, EUR, KZT
    amount = Column(Float, nullable=False, default=0)
    updated_at = Column(DateTime, default=dt.datetime.now)
    notes = Column(Text)


class CurrencyRate(Base):
    """Cached currency exchange rates."""
    __tablename__ = "currency_rates"
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    currency = Column(String, nullable=False)       # USD, EUR, KZT
    rate_to_rub = Column(Float, nullable=False)     # 1 USD = X RUB
    source = Column(String, default="cbr")


class Subscription(Base):
    """Recurring subscription / regular expense."""
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="RUB")
    period = Column(String, default="monthly")      # monthly, yearly, weekly
    category_id = Column(Integer, ForeignKey("categories.id"))
    category = relationship("Category")
    next_charge_date = Column(Date)
    is_active = Column(Boolean, default=True)
    merchant_pattern = Column(String)               # regex to auto-detect in imports
    notes = Column(Text)


class Income(Base):
    """Regular income source."""
    __tablename__ = "incomes"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)           # "Зарплата", "Фриланс"
    amount = Column(Float, nullable=False)
    currency = Column(String, default="RUB")
    period = Column(String, default="monthly")
    is_active = Column(Boolean, default=True)
    next_date = Column(Date)
    notes = Column(Text)


class Deposit(Base):
    """Bank deposit / savings account."""
    __tablename__ = "deposits"
    id = Column(Integer, primary_key=True)
    bank = Column(String, nullable=False)
    name = Column(String)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="RUB")
    rate = Column(Float, nullable=False)            # annual % rate
    start_date = Column(Date)
    end_date = Column(Date)
    is_capitalized = Column(Boolean, default=False) # compound interest
    is_active = Column(Boolean, default=True)
    notes = Column(Text)


class PlannedExpense(Base):
    """Large planned future expense."""
    __tablename__ = "planned_expenses"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="RUB")
    expected_date = Column(Date)
    is_completed = Column(Boolean, default=False)
    notes = Column(Text)


# Personal data is loaded from config.py (gitignored).
# Copy config.example.py to config.py and fill in your numbers.
try:
    from config import OWN_PHONES, OWN_ACCOUNTS, DEFAULT_ACCOUNTS
except ImportError:
    OWN_PHONES = []
    OWN_ACCOUNTS = []
    DEFAULT_ACCOUNTS = []

OWN_PHONE_FRAGMENTS = [p.lstrip("+7") for p in OWN_PHONES]


def init_db():
    """Create all tables and seed default categories."""
    Base.metadata.create_all(engine)
    session = SessionLocal()

    # Seed categories if empty
    if session.query(Category).count() == 0:
        default_categories = [
            # Расходы
            ("Продукты", False), ("Кафе и рестораны", False),
            ("Транспорт", False), ("Такси и каршеринг", False),
            ("ЖКХ и связь", False), ("Мобильная связь", False),
            ("Подписки", False), ("Одежда и обувь", False),
            ("Здоровье и аптеки", False), ("Спорт и фитнес", False),
            ("Красота", False), ("Товары для дома", False),
            ("Электроника", False), ("Развлечения", False),
            ("Образование", False), ("Путешествия", False),
            ("Автомобиль", False), ("АЗС", False),
            ("Госплатежи и налоги", False), ("Страхование", False),
            ("Маркетплейсы", False), ("Питомцы", False),
            ("Переводы людям", False), ("Снятие наличных", False),
            ("Прочие расходы", False),
            # Доходы
            ("Зарплата", True), ("Фриланс", True),
            ("Кэшбек", True), ("Переводы от людей", True),
            ("Проценты по вкладам", True), ("Прочие доходы", True),
            # Служебные
            ("Внутренний перевод", False),
        ]
        for name, is_income in default_categories:
            session.add(Category(name=name, is_income=is_income))

        # Seed accounts from config
        for bank, name, acc_num, card, cur in DEFAULT_ACCOUNTS:
            session.add(Account(
                bank=bank, name=name, account_number=acc_num,
                card_last4=card, currency=cur
            ))

        session.commit()
    session.close()
