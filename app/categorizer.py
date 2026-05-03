"""Auto-categorization of transactions based on merchant, MCC, and bank category hints."""
import re

# Mapping from bank category names to unified categories
BANK_CATEGORY_MAP = {
    # Sber categories
    "кафе, рестораны, фастфуд": "Кафе и рестораны",
    "супермаркеты": "Продукты",
    "транспорт": "Транспорт",
    "такси и каршеринг": "Такси и каршеринг",
    "жкх, связь, интернет": "ЖКХ и связь",
    "товары для дома": "Товары для дома",
    "спорт и фитнес": "Спорт и фитнес",
    "аптеки": "Здоровье и аптеки",
    "салоны красоты": "Красота",
    "маркетплейсы": "Маркетплейсы",
    "подписки": "Подписки",
    "автомобиль": "Автомобиль",
    "азс": "АЗС",
    "госплатежи и налоги": "Госплатежи и налоги",
    "услуги страхования": "Страхование",
    "хобби и развлечения": "Развлечения",
    "питомцы": "Питомцы",
    "переводы людям": "Переводы людям",
    "снятие наличных": "Снятие наличных",
    "табачные магазины": "Прочие расходы",
    "бизнес-услуги": "Прочие расходы",
    "бытовые услуги": "Прочие расходы",
    "прочее": "Прочие расходы",
    "переводы людям": "Переводы людям",
    # Alfa categories
    "транспорт": "Транспорт",
    "кафе и рестораны": "Кафе и рестораны",
    "прочие операции": None,  # needs further analysis
    "прочие расходы": "Прочие расходы",
    "мультимедиа": "Подписки",
    "финансовые операции": None,
    "телефон, интернет, тв": "ЖКХ и связь",
    "штрафы и налоги": "Госплатежи и налоги",
    "электроника": "Электроника",
    "красота": "Красота",
    "путешествия": "Путешествия",
    "снятие наличных": "Снятие наличных",
    "топливо": "АЗС",
    "одежда, обувь, аксессуары": "Одежда и обувь",
    # Ozon hints
    "кэшбек": "Кэшбек",
    "переводы от людей": "Переводы от людей",
}

# MCC code to category mapping
MCC_CATEGORY_MAP = {
    "4111": "Транспорт",       # Local transport
    "4121": "Такси и каршеринг",
    "4131": "Транспорт",       # Bus lines
    "5411": "Продукты",        # Grocery stores
    "5412": "Продукты",
    "5499": "Продукты",
    "5541": "АЗС",
    "5542": "АЗС",
    "5812": "Кафе и рестораны",
    "5813": "Кафе и рестораны",
    "5814": "Кафе и рестораны", # Fast food
    "5912": "Здоровье и аптеки",
    "5977": "Красота",
    "7832": "Развлечения",
    "7922": "Развлечения",
    "7941": "Спорт и фитнес",
    "7997": "Спорт и фитнес",
    "5661": "Одежда и обувь",
    "5651": "Одежда и обувь",
    "5691": "Одежда и обувь",
    "5311": "Маркетплейсы",
    "5331": "Маркетплейсы",
    "9390": "Госплатежи и налоги",  # Госуслуги
    "9311": "Госплатежи и налоги",
    "4900": "ЖКХ и связь",
    "4814": "ЖКХ и связь",
    "6011": "Снятие наличных",
    "6010": "Снятие наличных",
}

# Merchant keyword patterns for categorization
MERCHANT_PATTERNS = [
    # (regex_pattern, category_name)
    (r"(?i)pyaterochka|пятерочка|perekrestok|перекресток|magnit|магнит|dixy|дикси|vkusvill|вкусвилл|azbuka|лента|auchan|metro\s+c&c|spar", "Продукты"),
    (r"(?i)teremok|kfc|mcdonalds|burger\s*king|yakitoriya|sushi|шоколадница|coffee|starbucks|mosca|bufet|столовая|stolovaya|chaihona|ресторан", "Кафе и рестораны"),
    (r"(?i)mos\.transport|moscow\s*metro|мосгортранс|troika|тройка|ржд|aeroexpress", "Транспорт"),
    (r"(?i)yandex\.taxi|uber|citymobil|такси|bolt|wheely", "Такси и каршеринг"),
    (r"(?i)ozon|wildberries|yandex\.market|aliexpress|amazon|lamoda", "Маркетплейсы"),
    (r"(?i)apteka|аптека|eapteka|zdravcity|farmacia", "Здоровье и аптеки"),
    (r"(?i)lukoil|лукойл|gazprom|газпром|bp\s|shell|роснефть|azs|азс|neste|tnk", "АЗС"),
    (r"(?i)gosuslugi|госуслуги|nalog|налог|штраф|gibdd|гибдд", "Госплатежи и налоги"),
    (r"(?i)мтс|megafon|мегафон|beeline|билайн|tele2|теле2|мобильная\s+связь|rostelecom", "Мобильная связь"),
    (r"(?i)netflix|spotify|youtube|apple\.com|google\s+play|yandex\.plus|kinopoisk|okko|ivi\.ru|wink|подписка", "Подписки"),
    (r"(?i)sportivny|фитнес|fitness|world\s*class|gym|спортзал|x-fit", "Спорт и фитнес"),
    (r"(?i)парковка|parkovka|parking|автомойка|car\s*wash|шиномонтаж|автосервис|strojmarket", "Автомобиль"),
    (r"(?i)ikea|leroy\s*merlin|obi|castorama|hoff|товары\s+для\s+дома", "Товары для дома"),
    (r"(?i)dns|mvideo|м\.видео|citilink|ситилинк|eldorado|эльдорадо|re:store", "Электроника"),
    (r"(?i)кешбек|кэшбек|cashback|cash\s*back", "Кэшбек"),
    (r"(?i)зарплат|salary|аванс", "Зарплата"),
]


