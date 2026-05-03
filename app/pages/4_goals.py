"""Page: Financial goals management."""
import streamlit as st
import plotly.graph_objects as go
import sys
from pathlib import Path
from datetime import date, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))
from database import init_db, SessionLocal, Goal

init_db()
st.title("Финансовые цели")

CUR_SYM = {"RUB": "\u20bd", "USD": "$", "EUR": "\u20ac", "KZT": "\u20b8"}

# --- Add new goal (always visible at top) ---
with st.expander("Добавить цель", expanded=False):
    with st.form("new_goal"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Название", placeholder="Машина")
            target = st.number_input("Целевая сумма", min_value=0.0, step=10000.0, value=0.0)
            currency = st.selectbox("Валюта", ["RUB", "USD", "EUR", "KZT"])
        with col2:
            current = st.number_input("Накоплено", min_value=0.0, step=1000.0, value=0.0)
            offset = st.number_input("Зачёт (напр. продажа)", min_value=0.0, step=10000.0, value=0.0)
            offset_desc = st.text_input("Описание зачёта", placeholder="Продажа текущей")
        deadline = st.date_input("Дедлайн", value=date.today() + timedelta(days=365))

        submitted = st.form_submit_button("Создать", type="primary")
        if submitted:
            if name and target > 0:
                s = SessionLocal()
                try:
                    s.add(Goal(
                        name=name, target_amount=target, current_amount=current,
                        currency=currency, deadline=deadline,
                        offset_amount=offset, offset_description=offset_desc,
                    ))
                    s.commit()
                    st.success(f"\"{name}\" создана!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка: {e}")
                finally:
                    s.close()
            else:
                st.warning("Заполните название и целевую сумму > 0.")

st.markdown("---")

# --- Display goals ---
session = SessionLocal()
goals = session.query(Goal).filter(Goal.is_active == True).all()

if not goals:
    st.info("Нет активных целей. Добавьте первую цель выше.")
else:
    for goal in goals:
        remaining = max(0, goal.target_amount - goal.current_amount - goal.offset_amount)
        total_have = goal.current_amount + goal.offset_amount
        progress = min(1.0, total_have / goal.target_amount) if goal.target_amount > 0 else 0
        sym = CUR_SYM.get(goal.currency, goal.currency)

        st.markdown(f"### {goal.name}")

        # Progress visualization
        fig = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=total_have,
            number={"prefix": sym, "valueformat": ",.0f"},
            delta={"reference": goal.target_amount, "valueformat": ",.0f", "prefix": sym},
            gauge={
                "axis": {"range": [0, goal.target_amount], "tickformat": ",.0f"},
                "bar": {"color": "#667eea"},
                "steps": [
                    {"range": [0, goal.current_amount], "color": "#667eea33"},
                    {"range": [goal.current_amount, total_have], "color": "#2ecc7133"},
                ],
                "threshold": {
                    "line": {"color": "#e74c3c", "width": 3},
                    "thickness": 0.8,
                    "value": goal.target_amount,
                },
            },
        ))
        fig.update_layout(height=250, margin=dict(t=40, b=10))
        st.plotly_chart(fig, use_container_width=True)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Цель", f"{sym}{goal.target_amount:,.0f}")
        col2.metric("Накоплено", f"{sym}{goal.current_amount:,.0f}")
        if goal.offset_amount > 0:
            col3.metric(goal.offset_description or "Зачёт", f"{sym}{goal.offset_amount:,.0f}")
        col4.metric("Осталось", f"{sym}{remaining:,.0f}")

        if goal.deadline:
            days_left = (goal.deadline - date.today()).days
            if days_left > 0 and remaining > 0:
                monthly = remaining / max(1, days_left / 30)
                st.caption(f"До дедлайна {days_left} дн. | Нужно {sym}{monthly:,.0f}/мес.")
            elif remaining <= 0:
                st.success("Цель достигнута!")

        with st.expander("Редактировать"):
            col1, col2, col3 = st.columns(3)
            with col1:
                new_cur = st.number_input("Накоплено", value=float(goal.current_amount),
                                          step=1000.0, key=f"c_{goal.id}")
            with col2:
                new_off = st.number_input("Зачёт", value=float(goal.offset_amount),
                                          step=1000.0, key=f"o_{goal.id}")
            with col3:
                new_tgt = st.number_input("Цель", value=float(goal.target_amount),
                                          step=10000.0, key=f"t_{goal.id}")

            c1, c2 = st.columns(2)
            if c1.button("Сохранить", key=f"s_{goal.id}"):
                goal.current_amount = new_cur
                goal.offset_amount = new_off
                goal.target_amount = new_tgt
                session.commit()
                st.rerun()
            if c2.button("Архивировать", key=f"a_{goal.id}"):
                goal.is_active = False
                session.commit()
                st.rerun()

        st.markdown("---")

session.close()
