# ETL Bitrix24 → Google Sheets (Streamlit)

Продакшн-орієнтований ETL-сервіс для синхронізації CRM-угод із **Bitrix24** у **Google Sheets** з фокусом на маркетингову аналітику (UTM-джерела, канали, кампанії).

> Проєкт розрахований на ручний або напівручний запуск через Streamlit UI: підходить для інфраструктури, де застосунок може «засинати» і немає постійного cron.

---

## Зміст

- [1. Що робить сервіс](#1-що-робить-сервіс)
- [2. Ключові можливості](#2-ключові-можливості)
- [3. Архітектура та структура проєкту](#3-архітектура-та-структура-проєкту)
- [4. Потік даних (як працює синхронізація)](#4-потік-даних-як-працює-синхронізація)
- [5. Вимоги](#5-вимоги)
- [6. Швидкий старт](#6-швидкий-старт)
- [7. Налаштування секретів і змінних оточення](#7-налаштування-секретів-і-змінних-оточення)
- [8. Налаштування Google Apps Script Web App (рекомендовано)](#8-налаштування-google-apps-script-web-app-рекомендовано)
- [9. Запуск застосунку](#9-запуск-застосунку)
- [10. Режими синхронізації](#10-режими-синхронізації)
- [11. Формат даних у Google Sheets](#11-формат-даних-у-google-sheets)
- [12. State-файл і ідемпотентність](#12-state-файл-і-ідемпотентність)
- [13. Типові сценарії використання](#13-типові-сценарії-використання)
- [14. Troubleshooting (типові помилки)](#14-troubleshooting-типові-помилки)
- [15. Безпека та best practices](#15-безпека-та-best-practices)
- [16. Подальший розвиток](#16-подальший-розвиток)

---

## 1. Що робить сервіс

Сервіс:

1. Читає угоди з Bitrix24 по заданих воронках (`CATEGORY_ID`).
2. Залишає лише угоди, у яких заповнено хоча б одне UTM-поле.
3. Нормалізує дані (перейменування полів, мапінг воронок/стадій на людиночитні назви).
4. Виконує upsert у `crm_master` Google Sheets за ключем `deal_id`.
5. Видаляє рядки з таблиці, що більше не відповідають валідному набору UTM-угод у CRM.
6. Зберігає timestamp останньої синхронізації у `state.json`.

---

## 2. Ключові можливості

- **Повна початкова синхронізація** (`initial_full_sync`) з опціональним фільтром за датою створення.
- **Інкрементальна синхронізація** (`incremental_sync`) за `DATE_MODIFY` від останнього запуску.
- **UTM-фільтр**: беруться лише угоди з не порожніми UTM-полями.
- **Upsert без дублів**: нові угоди додаються, існуючі — оновлюються.
- **Актуалізація стадій/воронок** при переміщенні угоди у CRM.
- **Очищення таблиці + reset state** з UI.
- **Два режими запису в Google Sheets**:
  - через **Apps Script Web App** (основний рекомендований);
  - через **Service Account** (fallback).
- **Ретраї, таймаути, батчинг** для стабільної роботи з Google Apps Script.
- **Alias-підтримка action-ів Web App** для сумісності з різними ревізіями скрипта.

---

## 3. Архітектура та структура проєкту

```text
.
├── app.py                  # Streamlit UI, логін, запуск sync, прогрес, логи
├── etl.py                  # Основна ETL-логіка (initial/incremental, upsert, state)
├── bitrix.py               # Клієнт Bitrix24 webhook API, пагінація, ретраї
├── sheets.py               # Клієнт Google Sheets (Web App або service account)
├── config.py               # Секрети/ENV, константи, master schema
├── mapping.py              # Мапінг воронок і стадій на людиночитні назви
├── state.json              # Поточний timestamp останньої синхронізації
├── apps_script/
│   └── Code.gs             # Google Apps Script Web App proxy
└── requirements.txt        # Python залежності
```

---

## 4. Потік даних (як працює синхронізація)

### 4.1 Повна синхронізація

1. Для кожної воронки з `PIPELINES` завантажуються угоди (`crm.deal.list`).
2. Застосовується UTM-фільтр.
3. Дані нормалізуються у формат цільової таблиці.
4. Виконується dedup у пам’яті за `deal_id`.
5. Upsert у таблицю:
   - якщо `deal_id` знайдено — `update_row`;
   - якщо ні — `append_rows`.
6. Далі виконується ревізія таблиці: видаляються рядки, що не належать валідному набору UTM-угод.
7. Оновлюється `state.json`.

### 4.2 Інкрементальна синхронізація

1. Зчитується `last_sync_timestamp` зі `state.json`.
2. Запитуються лише угоди, змінені після timestamp (`>DATE_MODIFY`).
3. UTM-фільтр + нормалізація + dedup + upsert.
4. Повторно збирається повний список актуальних UTM `deal_id` у CRM.
5. З таблиці видаляються неактуальні рядки.
6. Оновлюється `state.json`.

---

## 5. Вимоги

- Python **3.11+**.
- Доступ до Bitrix24 webhook API.
- Google Spreadsheet (цільова таблиця).
- Один із режимів доступу до Sheets:
  - Apps Script Web App URL + token;
  - або Service Account credentials.

---

## 6. Швидкий старт

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Створіть secrets:

```bash
mkdir -p .streamlit
# створіть файл вручну: .streamlit/secrets.toml
```

Запуск:

```bash
streamlit run app.py
```

---

## 7. Налаштування секретів і змінних оточення

Сервіс читає значення у пріоритеті:

1. `st.secrets` (`.streamlit/secrets.toml`),
2. ENV-змінні (fallback).

### 7.1 Приклад `.streamlit/secrets.toml`

```toml
[bitrix]
webhook_url = "https://your-domain.bitrix24.ua/rest/1/xxxxxxxxxxxx"

[google]
url = "https://docs.google.com/spreadsheets/d/<SPREADSHEET_ID>/edit"
# альтернативно можна задати spreadsheet_id замість url
spreadsheet_id = "<SPREADSHEET_ID>"

# Режим Apps Script Web App (рекомендовано)
web_app_url = "https://script.google.com/macros/s/.../exec"
web_app_token = "<STRONG_RANDOM_TOKEN>"

# Режим service account (fallback)
service_account_file = "service_account.json"
# або service_account_info = "{...json...}"

[auth]
username = "admin"
password = "strong-password"
```

### 7.2 ENV-параметри (опційно)

- `BITRIX_WEBHOOK_URL`
- `GOOGLE_SHEETS_URL`
- `GOOGLE_SPREADSHEET_ID`
- `GOOGLE_WEB_APP_URL`
- `GOOGLE_WEB_APP_TOKEN`
- `GOOGLE_SERVICE_ACCOUNT_FILE`
- `GOOGLE_SERVICE_ACCOUNT_INFO`
- `STATE_FILE` (default: `state.json`)
- `REQUEST_TIMEOUT` (default: `30`)
- `MAX_RETRIES` (default: `3`)
- `RETRY_DELAY_SECONDS` (default: `1.5`)
- `WEB_APP_APPEND_TIMEOUT` (default: `REQUEST_TIMEOUT`)
- `WEB_APP_APPEND_BATCH_SIZE` (default: `200`)
- `APP_USERNAME`, `APP_PASSWORD` (fallback для авторизації UI)

---

## 8. Налаштування Google Apps Script Web App (рекомендовано)

1. Відкрийте [script.google.com](https://script.google.com).
2. Створіть новий Apps Script проєкт.
3. Вставте код із `apps_script/Code.gs`.
4. Замініть `WEB_APP_TOKEN` на складний випадковий токен.
5. Deploy → **New deployment** → **Web app**:
   - Execute as: **Me**
   - Who has access: **Anyone**
6. Збережіть URL деплою в `google.web_app_url`.

> Важливо: після будь-яких змін у `Code.gs` потрібно перевипустити deployment через **Manage deployments → Edit → Deploy**.

---

## 9. Запуск застосунку

```bash
streamlit run app.py
```

Для Linux-середовищ з обмеженим `inotify`:

```bash
streamlit run app.py --server.fileWatcherType none
```

Після запуску у UI доступні:

- запуск інкрементальної синхронізації;
- запуск повної синхронізації (з фільтром за датою створення);
- повне очищення таблиці + reset `state.json`;
- перегляд логів і поточного state.

---

## 10. Режими синхронізації

### `initial_full_sync`

Використовуйте, коли:

- перший запуск проєкту;
- потрібно перевантажити дані «з нуля»;
- треба перебудувати таблицю після зміни мапінгу чи логіки.

### `incremental_sync`

Використовуйте для регулярного оновлення:

- мінімальне навантаження на API;
- підтягуються лише змінені угоди від останнього запуску;
- виконуються актуалізації/видалення неактуальних рядків.

---

## 11. Формат даних у Google Sheets

Назва робочого аркуша: `crm_master`.

Обов’язкові колонки (і порядок):

1. `deal_id`
2. `pipeline_name`
3. `stage_name`
4. `date_create`
5. `date_modify`
6. `amount`
7. `utm_source`
8. `utm_medium`
9. `utm_campaign`
10. `utm_content`
11. `utm_term`

`GoogleSheetsClient.ensure_header()` автоматично приводить заголовок аркуша до очікуваної схеми.

---

## 12. State-файл і ідемпотентність

- `state.json` зберігає `last_sync_timestamp`.
- Після успішної sync timestamp оновлюється в UTC ISO-форматі.
- Upsert по `deal_id` забезпечує відсутність дублікатів у нормальному сценарії.
- Під час повної sync виконується дедуплікація в пам’яті перед записом.

---

## 13. Типові сценарії використання

### Сценарій A: перший запуск

1. Налаштуйте secrets.
2. Перевірте підключення до таблиці.
3. Запустіть **повну початкову синхронізацію**.
4. Перевірте, що таблиця наповнилась коректно.

### Сценарій B: регулярне оновлення

1. Відкрийте UI.
2. Натисніть **інкрементальну синхронізацію**.
3. Перегляньте JSON-результат (`appended/updated/deleted`).

### Сценарій C: аварійне очищення

1. Використайте кнопку **Повне очищення таблиці**.
2. Перезапустіть повну sync.

---

## 14. Troubleshooting (типові помилки)

### `ImportError: cannot import name 'read_secret' from 'config'`

Часто це вторинна помилка через падіння імпорту `config.py` вище (наприклад, невалідний JSON у `google.service_account_info`).

Що перевірити:

- валідність JSON у `GOOGLE_SERVICE_ACCOUNT_INFO`;
- або перейдіть на режим Web App (`google.web_app_url` + `google.web_app_token`).

---

### `404 .../crm.deal.list.json/crm.deal.list.json`

У webhook передано URL конкретного методу замість базового webhook.

Правильно:

```text
https://<domain>.bitrix24.<tld>/rest/<user_id>/<token>
```

У коді є нормалізація URL, але краще одразу зберігати базовий формат.

---

### `Apps Script Web App error: unknown_action`

Причина: у продеплоєному `Code.gs` відсутній потрібний action.

Що робити:

1. Оновіть код `apps_script/Code.gs`.
2. Перевипустіть deployment (Manage deployments → Edit → Deploy).
3. Переконайтесь, що `google.web_app_url` вказує на актуальну версію.

---

### `Read timed out` при `append_rows`

Причина: занадто великий батч або повільне виконання Apps Script.

Що робити:

- збільшити `WEB_APP_APPEND_TIMEOUT` (наприклад 60–120);
- зменшити `WEB_APP_APPEND_BATCH_SIZE` (100 або 50);
- за потреби збільшити `MAX_RETRIES`.

---

### `inotify watch limit reached`

Для локального Linux-запуску:

```bash
streamlit run app.py --server.fileWatcherType none
```

---

## 15. Безпека та best practices

- Не комітьте `.streamlit/secrets.toml` у Git.
- Не зберігайте production-токени у відкритих репозиторіях.
- Для `WEB_APP_TOKEN` використовуйте довге випадкове значення.
- Обмежуйте доступ до UI через `auth.username` / `auth.password`.
- Регулярно перевипускайте токени при ротації доступів.

---

## 16. Подальший розвиток

- Додати scheduler (cron/GitHub Actions/Cloud Run job) для автоматичних запусків.
- Додати unit/integration тести для ETL-модулів.
- Додати окремий лист `sync_audit` для історії запусків.
- Експортувати метрики (Prometheus/Grafana або хоча б structured logs).

---

## Ліцензія

Якщо потрібно, додайте окремий файл `LICENSE` (наприклад MIT/Apache-2.0) згідно політики вашої команди.