def categorize_transaction(tx: dict) -> str:
    """
    Determine unified category for a transaction.

    Priority:
    1. Internal transfers → "Внутренний перевод"
    2. MCC code mapping
    3. Bank category hint mapping
    4. Merchant pattern matching
    5. Amount-based heuristics
    6. Fallback to "Прочие расходы" / "Прочие доходы"
    """
    if tx.get("is_internal_transfer"):
        return "Внутренний перевод"

    # Try MCC code
    mcc = tx.get("mcc")
    if mcc and mcc in MCC_CATEGORY_MAP:
        return MCC_CATEGORY_MAP[mcc]

    # Try bank category hint
    hint = tx.get("category_hint")
    if hint:
        mapped = BANK_CATEGORY_MAP.get(hint.lower())
        if mapped:
            return mapped

    # Try merchant patterns on description
    description = tx.get("description", "") + " " + (tx.get("merchant") or "")
    for pattern, category in MERCHANT_PATTERNS:
        if re.search(pattern, description):
            return category

    # Fallback
    amount = tx.get("amount", 0)
    if amount > 0:
        return "Прочие доходы"
    return "Прочие расходы"


def detect_subscriptions(transactions: list[dict]) -> list[dict]:
    """
    Detect recurring subscriptions from transaction history.

    Returns list of suspected subscriptions with:
        merchant, amount, frequency, dates
    """
    # Group by merchant pattern (normalized)
    merchant_groups = {}
    for tx in transactions:
        if tx.get("is_internal_transfer"):
            continue
        merchant = tx.get("merchant") or ""
        desc = tx.get("description", "")
        # Normalize merchant name
        key = _normalize_merchant(merchant or desc)
        if not key:
            continue
        if key not in merchant_groups:
            merchant_groups[key] = []
        merchant_groups[key].append(tx)

    subscriptions = []
    for key, txs in merchant_groups.items():
        if len(txs) < 2:
            continue

        # Check if amounts are consistent (within 10% tolerance)
        amounts = [abs(t["amount"]) for t in txs]
        avg_amount = sum(amounts) / len(amounts)
        if avg_amount == 0:
            continue
        consistent = all(abs(a - avg_amount) / avg_amount < 0.1 for a in amounts)

        if consistent and len(txs) >= 2:
            # Calculate average interval
            dates = sorted([t["date"] for t in txs])
            if len(dates) >= 2:
                intervals = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
                avg_interval = sum(intervals) / len(intervals)

                if 25 <= avg_interval <= 35:
                    period = "monthly"
                elif 350 <= avg_interval <= 380:
                    period = "yearly"
                elif 6 <= avg_interval <= 8:
                    period = "weekly"
                else:
                    continue  # irregular

                subscriptions.append({
                    "merchant": key,
                    "amount": round(avg_amount, 2),
                    "period": period,
                    "count": len(txs),
                    "last_date": max(dates),
                    "sample_description": txs[0]["description"][:100],
                })

    return subscriptions


def _normalize_merchant(text: str) -> str:
    """Normalize merchant name for grouping."""
    text = text.lower().strip()
    # Remove common suffixes and noise
    text = re.sub(r"\s+(moscow|moskva|ru|rus|saint-petersburg|sankt-peterbu)\b.*", "", text)
    text = re.sub(r"\s+\d+$", "", text)  # trailing numbers
    text = re.sub(r"\s+", " ", text).strip()
    # Take first meaningful words
    words = text.split()[:3]
    return " ".join(words) if words else ""
