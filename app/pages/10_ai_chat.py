"""Page: AI Financial Advisor Chat."""
import streamlit as st
import pandas as pd
import json
import sys
import requests
from pathlib import Path
from datetime import date, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))
from database import init_db, SessionLocal, Transaction, Category, Reserve, Goal, Subscription, Income, Deposit
from currency import get_rates, convert_to_rub
from sqlalchemy import func

init_db()
st.title("AI Финансовый советник")

# --- Settings ---
with st.sidebar:
    st.markdown("### Настройки AI")
    api_endpoint = st.text_input(
        "API Base URL",
        value=st.session_state.get("ai_endpoint", "https://foundation-models.api.cloud.ru/v1"),
        help="Базовый URL API. /chat/completions добавится автоматически.",
        key="ai_endpoint_input",
    )
    api_key = st.text_input("API Key", type="password", key="ai_key")
    model = st.text_input("Модель", value=st.session_state.get("ai_model", "openai/gpt-oss-120b"), key="ai_model_input")

    if st.button("Сохранить настройки"):
        st.session_state["ai_endpoint"] = api_endpoint
        st.session_state["ai_model"] = model
        st.success("Сохранено")


def build_financial_context() -> str:
    """Build a summary of current financial state for the AI."""
    session = SessionLocal()
    try:
        # Monthly expenses by category
        cat_map = {c.id: c.name for c in session.query(Category).all()}

        monthly_data = session.query(
            func.strftime("%Y-%m", Transaction.date),
            func.sum(Transaction.amount),
        ).filter(
            Transaction.amount < 0,
            Transaction.is_internal_transfer == False,
        ).group_by(func.strftime("%Y-%m", Transaction.date)).all()

        monthly_expenses = {m: abs(s) for m, s in monthly_data}

        # Category breakdown (last 3 months)
        three_months_ago = date.today() - timedelta(days=90)
        cat_data = session.query(
            Category.name, func.sum(Transaction.amount), func.count(Transaction.id)
        ).join(Category).filter(
            Transaction.date >= three_months_ago,
            Transaction.amount < 0,
            Transaction.is_internal_transfer == False,
        ).group_by(Category.name).order_by(func.sum(Transaction.amount)).all()

        # Income
        incomes = session.query(Income).filter(Income.is_active == True).all()
        total_monthly_income = sum(
            i.amount if i.period == "monthly" else i.amount / 12
            for i in incomes
        )

        # Reserves
        reserves = session.query(Reserve).all()
        rates = get_rates(session=session)
        reserve_info = []
        total_reserve_rub = 0
        cur_sym = {"RUB": "\u20bd", "USD": "$", "EUR": "\u20ac", "KZT": "\u20b8"}
        for r in reserves:
            rub = convert_to_rub(r.amount, r.currency, rates)
            total_reserve_rub += rub
            reserve_info.append(f"  {cur_sym.get(r.currency, r.currency)}{r.amount:,.0f} ({rub:,.0f}\u20bd)")

        # Goals
        goals = session.query(Goal).filter(Goal.is_active == True).all()
        goals_info = []
        for g in goals:
            remaining = max(0, g.target_amount - g.current_amount - g.offset_amount)
            sym = cur_sym.get(g.currency, g.currency)
            goals_info.append(f"  {g.name}: цель {sym}{g.target_amount:,.0f}, осталось {sym}{remaining:,.0f}")

        # Subscriptions
        subs = session.query(Subscription).filter(Subscription.is_active == True).all()
        total_subs = sum(s.amount if s.period == "monthly" else s.amount / 12 for s in subs)

        # Deposits
        deposits = session.query(Deposit).filter(Deposit.is_active == True).all()

        # Build context
        ctx = f"""=== ФИНАНСОВОЕ СОСТОЯНИЕ ПОЛЬЗОВАТЕЛЯ ===

ЕЖЕМЕСЯЧНЫЙ ДОХОД: {total_monthly_income:,.0f}\u20bd
Источники: {', '.join(f'{i.name} ({i.amount:,.0f}\u20bd)' for i in incomes)}

РАСХОДЫ ПО МЕСЯЦАМ:
{chr(10).join(f'  {m}: {s:,.0f} руб' for m, s in sorted(monthly_expenses.items())[-6:])}

РАСХОДЫ ПО КАТЕГОРИЯМ (последние 3 мес.):
{chr(10).join(f'  {name}: {abs(total):,.0f} руб ({count} операций)' for name, total, count in cat_data)}

ПОДПИСКИ: {total_subs:,.0f}\u20bd/мес. ({len(subs)} шт.)
{chr(10).join(f'  {s.name}: {s.amount:,.0f}\u20bd/{s.period}' for s in subs)}

ЗАНАЧКА (emergency fund): {total_reserve_rub:,.0f}\u20bd
{chr(10).join(reserve_info) if reserve_info else '  Не заполнена'}

ФИНАНСОВЫЕ ЦЕЛИ:
{chr(10).join(goals_info) if goals_info else '  Нет активных целей'}

ВКЛАДЫ: {len(deposits)} шт.
{chr(10).join(f'  {d.bank} {d.name}: {d.amount:,.0f}\u20bd под {d.rate}%' for d in deposits) if deposits else '  Нет вкладов'}

КУРСЫ ВАЛЮТ: USD={rates.get("USD", 0):.2f}\u20bd, EUR={rates.get("EUR", 0):.2f}\u20bd, KZT={rates.get("KZT", 0):.4f}\u20bd
"""
        return ctx
    finally:
        session.close()


