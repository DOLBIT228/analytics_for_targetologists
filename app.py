"""Streamlit UI для ручного запуску ETL."""
from __future__ import annotations

import json
import logging
from io import StringIO

import streamlit as st

import config
from etl import incremental_sync, initial_full_sync, load_state
from sheets import GoogleSheetsClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


class UILogHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.stream = StringIO()

    def emit(self, record: logging.LogRecord) -> None:
        self.stream.write(self.format(record) + "\n")

    def get_logs(self) -> str:
        return self.stream.getvalue()


def require_login() -> bool:
    """Проста авторизація через Streamlit secrets."""
    read_secret_fn = getattr(config, "read_secret", None)

    if callable(read_secret_fn):
        configured_username = str(read_secret_fn("auth.username", "APP_USERNAME", "")).strip()
        configured_password = str(read_secret_fn("auth.password", "APP_PASSWORD", "")).strip()
    else:
        configured_username = str(st.secrets.get("auth", {}).get("username", "") or "").strip()
        configured_password = str(st.secrets.get("auth", {}).get("password", "") or "").strip()

    if not configured_username or not configured_password:
        st.info("Авторизацію не налаштовано (auth.username/auth.password). Доступ відкритий.")
        return True

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.subheader("Вхід до застосунку")
    username = st.text_input("Логін")
    password = st.text_input("Пароль", type="password")
    if st.button("Увійти", type="primary"):
        if username == configured_username and password == configured_password:
            st.session_state.authenticated = True
            st.success("Успішний вхід")
            st.rerun()
        else:
            st.error("Неправильний логін або пароль")
    return False


def render_status_panel() -> None:
    state = load_state()
    last_sync = state.get("last_sync_timestamp")

    deals_count = "Н/Д"
    try:
        deals_count = GoogleSheetsClient().count_deals()
    except Exception as exc:
        st.warning(f"Не вдалося прочитати кількість угод з Google Sheets: {exc}")

    c1, c2 = st.columns(2)
    c1.metric("Остання синхронізація", str(last_sync))
    c2.metric("Угод у таблиці", str(deals_count))


def main() -> None:
    st.set_page_config(page_title="Bitrix24 -> Google Sheets ETL", layout="wide")
    st.title("Синхронізація Bitrix24 CRM")
    st.caption("Ручний режим синхронізації: дані оновлюються після натискання кнопки.")

    if not require_login():
        return

    render_status_panel()

    ui_handler = UILogHandler()
    ui_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    root_logger = logging.getLogger()
    root_logger.addHandler(ui_handler)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Запустити інкрементальну синхронізацію", type="primary"):
            with st.spinner("Виконується інкрементальна синхронізація..."):
                try:
                    result = incremental_sync()
                    st.success("Інкрементальну синхронізацію завершено")
                    st.json(result)
                except Exception as exc:
                    st.error(f"Інкрементальна синхронізація завершилась з помилкою: {exc}")

    with col2:
        if st.button("Запустити повну початкову синхронізацію"):
            with st.spinner("Виконується повна початкова синхронізація..."):
                try:
                    result = initial_full_sync()
                    st.success("Повну початкову синхронізацію завершено")
                    st.json(result)
                except Exception as exc:
                    st.error(f"Початкова синхронізація завершилась з помилкою: {exc}")

    st.subheader("Логи")
    st.code(ui_handler.get_logs() or "Логів поки немає.")

    st.subheader("Поточний state.json")
    st.code(json.dumps(load_state(), ensure_ascii=False, indent=2), language="json")


if __name__ == "__main__":
    main()
