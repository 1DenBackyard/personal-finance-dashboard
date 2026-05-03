"""Page: Transaction list with filters."""
import streamlit as st
import pandas as pd
import sys
from pathlib import Path
from datetime import date, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))
from database import init_db, SessionLocal, Transaction, Category, Account
from sqlalchemy import func

init_db()
st.title("Транзакции")

session = SessionLocal()

# Filters
col1, col2, col3, col4 = st.columns(4)

with col1:
    min_date = session.query(func.min(Transaction.date)).scalar() or date.today()
    max_date = session.query(func.max(Transaction.date)).scalar() or date.today()
    date_from = st.date_input("С", value=max(min_date, max_date - timedelta(days=30)))

with col2:
    date_to = st.date_input("По", value=max_date)

with col3:
    categories = session.query(Category).order_by(Category.name).all()
    cat_names = ["Все"] + [c.name for c in categories]
    selected_cat = st.selectbox("Категория", cat_names)

with col4:
    accounts = session.query(Account).all()
    acc_names = ["Все"] + [f"{a.bank}" for a in accounts]
    selected_acc = st.selectbox("Банк", acc_names)

col5, col6, col7 = st.columns(3)
with col5:
    show_internal = st.checkbox("Внутренние переводы", value=False)
with col6:
    tx_type = st.selectbox("Тип", ["Все", "Расходы", "Доходы"])
with col7:
    search = st.text_input("Поиск", placeholder="описание...")

# Query
query = session.query(Transaction).filter(
    Transaction.date >= date_from,
    Transaction.date <= date_to,
)
if not show_internal:
    query = query.filter(Transaction.is_internal_transfer == False)
if selected_cat != "Все":
    cat = session.query(Category).filter(Category.name == selected_cat).first()
    if cat:
        query = query.filter(Transaction.category_id == cat.id)
if selected_acc != "Все":
    acc_idx = acc_names.index(selected_acc) - 1
    query = query.filter(Transaction.account_id == accounts[acc_idx].id)
if tx_type == "Расходы":
    query = query.filter(Transaction.amount < 0)
elif tx_type == "Доходы":
    query = query.filter(Transaction.amount > 0)

txs = query.order_by(Transaction.date.desc()).all()

if search:
    txs = [t for t in txs if search.lower() in (t.description or "").lower()]

if txs:
    cat_map = {c.id: c.name for c in categories}
    acc_map = {a.id: a.bank for a in accounts}

    data = [{
        "Дата": t.date,
        "Сумма": t.amount,
        "Категория": cat_map.get(t.category_id, "\u2014"),
        "Описание": (t.description or "")[:70],
        "Банк": acc_map.get(t.account_id, "\u2014"),
    } for t in txs]

    df = pd.DataFrame(data)
    total_exp = df[df["Сумма"] < 0]["Сумма"].sum()
    total_inc = df[df["Сумма"] > 0]["Сумма"].sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("Найдено", f"{len(df)}")
    col2.metric("Расходы", f"{abs(total_exp):,.0f} \u20bd")
    col3.metric("Доходы", f"{total_inc:,.0f} \u20bd")

    st.dataframe(
        df, use_container_width=True, height=500, hide_index=True,
        column_config={
            "Сумма": st.column_config.NumberColumn(format="%.0f \u20bd"),
            "Дата": st.column_config.DateColumn(format="DD.MM.YYYY"),
        },
    )

    # Bulk re-categorize
    st.markdown("---")
    with st.expander("Переназначить категорию"):
        search_desc = st.text_input("Поиск по описанию для переназначения", key="recat_search")
        if search_desc:
            matching = [t for t in txs if search_desc.lower() in (t.description or "").lower()]
            if matching:
                st.write(f"Найдено: {len(matching)}")
                new_cat = st.selectbox("Новая категория", [c.name for c in categories], key="new_cat")
                if st.button("Применить"):
                    cat_obj = session.query(Category).filter(Category.name == new_cat).first()
                    for t in matching:
                        t.category_id = cat_obj.id
                    session.commit()
                    st.success(f"Обновлено {len(matching)} транзакций")
                    st.rerun()
else:
    st.info("Нет транзакций.")

session.close()