SYSTEM_PROMPT = (
    "Ты - персональный финансовый советник. Анализируй данные пользователя "
    "и давай конкретные, практичные рекомендации. Отвечай на русском языке. "
    "Будь кратким и по делу. Используй цифры из контекста."
)


def call_ai(messages: list, endpoint: str, key: str, model: str) -> str:
    """Call AI API with financial context. Supports Anthropic and OpenAI-compatible APIs."""

    # Normalize base URL: strip trailing slash
    base_url = endpoint.rstrip("/")

    if "anthropic.com" in base_url:
        # Native Anthropic API
        url = base_url if base_url.endswith("/messages") else f"{base_url}/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": model,
            "max_tokens": 2500,
            "temperature": 0.5,
            "system": SYSTEM_PROMPT,
            "messages": messages,
        }
    else:
        # OpenAI-compatible API (cloud.ru, OpenAI, local LLMs, etc.)
        # Ensure URL ends with /chat/completions
        if not base_url.endswith("/chat/completions"):
            url = f"{base_url}/chat/completions"
        else:
            url = base_url

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        }
        payload = {
            "model": model,
            "max_tokens": 2500,
            "temperature": 0.5,
            "top_p": 0.95,
            "presence_penalty": 0,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
            ] + messages,
        }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        # Parse response
        if "anthropic.com" in base_url:
            return data.get("content", [{}])[0].get("text", "Нет ответа")
        else:
            return data.get("choices", [{}])[0].get("message", {}).get("content", "Нет ответа")
    except requests.exceptions.RequestException as e:
        return f"Ошибка API: {e}"
    except (KeyError, IndexError) as e:
        return f"Ошибка разбора ответа: {e}\n\nОтвет: {resp.text[:500]}"


# --- Chat UI ---
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Quick action buttons
st.markdown("#### Быстрые вопросы")
col1, col2, col3, col4 = st.columns(4)

quick_prompts = {
    "Саммари": "Сделай краткое саммари моего финансового состояния. Что хорошо, что плохо?",
    "Советы": "Дай 5 конкретных советов как улучшить мою финансовую ситуацию. Основывайся на реальных данных.",
    "Подписки": "Проанализируй мои подписки. Какие можно отключить или оптимизировать?",
    "Заначка": "Оцени мою заначку. Достаточна ли она? Как лучше распределить по валютам?",
}

for label, prompt in quick_prompts.items():
    if st.columns(4)[list(quick_prompts.keys()).index(label)].button(label, use_container_width=True):
        st.session_state.chat_history.append({"role": "user", "content": prompt})

st.markdown("---")

# Display chat history
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
user_input = st.chat_input("Задайте вопрос о ваших финансах...")

if user_input:
    st.session_state.chat_history.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

# Process last message if it's from user
if st.session_state.chat_history and st.session_state.chat_history[-1]["role"] == "user":
    endpoint = st.session_state.get("ai_endpoint", api_endpoint)
    key = api_key
    mdl = st.session_state.get("ai_model", model)

    if not key:
        with st.chat_message("assistant"):
            st.warning("Укажите API Key в настройках (боковая панель).")
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": "Укажите API Key в настройках (боковая панель)."
        })
    else:
        with st.chat_message("assistant"):
            with st.spinner("Анализирую ваши финансы..."):
                # Build context and inject into first user message
                ctx = build_financial_context()
                messages_for_api = []
                for i, msg in enumerate(st.session_state.chat_history):
                    if msg["role"] == "user":
                        if i == len(st.session_state.chat_history) - 1:
                            # Last message - add context
                            messages_for_api.append({
                                "role": "user",
                                "content": f"{ctx}\n\nВОПРОС ПОЛЬЗОВАТЕЛЯ:\n{msg['content']}"
                            })
                        else:
                            messages_for_api.append(msg)
                    else:
                        messages_for_api.append(msg)

                # Keep only last 10 messages for context window
                messages_for_api = messages_for_api[-10:]

                response = call_ai(messages_for_api, endpoint, key, mdl)
                st.markdown(response)

        st.session_state.chat_history.append({"role": "assistant", "content": response})

# Clear chat
if st.session_state.chat_history:
    if st.button("Очистить чат"):
        st.session_state.chat_history = []
        st.rerun()
