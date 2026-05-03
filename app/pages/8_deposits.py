"""Page: Bank deposits management and calculator."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sys
import math
from pathlib import Path
from datetime import date, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))
from database import init_db, SessionLocal, Deposit

init_db()
st.title("Вклады")

session = SessionLocal()

# --- Add deposit ---
with st.expander("Добавить вклад"):
    with st.form("new_deposit"):
        col1, col2 = st.columns(2)
        with col1:
            bank = st.text_input("Банк", placeholder="Альфа-Банк")
            amount = st.number_input("Сумма", min_value=0.0, step=10000.0)
            rate = st.number_input("Ставка (% годовых)", min_value=0.0, max_value=50.0, step=0.1)
        with col2:
            name = st.text_input("Название", placeholder="Накопительный")
            currency = st.selectbox("Валюта", ["RUB", "USD", "EUR"], key="dep_cur")
            is_cap = st.checkbox("С капитализацией")

        col3, col4 = st.columns(2)
        with col3:
            start = st.date_input("Дата открытия", value=date.today())
        with col4:
            end = st.date_input("Дата закрытия", value=date.today() + timedelta(days=365))

        notes = st.text_input("Заметки", key="dep_notes")

        if st.form_submit_button("Добавить"):
            if bank and amount > 0 and rate > 0:
                session.add(Deposit(
                    bank=bank, name=name, amount=amount, currency=currency,
                    rate=rate, start_date=start, end_date=end,
                    is_capitalized=is_cap, notes=notes,
                ))
                session.commit()
                st.success("Вклад добавлен!")
                st.rerun()

# --- List deposits ---
deposits = session.query(Deposit).filter(Deposit.is_active == True).all()

if deposits:
    st.subheader("Активные вклады")

    for dep in deposits:
        days_total = (dep.end_date - dep.start_date).days if dep.end_date and dep.start_date else 365
        days_passed = (date.today() - dep.start_date).days if dep.start_date else 0
        days_left = max(0, days_total - days_passed)

        # Calculate expected return
        if dep.is_capitalized:
            # Monthly capitalization
            months = days_total / 30
            monthly_rate = dep.rate / 100 / 12
            final = dep.amount * (1 + monthly_rate) ** months
        else:
            final = dep.amount * (1 + dep.rate / 100 * days_total / 365)

        profit = final - dep.amount

        # Current accrued
        if dep.is_capitalized:
            months_passed = days_passed / 30
            monthly_rate = dep.rate / 100 / 12
            current_value = dep.amount * (1 + monthly_rate) ** months_passed
        else:
            current_value = dep.amount * (1 + dep.rate / 100 * days_passed / 365)

        current_profit = current_value - dep.amount

        st.markdown(f"### {dep.bank} — {dep.name or 'Вклад'}")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Сумма", f"{dep.amount:,.0f} {dep.currency}")
        col2.metric("Ставка", f"{dep.rate}%{'(кап.)' if dep.is_capitalized else ''}")
        col3.metric("Начислено", f"+{current_profit:,.0f} {dep.currency}")
        col4.metric("Итого при закрытии", f"{final:,.0f} {dep.currency}")

        progress = min(1.0, days_passed / days_total) if days_total > 0 else 0
        st.progress(progress, text=f"Осталось {days_left} дн. из {days_total}")

        # Monthly projection
        with st.expander("Помесячный прогноз"):
            projections = []
            for month in range(0, min(math.ceil(days_total / 30) + 1, 37)):
                m_date = dep.start_date + timedelta(days=30 * month) if dep.start_date else date.today()
                if dep.is_capitalized:
                    val = dep.amount * (1 + dep.rate / 100 / 12) ** month
                else:
                    val = dep.amount * (1 + dep.rate / 100 * month * 30 / 365)
                projections.append({
                    "Месяц": m_date.strftime("%Y-%m"),
                    "Сумма": round(val, 2),
                    "Прибыль": round(val - dep.amount, 2),
                })

            df_proj = pd.DataFrame(projections)
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_proj["Месяц"], y=df_proj["Сумма"],
                mode="lines+markers", name="Сумма",
                fill="tonexty", line=dict(color="#2ecc71"),
            ))
            fig.update_layout(height=300, margin=dict(t=20, b=20))
            st.plotly_chart(fig, use_container_width=True)

        # Close deposit
        if st.button(f"Закрыть вклад", key=f"close_{dep.id}"):
            dep.is_active = False
            session.commit()
            st.success("Вклад закрыт.")
            st.rerun()

        st.markdown("---")

    # Summary
    total_deposits = sum(d.amount for d in deposits if d.currency == "RUB")
    st.metric("Всего на вкладах (RUB)", f"{total_deposits:,.0f} R")
else:
    st.info("Нет активных вкладов. Добавьте первый вклад.")

# --- Deposit calculator ---
st.markdown("---")
st.subheader("Калькулятор вклада")

col1, col2, col3 = st.columns(3)
with col1:
    calc_amount = st.number_input("Сумма", value=500000.0, step=50000.0, key="calc_amt")
with col2:
    calc_rate = st.number_input("Ставка (%)", value=18.0, step=0.5, key="calc_rate")
with col3:
    calc_months = st.number_input("Срок (мес.)", value=12, min_value=1, max_value=60, key="calc_months")

calc_cap = st.checkbox("С капитализацией", key="calc_cap")

if calc_cap:
    monthly_rate = calc_rate / 100 / 12
    final = calc_amount * (1 + monthly_rate) ** calc_months
else:
    final = calc_amount * (1 + calc_rate / 100 * calc_months / 12)

profit = final - dep.amount if deposits else final - calc_amount
profit = final - calc_amount

col1, col2 = st.columns(2)
col1.metric("Итого", f"{final:,.0f} R")
col2.metric("Доход", f"+{profit:,.0f} R")

session.close()
