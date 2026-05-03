"""Page: Subscriptions and recurring expenses."""
import streamlit as st
import pandas as pd
import plotly.express as px
import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent))
from database import init_db, SessionLocal, Subscription, Category

init_db()
st.title("Подписки и регулярные траты")

session = SessionLocal()

# List subscriptions
subs = session.query(Subscription).filter(Subscription.is_active == True).order_by(Subscription.amount.desc()).all()

if subs:
    total_monthly = 0
    data = []
    for s in subs:
        if s.period == "monthly":
            monthly = s.amount
        elif s.period == "yearly":
            monthly = s.amount / 12
        else:
            monthly = s.amount * 4.33
        total_monthly += monthly

        data.append({
            "Название": s.name,
            "Сумма": s.amount,
            "Период": {"monthly": "мес.", "yearly": "год", "weekly": "нед."}.get(s.period, s.period),
            "В месяц": round(monthly),
            "В год": round(monthly * 12),
        })

    # Summary
    col1, col2 = st.columns(2)
    col1.metric("Всего подписок в месяц", f"{total_monthly:,.0f} \u20bd")
    col2.metric("Всего подписок в год", f"{total_monthly * 12:,.0f} \u20bd")

    st.markdown("---")

    # Chart
    df = pd.DataFrame(data)
    fig = px.bar(
        df.sort_values("В месяц"), x="В месяц", y="Название",
        orientation="h",
        text=df.sort_values("В месяц")["В месяц"].apply(lambda x: f"{x:,.0f} \u20bd"),
        color_discrete_sequence=["#667eea"],
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(
        height=max(300, len(data) * 35),
        margin=dict(t=10, b=10, l=10, r=60),
        xaxis_title="", yaxis_title="",
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Table
    st.dataframe(df, use_container_width=True, hide_index=True,
                 column_config={
                     "Сумма": st.column_config.NumberColumn(format="%.0f \u20bd"),
                     "В месяц": st.column_config.NumberColumn(format="%.0f \u20bd"),
                     "В год": st.column_config.NumberColumn(format="%.0f \u20bd"),
                 })

    # Deactivate
    st.markdown("---")
    sub_to_deactivate = st.selectbox("Отключить подписку", ["--"] + [s.name for s in subs])
    if sub_to_deactivate != "--" and st.button("Отключить"):
        sub = session.query(Subscription).filter(Subscription.name == sub_to_deactivate).first()
        if sub:
            sub.is_active = False
            session.commit()
            st.success(f"\"{sub_to_deactivate}\" отключена.")
            st.rerun()
else:
    st.info("Нет подписок.")

# Add new
st.markdown("---")
with st.expander("Добавить подписку"):
    with st.form("new_sub"):
        col1, col2, col3 = st.columns(3)
        with col1:
            name = st.text_input("Название")
        with col2:
            amount = st.number_input("Сумма", min_value=0.0, step=100.0)
        with col3:
            period = st.selectbox("Период", ["monthly", "yearly", "weekly"],
                                  format_func=lambda x: {"monthly": "Мес.", "yearly": "Год", "weekly": "Нед."}[x])

        if st.form_submit_button("Добавить"):
            if name and amount > 0:
                cat = session.query(Category).filter(Category.name == "Подписки").first()
                session.add(Subscription(
                    name=name, amount=amount, currency="RUB",
                    period=period, category_id=cat.id if cat else None,
                ))
                session.commit()
                st.success(f"\"{name}\" добавлена!")
                st.rerun()

session.close()
