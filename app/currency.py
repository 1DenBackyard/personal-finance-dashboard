"""Currency exchange rates from CBR (Central Bank of Russia) and fallback APIs."""
import datetime as dt
import xml.etree.ElementTree as ET
import requests
from sqlalchemy.orm import Session
from database import CurrencyRate, SessionLocal


CBR_URL = "https://www.cbr.ru/scripts/XML_daily.asp"

# CBR currency codes
CBR_CODES = {
    "USD": "R01235",
    "EUR": "R01239",
    "KZT": "R01335",
}


def fetch_cbr_rates(date: dt.date | None = None) -> dict[str, float]:
    """
    Fetch exchange rates from CBR XML API.
    Returns dict like {"USD": 92.5, "EUR": 100.2, "KZT": 0.21}
    """
    params = {}
    if date:
        params["date_req"] = date.strftime("%d/%m/%Y")

    try:
        resp = requests.get(CBR_URL, params=params, timeout=10)
        resp.encoding = "windows-1251"
        root = ET.fromstring(resp.text)
    except Exception as e:
        print(f"CBR API error: {e}")
        return {}

    rates = {}
    for valute in root.findall("Valute"):
        char_code = valute.find("CharCode").text
        if char_code in ("USD", "EUR", "KZT"):
            nominal = int(valute.find("Nominal").text)
            value = float(valute.find("Value").text.replace(",", "."))
            rates[char_code] = value / nominal  # rate for 1 unit of currency

    return rates


def get_rates(date: dt.date | None = None, session: Session | None = None) -> dict[str, float]:
    """
    Get exchange rates, using cache first, then fetching from CBR.
    Always returns rates for USD, EUR, KZT in RUB.
    """
    if date is None:
        date = dt.date.today()

    own_session = session is None
    if own_session:
        session = SessionLocal()

    try:
        # Check cache
        cached = session.query(CurrencyRate).filter(
            CurrencyRate.date == date
        ).all()

        if len(cached) >= 3:  # we expect USD, EUR, KZT
            return {r.currency: r.rate_to_rub for r in cached}

        # Fetch from CBR
        rates = fetch_cbr_rates(date)

        if not rates:
            # Try previous day (weekends/holidays)
            for days_back in range(1, 5):
                rates = fetch_cbr_rates(date - dt.timedelta(days=days_back))
                if rates:
                    break

        if not rates:
            # Return last known rates from DB
            for currency in ("USD", "EUR", "KZT"):
                last = session.query(CurrencyRate).filter(
                    CurrencyRate.currency == currency
                ).order_by(CurrencyRate.date.desc()).first()
                if last:
                    rates[currency] = last.rate_to_rub
            return rates

        # Cache rates
        for currency, rate in rates.items():
            existing = session.query(CurrencyRate).filter(
                CurrencyRate.date == date,
                CurrencyRate.currency == currency
            ).first()
            if not existing:
                session.add(CurrencyRate(
                    date=date, currency=currency,
                    rate_to_rub=rate, source="cbr"
                ))
        session.commit()

        return rates

    finally:
        if own_session:
            session.close()


def convert_to_rub(amount: float, currency: str, rates: dict[str, float]) -> float:
    """Convert amount in given currency to RUB using provided rates."""
    if currency == "RUB":
        return amount
    rate = rates.get(currency)
    if rate is None:
        return amount  # fallback: return as-is
    return amount * rate


def get_total_reserve_rub(reserves: list[dict], rates: dict[str, float]) -> float:
    """Calculate total emergency fund value in RUB."""
    total = 0.0
    for r in reserves:
        total += convert_to_rub(r["amount"], r["currency"], rates)
    return total
