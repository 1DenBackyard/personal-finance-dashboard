"""Page: Analytics dashboards with charts."""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys
from pathlib import Path
from datetime import date, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))
from database import init_db, SessionLocal, Transaction, Category, Account
from sqlalchemy import func

init_db()
st.title("Аналитика расходов")

session = SessionLocal()

# Date range
col1, col2, col3 = st.columns([1, 1, 2])
with col1:
    min_date = session.query(func.min(Transaction.date)).scalar() or date.today()
    max_date = session.query(func.max(Transaction.date)).scalar() or date.today()
    date_from = st.date_input("С", value=max(min_date, max_date - timedelta(days=180)), key="an_from")
with col2:
    date_to = st.date_input("По", value=max_date, key="an_to")
with col3:
    exclude_cash = st.checkbox("Исключить снятие наличных", value=True)

# Categories to exclude
cash_cat = session.query(Category).filter(Category.name == "Снятие наличных").first()
exclude_ids = []
if exclude_cash and cash_cat:
    exclude_ids.append(cash_cat.id)

# Load data
query = session.query(Transaction).filter(
    Transaction.date >= date_from,
    Transaction.date <= date_to,
    Transaction.is_internal_transfer == False,
)
if exclude_ids:
    query = query.filter(~Transaction.category_id.in_(exclude_ids))

txs = query.all()

if not txs:
    st.info("Нет данных за выбранный период.")
    session.close()
    st.stop()

cat_map = {c.id: c.name for c in session.query(Category).all()}

df = pd.DataFrame([{
    "date": t.date,
    "amount": t.amount,
    "abs_amount": abs(t.amount),
    "category": cat_map.get(t.category_id, "???"),
    "month": t.date.strftime("%Y-%m"),
    "week": t.date.strftime("%Y-W%W"),
    "weekday": t.date.strftime("%A"),
    "weekday_n": t.date.weekday(),
    "description": (t.description or "")[:60],
} for t in txs])

expenses = df[df["amount"] < 0].copy()
incomes = df[df["amount"] > 0].copy()

COLORS = px.colors.qualitative.Pastel + px.colors.qualitative.Set3

# --- Summary metrics ---
num_days = max(1, (date_to - date_from).days)
num_months = max(1, expenses["month"].nunique()) if not expenses.empty else 1

col1, col2, col3, col4 = st.columns(4)
col1.metric("Расходы", f"{expenses['abs_amount'].sum():,.0f} \u20bd")
col2.metric("Доходы", f"{incomes['amount'].sum():,.0f} \u20bd")
col3.metric("Ср. расход/мес.", f"{expenses['abs_amount'].sum() / num_months:,.0f} \u20bd")
col4.metric("Ср. расход/день", f"{expenses['abs_amount'].sum() / num_days:,.0f} \u20bd")

st.markdown("---")

# --- Tabs ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "По категориям", "По месяцам", "Приход/Уход",
    "По дням недели", "Топ расходов", "Тренд"
])

