"""Page: Income tracking and forecasting."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sys
from pathlib import Path
from datetime import date, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))
from database import init_db, SessionLocal, Income, Transaction, PlannedExpense, Subscription, Category
from sqlalchemy import func

init_db()
st.title("Доходы и прогноз")

session = SessionLocal()

# --- Auto-detected cashback income ---
# Calculate average monthly cashback
cashback_cat = session.query(Category).filter(Category.name == "Кэшбек").first()
if cashback_cat:
    total_cashback = session.query(func.sum(Transaction.amount)).filter(
        Transaction.category_id == cashback_cat.id,
        Transaction.amount > 0,
    ).scalar() or 0

    cashback_months = session.query(
        func.count(func.distinct(func.strftime("%Y-%m", Transaction.date)))
    ).filter(
        Transaction.category_id == cashback_cat.id,
        Transaction.amount > 0,
    ).scalar() or 1

    avg_cashback = total_cashback / cashback_months

    # Add cashback as income source if not exists
    existing_cb = session.query(Income).filter(Income.name == "Кэшбек (авто)").first()
    if not existing_cb and avg_cashback > 0:
        session.add(Income(
            name="Кэшбек (авто)", amount=round(avg_cashback),
            period="monthly", notes="Автоматически рассчитано из истории"
        ))
        session.commit()

# --- Income sources ---
st.subheader("Источники дохода")

incomes = session.query(Income).filter(Income.is_active == True).all()

if incomes:
    total_monthly = 0
    data = []
    for inc in incomes:
        monthly = inc.amount if inc.period == "monthly" else inc.amount / 12
        total_monthly += monthly
        data.append({
            "Источник": inc.name,
            "Сумма": inc.amount,
            "Период": "мес." if inc.period == "monthly" else "год",
            "В месяц": round(monthly),
        })

    col1, col2 = st.columns(2)
    col1.metric("Итого доход/мес.", f"{total_monthly:,.0f} \u20bd")
    col2.metric("Итого доход/год", f"{total_monthly * 12:,.0f} \u20bd")

    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True, hide_index=True,
                 column_config={
                     "Сумма": st.column_config.NumberColumn(format="%.0f \u20bd"),
                     "В месяц": st.column_config.NumberColumn(format="%.0f \u20bd"),
                 })

with st.expander("Добавить источник дохода"):
    with st.form("new_income"):
        col1, col2, col3 = st.columns(3)
        with col1:
            name = st.text_input("Название", placeholder="Зарплата")
        with col2:
            amount = st.number_input("Сумма", min_value=0.0, step=5000.0)
        with col3:
            period = st.selectbox("Период", ["monthly", "yearly"],
                                  format_func=lambda x: {"monthly": "Мес.", "yearly": "Год"}[x])
        if st.form_submit_button("Добавить"):
            if name and amount > 0:
                session.add(Income(name=name, amount=amount, period=period))
                session.commit()
                st.success(f"\"{name}\" добавлен!")
                st.rerun()

# --- Planned expenses ---
st.markdown("---")
st.subheader("Крупные планируемые расходы")

planned = session.query(PlannedExpense).filter(
    PlannedExpense.is_completed == False
).order_by(PlannedExpense.expected_date).all()

if planned:
    for p in planned:
        days = (p.expected_date - date.today()).days if p.expected_date else None
        col1, col2, col3 = st.columns([3, 1, 1])
        col1.write(f"**{p.name}** \u2014 {p.amount:,.0f} \u20bd")
        if days is not None:
            col2.write(f"{'через ' + str(days) + ' дн.' if days > 0 else 'просрочено'}")
        if col3.button("Done", key=f"done_{p.id}"):
            p.is_completed = True
            session.commit()
            st.rerun()

with st.expander("Добавить планируемый расход"):
    with st.form("new_planned"):
        col1, col2, col3 = st.columns(3)
        with col1:
            pe_name = st.text_input("Название", placeholder="Отпуск")
        with col2:
            pe_amount = st.number_input("Сумма", min_value=0.0, step=5000.0, key="pe_a")
        with col3:
            pe_date = st.date_input("Дата", value=date.today() + timedelta(days=30), key="pe_d")
        if st.form_submit_button("Добавить"):
            if pe_name and pe_amount > 0:
                session.add(PlannedExpense(name=pe_name, amount=pe_amount, expected_date=pe_date))
                session.commit()
                st.success(f"\"{pe_name}\" добавлен!")
                st.rerun()

# --- Forecast ---
st.markdown("---")
st.subheader("Прогноз на 6 месяцев")

if incomes:
    # Real monthly expenses from history (excluding cash withdrawals)
    cash_cat = session.query(Category).filter(Category.name == "Снятие наличных").first()
    expense_filter = [
        Transaction.amount < 0,
        Transaction.is_internal_transfer == False,
    ]
    if cash_cat:
        expense_filter.append(Transaction.category_id != cash_cat.id)

    monthly_data = session.query(
        func.strftime("%Y-%m", Transaction.date),
        func.sum(Transaction.amount),
    ).filter(*expense_filter).group_by(func.strftime("%Y-%m", Transaction.date)).all()

    if monthly_data:
        real_months = {m: abs(s) for m, s in monthly_data}
        # Use median of last 4 months for better estimate
        recent_values = sorted(real_months.values())[-4:]
        avg_expense = sum(recent_values) / len(recent_values) if recent_values else 0

        # Subscriptions
        subs = session.query(Subscription).filter(Subscription.is_active == True).all()
        monthly_subs = sum(
            s.amount if s.period == "monthly"
            else s.amount / 12 if s.period == "yearly"
            else s.amount * 4.33
            for s in subs
        )

        months = []
        today = date.today()
        cumulative_free = 0

        for i in range(6):
            m = today + timedelta(days=30 * i)
            month_str = m.strftime("%Y-%m")

            income = total_monthly
            expense = avg_expense

            # Add planned expenses
            for p in planned:
                if p.expected_date and p.expected_date.strftime("%Y-%m") == month_str:
                    expense += p.amount

            free = income - expense
            cumulative_free += free

            months.append({
                "Месяц": month_str,
                "Доходы": round(income),
                "Расходы": round(expense),
                "Свободно": round(free),
                "Накопительно": round(cumulative_free),
            })

        df_forecast = pd.DataFrame(months)

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df_forecast["Месяц"], y=df_forecast["Доходы"],
            name="Доходы", marker_color="#2ecc71",
        ))
        fig.add_trace(go.Bar(
            x=df_forecast["Месяц"], y=df_forecast["Расходы"],
            name="Расходы", marker_color="#e74c3c",
        ))
        fig.add_trace(go.Scatter(
            x=df_forecast["Месяц"], y=df_forecast["Свободно"],
            name="Свободно", mode="lines+markers+text",
            line=dict(color="#3498db", width=3),
            text=df_forecast["Свободно"].apply(lambda x: f"{x:+,.0f}"),
            textposition="top center",
        ))
        fig.update_layout(
            barmode="group", height=420,
            margin=dict(t=30, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
            yaxis_title="\u20bd",
        )
        st.plotly_chart(fig, use_container_width=True)

        st.caption(f"Расчёт: средний расход за последние {len(recent_values)} мес. = {avg_expense:,.0f} \u20bd/мес.")

        st.dataframe(df_forecast, use_container_width=True, hide_index=True,
                     column_config={c: st.column_config.NumberColumn(format="%.0f \u20bd")
                                    for c in ["Доходы", "Расходы", "Свободно", "Накопительно"]})
    else:
        st.info("Нет данных о расходах для прогноза.")
else:
    st.info("Добавьте источники дохода.")

session.close()
