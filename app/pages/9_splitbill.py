"""Page: Split bill detection — find cases where user paid for group and got money back."""
import streamlit as st
import pandas as pd
import sys
from pathlib import Path
from datetime import timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))
from database import init_db, SessionLocal, Transaction, Category
from sqlalchemy import func
from collections import defaultdict

init_db()
st.title("Общие счета (split bill)")

st.caption(
    "Автоматический поиск ситуаций, когда вы рассчитались за всех, "
    "а потом получили возвраты от друзей."
)

session = SessionLocal()

txs = session.query(Transaction).filter(
    Transaction.is_internal_transfer == False,
).order_by(Transaction.date).all()

if not txs:
    st.info("Нет транзакций для анализа.")
    session.close()
    st.stop()

# Group by date
by_date = defaultdict(list)
for t in txs:
    by_date[t.date].append(t)

# Find split candidates
split_events = []
for d, day_txs in sorted(by_date.items()):
    # Large expenses (> 2000)
    expenses = [t for t in day_txs if t.amount < 0 and abs(t.amount) >= 2000]

    # Incoming transfers within same day and next day
    incomes = [t for t in day_txs if t.amount > 0 and 100 <= t.amount <= 20000]
    next_day = d + timedelta(days=1)
    if next_day in by_date:
        incomes += [t for t in by_date[next_day] if t.amount > 0 and 100 <= t.amount <= 20000]

    if not expenses or len(incomes) < 2:
        continue

    for exp in expenses:
        # Find incoming transfers that look like returns
        # (smaller than the expense, multiple people)
        returns = [i for i in incomes if i.amount < abs(exp.amount) * 0.7]

        if len(returns) >= 2:
            total_back = sum(i.amount for i in returns)
            # At least 30% returned = likely split
            if total_back >= abs(exp.amount) * 0.25:
                net_cost = abs(exp.amount) - total_back
                split_events.append({
                    "Дата": d,
                    "Расход": abs(exp.amount),
                    "Описание": (exp.description or "")[:50],
                    "Возвратов": len(returns),
                    "Вернули": round(total_back),
                    "Реальный расход": round(max(0, net_cost)),
                    "Экономия": round(total_back),
                })

if split_events:
    st.metric("Найдено событий", len(split_events))

    df = pd.DataFrame(split_events)
    total_saved = df["Экономия"].sum()
    total_real = df["Реальный расход"].sum()
    total_paid = df["Расход"].sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("Заплатили за всех", f"{total_paid:,.0f} \u20bd")
    col2.metric("Вернули", f"{total_saved:,.0f} \u20bd")
    col3.metric("Реальный расход", f"{total_real:,.0f} \u20bd")

    st.markdown("---")
    st.dataframe(
        df, use_container_width=True, hide_index=True,
        column_config={
            "Дата": st.column_config.DateColumn(format="DD.MM.YYYY"),
            "Расход": st.column_config.NumberColumn(format="%.0f \u20bd"),
            "Вернули": st.column_config.NumberColumn(format="%.0f \u20bd"),
            "Реальный расход": st.column_config.NumberColumn(format="%.0f \u20bd"),
            "Экономия": st.column_config.NumberColumn(format="%.0f \u20bd"),
        },
    )

    st.caption(
        "Логика: ищем дни, когда был крупный расход (>2000 \u20bd) "
        "и в тот же / следующий день пришло 2+ перевода, суммарно "
        "покрывающих 25%+ от расхода."
    )
else:
    st.info("Паттерны split bill не обнаружены.")

session.close()
