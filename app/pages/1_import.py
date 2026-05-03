"""Page: Import bank statements."""
import streamlit as st
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from database import init_db, SessionLocal, Transaction
from import_service import import_file, detect_bank
from sqlalchemy import func

init_db()

st.title("Импорт выгрузок")

tab1, tab2 = st.tabs(["Загрузить файлы", "Из папки"])

with tab1:
    st.markdown("""
    | Банк | Формат | Название файла |
    |------|--------|----------------|
    | Альфа-Банк | `.xlsx` | `Альфа...` или `Alfa...` |
    | Сбербанк | `.xlsx` | `Сбер...` или `Sber...` |
    | Озон Банк | `.pdf` | `Озон...` или `Ozon...` |
    """)

    uploaded_files = st.file_uploader(
        "Выберите файлы выгрузок",
        type=["xlsx", "xls", "pdf"],
        accept_multiple_files=True,
    )

    if uploaded_files:
        for uf in uploaded_files:
            bank = detect_bank(uf.name)
            icon = {"alfa": "\U0001f534", "sber": "\U0001f7e2", "ozon": "\U0001f535"}.get(bank, "\u2753")
            st.write(f"{icon} **{uf.name}** \u2192 {(bank or '???').upper()}")

        if st.button("Импортировать", type="primary"):
            for uf in uploaded_files:
                with st.spinner(f"Импорт {uf.name}..."):
                    suffix = Path(uf.name).suffix
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                        tmp.write(uf.getvalue())
                        tmp_path = tmp.name
                    bank = detect_bank(uf.name)
                    result = import_file(tmp_path, bank)
                    os.unlink(tmp_path)

                    if "error" in result:
                        st.error(f"{uf.name}: {result['error']}")
                    else:
                        st.success(
                            f"**{uf.name}**: {result['imported']} импортировано, "
                            f"{result['skipped']} дублей, {result['internal']} внутренних"
                        )

with tab2:
    import_dir = st.text_input(
        "Путь к папке:",
        value=str(Path(__file__).parent.parent.parent / "Выгрузки"),
    )
    if st.button("Сканировать папку", type="primary"):
        import_path = Path(import_dir)
        if not import_path.exists():
            st.error(f"Папка не найдена: {import_dir}")
        else:
            files = list(import_path.glob("*.xlsx")) + list(import_path.glob("*.pdf"))
            if not files:
                st.warning("Файлы не найдены.")
            else:
                for f in files:
                    with st.spinner(f"{f.name}..."):
                        result = import_file(str(f))
                        if "error" in result:
                            st.error(f"{f.name}: {result['error']}")
                        else:
                            st.success(
                                f"**{f.name}**: {result['imported']} / "
                                f"{result['skipped']} дублей / {result['internal']} внутр."
                            )

# Stats
st.markdown("---")
session = SessionLocal()
total = session.query(func.count(Transaction.id)).scalar()
internal = session.query(func.count(Transaction.id)).filter(Transaction.is_internal_transfer == True).scalar()
real = total - internal
col1, col2, col3 = st.columns(3)
col1.metric("Всего в базе", f"{total:,}")
col2.metric("Реальных", f"{real:,}")
col3.metric("Внутренних", f"{internal:,}")
session.close()
