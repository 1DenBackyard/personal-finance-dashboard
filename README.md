# Финансовый дашборд

Персональная система учёта финансов: импорт банковских выгрузок, аналитика расходов/доходов, мультивалютная заначка, финансовые цели, вклады, AI-советник.

## Стек

- **Backend:** Python 3.13, SQLAlchemy, SQLite
- **UI:** Streamlit + Plotly
- **Парсеры:** pandas (XLSX), pdfplumber (PDF)
- **Курсы валют:** ЦБ РФ XML API
- **AI:** Anthropic / OpenAI-совместимые API (cloud.ru и др.)

## Поддерживаемые банки

- Альфа-Банк (XLSX)
- Сбербанк (XLSX)
- Озон Банк (PDF)

## Запуск

```bash
cd app
pip install -r requirements.txt
streamlit run app.py
```

UI откроется на http://localhost:8501

## Структура

```
app/
  app.py              # точка входа Streamlit
  database.py         # SQLAlchemy модели
  categorizer.py      # автокатегоризация
  currency.py         # курсы валют ЦБ РФ
  parsers/            # парсеры выгрузок
    alfa.py
    sber.py
    ozon.py
  pages/              # страницы UI
    01_overview.py    # обзор
    02_import.py      # импорт выгрузок
    03_transactions.py
    04_analytics.py
    05_reserves.py    # заначка
    06_goals.py       # цели
    07_subscriptions.py
    08_deposits.py
    09_planning.py
    10_ai_chat.py     # AI-советник
```

## Безопасность

Файл `.gitignore` исключает БД и выгрузки из репозитория. Не коммитьте финансовые данные.
