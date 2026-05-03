"""Main Streamlit application — Financial Dashboard."""
import streamlit as st
import sys
import datetime as dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from database import init_db, SessionLocal, Transaction, Reserve, Category
from currency import get_rates, convert_to_rub
from sqlalchemy import func

init_db()

st.set_page_config(
    page_title="Финансы",
    page_icon="\U0001f4b0",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Custom CSS ---
st.markdown("""
<style>
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    }
    [data-testid="stSidebar"] * {
        color: #e0e0e0 !important;
    }
    [data-testid="stSidebar"] .stSelectbox label,
    [data-testid="stSidebar"] .stRadio label {
        color: #a0c4ff !important;
    }

    /* Metric cards */
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #667eea11 0%, #764ba211 100%);
        border: 1px solid #667eea33;
        border-radius: 12px;
        padding: 16px;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.4rem !important;
        font-weight: 700 !important;
    }

    /* Headers */
    h1 {
        background: linear-gradient(90deg, #667eea, #764ba2);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800 !important;
    }

    /* Progress bars */
    .stProgress > div > div {
        background: linear-gradient(90deg, #667eea, #764ba2) !important;
    }

    /* Dataframe */
    .stDataFrame {
        border-radius: 12px;
        overflow: hidden;
    }

    /* Buttons */
    .stButton > button[kind="primary"] {
        background: linear-gradient(90deg, #667eea, #764ba2) !important;
        border: none !important;
        border-radius: 8px !important;
    }

    /* Info boxes */
    div[data-testid="stAlert"] {
        border-radius: 12px;
    }

    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        padding: 8px 16px;
    }
</style>
""", unsafe_allow_html=True)

# --- Sidebar ---
st.sidebar.markdown("## \U0001f4b0 Финансы")
st.sidebar.markdown("---")
st.sidebar.caption("Навигация по разделам через страницы выше")

# --- Main page ---
st.title("Обзор финансов")

session = SessionLocal()
today = dt.date.today()
first_of_month = today.replace(day=1)

# Metrics row 1
col1, col2, col3, col4 = st.columns(4)

total_tx = session.query(func.count(Transaction.id)).filter(
    Transaction.is_internal_transfer == False
).scalar() or 0

cash_cat = session.query(Category).filter(Category.name == "Снятие наличных").first()
_exp_filters = [
    Transaction.date >= first_of_month,
    Transaction.amount < 0,
    Transaction.is_internal_transfer == False,
]
if cash_cat:
    _exp_filters.append(Transaction.category_id != cash_cat.id)

month_expenses = session.query(func.sum(Transaction.amount)).filter(
    *_exp_filters
).scalar() or 0

month_income = session.query(func.sum(Transaction.amount)).filter(
    Transaction.date >= first_of_month,
    Transaction.amount > 0,
    Transaction.is_internal_transfer == False,
).scalar() or 0

balance = month_income + month_expenses

# Previous month for delta
prev_first = (first_of_month - dt.timedelta(days=1)).replace(day=1)
_prev_filters = [
    Transaction.date >= prev_first,
    Transaction.date < first_of_month,
    Transaction.amount < 0,
    Transaction.is_internal_transfer == False,
]
if cash_cat:
    _prev_filters.append(Transaction.category_id != cash_cat.id)
prev_expenses = session.query(func.sum(Transaction.amount)).filter(
    *_prev_filters
).scalar() or 0

col1.metric("Транзакций", f"{total_tx:,}")
col2.metric(
    "Расходы (мес.)",
    f"{abs(month_expenses):,.0f} \u20bd",
    delta=f"{abs(month_expenses) - abs(prev_expenses):+,.0f} \u20bd" if prev_expenses else None,
    delta_color="inverse",
)
col3.metric("Доходы (мес.)", f"{month_income:,.0f} \u20bd")
col4.metric(
    "Баланс",
    f"{balance:+,.0f} \u20bd",
    delta="профицит" if balance > 0 else "дефицит",
    delta_color="normal" if balance > 0 else "inverse",
)

# Reserve summary
st.markdown("---")
reserves = session.query(Reserve).all()
if reserves:
    rates = get_rates(session=session)
    cur_symbols = {"RUB": "\u20bd", "USD": "$", "EUR": "\u20ac", "KZT": "\u20b8"}

    st.subheader("Заначка")
    cols = st.columns(len(reserves) + 1)
    total_rub = 0
    for i, r in enumerate(reserves):
        sym = cur_symbols.get(r.currency, r.currency)
        rub_eq = convert_to_rub(r.amount, r.currency, rates)
        total_rub += rub_eq
        cols[i].metric(f"{sym} {r.currency}", f"{r.amount:,.0f}")
    cols[len(reserves)].metric("Итого", f"{total_rub:,.0f} \u20bd")

# Quick expense chart for current month
import plotly.express as px
import pandas as pd

st.markdown("---")

tab1, tab2 = st.tabs(["Расходы по категориям (месяц)", "Динамика по дням"])

with tab1:
    month_txs = session.query(
        Category.name, func.sum(Transaction.amount)
    ).join(Category).filter(
        Transaction.date >= first_of_month,
        Transaction.amount < 0,
        Transaction.is_internal_transfer == False,
    ).group_by(Category.name).all()

    if month_txs:
        df = pd.DataFrame(month_txs, columns=["Категория", "Сумма"])
        df["Сумма"] = df["Сумма"].abs()
        df = df.sort_values("Сумма", ascending=False)

        fig = px.pie(
            df, values="Сумма", names="Категория",
            hole=0.45,
            color_discrete_sequence=px.colors.qualitative.Set3,
        )
        fig.update_traces(textinfo="percent+label", textposition="outside")
        fig.update_layout(
            height=420,
            margin=dict(t=20, b=20, l=20, r=20),
            showlegend=False,
            font=dict(size=13),
        )
        st.plotly_chart(fig, use_container_width=True)

with tab2:
    daily = session.query(
        Transaction.date, func.sum(Transaction.amount)
    ).filter(
        Transaction.date >= first_of_month,
        Transaction.amount < 0,
        Transaction.is_internal_transfer == False,
    ).group_by(Transaction.date).all()

    if daily:
        df_d = pd.DataFrame(daily, columns=["Дата", "Сумма"])
        df_d["Сумма"] = df_d["Сумма"].abs()

        fig_d = px.bar(
            df_d, x="Дата", y="Сумма",
            color_discrete_sequence=["#667eea"],
        )
        fig_d.update_layout(
            height=350,
            margin=dict(t=20, b=20),
            xaxis_title="", yaxis_title="Расходы, \u20bd",
        )
        st.plotly_chart(fig_d, use_container_width=True)

session.close()