with tab1:
    if not expenses.empty:
        by_cat = expenses.groupby("category")["abs_amount"].sum().reset_index()
        by_cat = by_cat.sort_values("abs_amount", ascending=False)
        by_cat["percent"] = (by_cat["abs_amount"] / by_cat["abs_amount"].sum() * 100).round(1)

        col1, col2 = st.columns([1, 1])
        with col1:
            fig = px.pie(
                by_cat, values="abs_amount", names="category",
                hole=0.5, color_discrete_sequence=COLORS,
            )
            fig.update_traces(textinfo="percent+label", textposition="outside", textfont_size=11)
            fig.update_layout(height=450, margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            fig_bar = px.bar(
                by_cat, x="abs_amount", y="category", orientation="h",
                text=by_cat.apply(lambda r: f"{r['abs_amount']:,.0f} \u20bd ({r['percent']}%)", axis=1),
                color_discrete_sequence=["#667eea"],
            )
            fig_bar.update_traces(textposition="outside")
            fig_bar.update_layout(
                height=450, margin=dict(t=10, b=10, l=10, r=60),
                xaxis_title="", yaxis_title="", yaxis=dict(autorange="reversed"), showlegend=False,
            )
            st.plotly_chart(fig_bar, use_container_width=True)

        # Treemap
        st.markdown("#### Карта расходов")
        fig_tree = px.treemap(
            by_cat, path=["category"], values="abs_amount",
            color="abs_amount", color_continuous_scale="Blues",
        )
        fig_tree.update_traces(textinfo="label+value+percent root")
        fig_tree.update_layout(height=400, margin=dict(t=10, b=10))
        st.plotly_chart(fig_tree, use_container_width=True)

with tab2:
    monthly = df.groupby("month").apply(
        lambda g: pd.Series({
            "Расходы": g[g["amount"] < 0]["amount"].sum(),
            "Доходы": g[g["amount"] > 0]["amount"].sum(),
        })
    ).reset_index()

    if not monthly.empty:
        monthly["Расходы"] = monthly["Расходы"].abs()
        monthly["Баланс"] = monthly["Доходы"] - monthly["Расходы"]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=monthly["month"], y=monthly["Доходы"], name="Доходы",
            marker_color="#2ecc71",
            text=monthly["Доходы"].apply(lambda x: f"{x:,.0f}"), textposition="outside",
        ))
        fig.add_trace(go.Bar(
            x=monthly["month"], y=monthly["Расходы"], name="Расходы",
            marker_color="#e74c3c",
            text=monthly["Расходы"].apply(lambda x: f"{x:,.0f}"), textposition="outside",
        ))
        fig.add_trace(go.Scatter(
            x=monthly["month"], y=monthly["Баланс"], name="Баланс",
            mode="lines+markers+text",
            line=dict(color="#3498db", width=3),
            text=monthly["Баланс"].apply(lambda x: f"{x:+,.0f}"), textposition="top center",
        ))
        fig.update_layout(
            barmode="group", height=450, margin=dict(t=30, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
            yaxis_title="\u20bd",
        )
        st.plotly_chart(fig, use_container_width=True)

        # Stacked
        st.markdown("#### Структура расходов по месяцам")
        if not expenses.empty:
            monthly_cat = expenses.groupby(["month", "category"])["abs_amount"].sum().reset_index()
            fig_stack = px.bar(
                monthly_cat, x="month", y="abs_amount", color="category",
                color_discrete_sequence=COLORS,
                labels={"abs_amount": "\u20bd", "month": "", "category": ""},
            )
            fig_stack.update_layout(barmode="stack", height=400, margin=dict(t=10, b=10),
                                    legend=dict(orientation="h", yanchor="bottom", y=1.02))
            st.plotly_chart(fig_stack, use_container_width=True)

with tab3:
    # Cashflow: incoming vs outgoing per month
    st.markdown("#### Денежный поток (приход / уход)")

    if not monthly.empty:
        # Waterfall-style
        fig_flow = go.Figure()
        fig_flow.add_trace(go.Scatter(
            x=monthly["month"], y=monthly["Доходы"],
            name="Приход", fill="tozeroy",
            mode="lines+markers", line=dict(color="#2ecc71", width=2),
            fillcolor="rgba(46,204,113,0.2)",
        ))
        fig_flow.add_trace(go.Scatter(
            x=monthly["month"], y=-monthly["Расходы"],
            name="Уход", fill="tozeroy",
            mode="lines+markers", line=dict(color="#e74c3c", width=2),
            fillcolor="rgba(231,76,60,0.2)",
        ))
        fig_flow.update_layout(
            height=400, margin=dict(t=20, b=20),
            yaxis_title="\u20bd",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        )
        st.plotly_chart(fig_flow, use_container_width=True)

    # Cumulative balance
    st.markdown("#### Накопительный баланс")
    if not monthly.empty:
        monthly_sorted = monthly.sort_values("month")
        monthly_sorted["Накоп. баланс"] = monthly_sorted["Баланс"].cumsum()

        fig_cum = go.Figure()
        fig_cum.add_trace(go.Scatter(
            x=monthly_sorted["month"], y=monthly_sorted["Накоп. баланс"],
            mode="lines+markers+text", fill="tozeroy",
            line=dict(color="#667eea", width=3),
            text=monthly_sorted["Накоп. баланс"].apply(lambda x: f"{x:+,.0f}"),
            textposition="top center",
            fillcolor="rgba(102,126,234,0.15)",
        ))
        fig_cum.add_hline(y=0, line_dash="dash", line_color="gray")
        fig_cum.update_layout(height=350, margin=dict(t=20, b=20), yaxis_title="\u20bd")
        st.plotly_chart(fig_cum, use_container_width=True)

    # Sankey: income sources -> expense categories
    st.markdown("#### Поток денег (откуда \u2192 куда)")
    if not expenses.empty and not incomes.empty:
        inc_cats = incomes.groupby("category")["amount"].sum().nlargest(5)
        exp_cats = expenses.groupby("category")["abs_amount"].sum().nlargest(8)

        labels = list(inc_cats.index) + list(exp_cats.index)
        source = []
        target = []
        values = []

        for i, (inc_name, inc_val) in enumerate(inc_cats.items()):
            for j, (exp_name, exp_val) in enumerate(exp_cats.items()):
                proportion = exp_val / expenses["abs_amount"].sum() * inc_val
                source.append(i)
                target.append(len(inc_cats) + j)
                values.append(round(proportion))

        fig_sankey = go.Figure(data=[go.Sankey(
            node=dict(
                pad=15, thickness=20,
                label=labels,
                color=["#2ecc71"] * len(inc_cats) + ["#e74c3c"] * len(exp_cats),
            ),
            link=dict(source=source, target=target, value=values,
                      color="rgba(102,126,234,0.15)"),
        )])
        fig_sankey.update_layout(height=400, margin=dict(t=20, b=20))
        st.plotly_chart(fig_sankey, use_container_width=True)

with tab4:
    if not expenses.empty:
        weekday_names = {0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"}
        expenses["day_name"] = expenses["weekday_n"].map(weekday_names)
        by_weekday = expenses.groupby(["weekday_n", "day_name"])["abs_amount"].agg(["sum", "mean", "count"]).reset_index()
        by_weekday = by_weekday.sort_values("weekday_n")

        fig_wd = go.Figure()
        fig_wd.add_trace(go.Bar(
            x=by_weekday["day_name"], y=by_weekday["mean"],
            name="Ср. расход", marker_color="#667eea",
            text=by_weekday["mean"].apply(lambda x: f"{x:,.0f}"), textposition="outside",
        ))
        fig_wd.add_trace(go.Scatter(
            x=by_weekday["day_name"], y=by_weekday["count"],
            name="Кол-во операций", yaxis="y2",
            mode="lines+markers", line=dict(color="#e74c3c", width=2),
        ))
        fig_wd.update_layout(
            height=400, margin=dict(t=30, b=20),
            yaxis=dict(title="Ср. расход, \u20bd"),
            yaxis2=dict(title="Операций", overlaying="y", side="right"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig_wd, use_container_width=True)

        # Heatmap: weekday x category
        st.markdown("#### Расходы по дням недели и категориям")
        top_cats = expenses.groupby("category")["abs_amount"].sum().nlargest(8).index
        heat_data = expenses[expenses["category"].isin(top_cats)].copy()
        heat_data["day_name"] = heat_data["weekday_n"].map(weekday_names)
        heat_pivot = heat_data.pivot_table(
            values="abs_amount", index="category", columns="day_name",
            aggfunc="mean", fill_value=0,
        )
        # Reorder columns
        day_order = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        heat_pivot = heat_pivot.reindex(columns=[d for d in day_order if d in heat_pivot.columns])

        fig_heat = px.imshow(
            heat_pivot, aspect="auto",
            color_continuous_scale="Blues",
            labels=dict(x="День", y="Категория", color="Ср. расход"),
        )
        fig_heat.update_layout(height=350, margin=dict(t=10, b=10))
        st.plotly_chart(fig_heat, use_container_width=True)

with tab5:
    if not expenses.empty:
        top = expenses.nlargest(30, "abs_amount")[["date", "abs_amount", "category", "description"]].copy()
        top.columns = ["Дата", "Сумма", "Категория", "Описание"]
        st.dataframe(
            top, use_container_width=True, hide_index=True, height=600,
            column_config={
                "Сумма": st.column_config.NumberColumn(format="%.0f \u20bd"),
                "Дата": st.column_config.DateColumn(format="DD.MM.YYYY"),
            },
        )

with tab6:
    if not expenses.empty:
        daily = expenses.groupby("date")["abs_amount"].sum().reset_index()
        daily.columns = ["Дата", "Сумма"]
        daily = daily.sort_values("Дата")
        daily["MA7"] = daily["Сумма"].rolling(7, min_periods=1).mean()
        daily["MA30"] = daily["Сумма"].rolling(30, min_periods=1).mean()

        fig_d = go.Figure()
        fig_d.add_trace(go.Bar(
            x=daily["Дата"], y=daily["Сумма"],
            name="Расходы", marker_color="#667eea", opacity=0.4,
        ))
        fig_d.add_trace(go.Scatter(
            x=daily["Дата"], y=daily["MA7"],
            name="Тренд 7 дн.", mode="lines",
            line=dict(color="#e74c3c", width=2),
        ))
        fig_d.add_trace(go.Scatter(
            x=daily["Дата"], y=daily["MA30"],
            name="Тренд 30 дн.", mode="lines",
            line=dict(color="#2ecc71", width=2, dash="dot"),
        ))
        fig_d.update_layout(
            height=400, margin=dict(t=20, b=20),
            yaxis_title="\u20bd",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig_d, use_container_width=True)

session.close()
