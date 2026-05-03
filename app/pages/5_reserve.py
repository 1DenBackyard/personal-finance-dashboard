"""Page: Emergency fund (multi-currency reserve)."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sys
import datetime as dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from database import init_db, SessionLocal, Reserve, Transaction
from currency import get_rates, convert_to_rub
from sqlalchemy import func

init_db()
st.title("Заначка на чёрный день")

session = SessionLocal()

CUR_SYMBOLS = {"RUB": "\u20bd", "USD": "$", "EUR": "\u20ac", "KZT": "\u20b8"}
CUR_FLAGS = {"RUB": "\U0001f1f7\U0001f1fa", "USD": "\U0001f1fa\U0001f1f8", "EUR": "\U0001f1ea\U0001f1fa", "KZT": "\U0001f1f0\U0001f1ff"}

# Fetch rates
with st.spinner("Курсы ЦБ РФ..."):
    rates = get_rates(session=session)

if rates:
    rate_cols = st.columns(3)
    for i, (cur, rate) in enumerate(rates.items()):
        sym = CUR_SYMBOLS.get(cur, cur)
        flag = CUR_FLAGS.get(cur, "")
        fmt = f"{rate:.2f}" if cur != "KZT" else f"{rate:.4f}"
        rate_cols[i].metric(f"{flag} {sym}1", f"{fmt} \u20bd")

st.markdown("---")

# Current balances
st.subheader("Балансы")

currencies = ["RUB", "USD", "EUR", "KZT"]
reserves = {c: session.query(Reserve).filter(Reserve.currency == c).first() for c in currencies}

cols = st.columns(5)
total_rub = 0.0

for i, cur in enumerate(currencies):
    r = reserves[cur]
    amount = r.amount if r else 0.0
    rub_eq = convert_to_rub(amount, cur, rates)
    total_rub += rub_eq
    sym = CUR_SYMBOLS[cur]
    flag = CUR_FLAGS[cur]

    with cols[i]:
        st.metric(
            f"{flag} {cur}",
            f"{sym}{amount:,.0f}",
            delta=f"= {rub_eq:,.0f} \u20bd" if cur != "RUB" else None,
        )

cols[4].metric("\U0001f4b0 Итого", f"{total_rub:,.0f} \u20bd")

# Composition chart
if total_rub > 0:
    reserve_data = []
    for cur in currencies:
        r = reserves[cur]
        amount = r.amount if r else 0.0
        if amount > 0:
            rub_eq = convert_to_rub(amount, cur, rates)
            sym = CUR_SYMBOLS[cur]
            reserve_data.append({"Валюта": f"{sym} {cur}", "Сумма": rub_eq})

    if reserve_data:
        df = pd.DataFrame(reserve_data)
        fig = go.Figure(data=[go.Pie(
            labels=df["Валюта"], values=df["Сумма"],
            hole=0.5,
            marker_colors=["#667eea", "#2ecc71", "#e74c3c", "#f39c12"],
            textinfo="percent+label",
        )])
        fig.update_layout(height=320, margin=dict(t=10, b=10), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

# Coverage
st.markdown("---")
st.subheader("Покрытие расходов")

avg_monthly = session.query(func.sum(Transaction.amount)).filter(
    Transaction.amount < 0,
    Transaction.is_internal_transfer == False,
).scalar()

total_months = session.query(
    func.count(func.distinct(func.strftime("%Y-%m", Transaction.date)))
).filter(
    Transaction.amount < 0,
    Transaction.is_internal_transfer == False,
).scalar() or 1

if avg_monthly and avg_monthly < 0:
    avg_abs = abs(avg_monthly) / total_months
    months_covered = total_rub / avg_abs if avg_abs > 0 else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Ср. расходы/мес.", f"{avg_abs:,.0f} \u20bd")
    col2.metric("Хватит на", f"{months_covered:.1f} мес.")

    target_months = 6
    target_rub = avg_abs * target_months
    pct = min(1.0, total_rub / target_rub) if target_rub > 0 else 0
    col3.metric(f"Цель ({target_months} мес.)", f"{target_rub:,.0f} \u20bd")
    st.progress(pct, text=f"Прогресс: {pct*100:.0f}%")
else:
    st.info("Импортируйте транзакции для расчёта покрытия.")

# Update form
st.markdown("---")
st.subheader("Обновить балансы")

with st.form("update_reserve"):
    cols = st.columns(4)
    new_amounts = {}
    for i, cur in enumerate(currencies):
        r = reserves[cur]
        sym = CUR_SYMBOLS[cur]
        with cols[i]:
            new_amounts[cur] = st.number_input(
                f"{sym} {cur}",
                value=float(r.amount if r else 0),
                step=100.0 if cur in ("RUB", "KZT") else 10.0,
            )

    if st.form_submit_button("Сохранить", type="primary"):
        for cur, amount in new_amounts.items():
            r = reserves[cur]
            if r:
                r.amount = amount
                r.updated_at = dt.datetime.now()
            else:
                session.add(Reserve(currency=cur, amount=amount, updated_at=dt.datetime.now()))
        session.commit()
        st.success("Обновлено!")
        st.rerun()

session.close()
