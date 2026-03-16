# ETL Bitrix24 → Google Sheets (Streamlit)

Продакшн-орієнтований ETL-сервіс для синхронізації угод із Bitrix24 у Google Sheets для маркетингової аналітики.

## Можливості

- Одноразова повна синхронізація за вибраними воронками (`initial_full_sync`)
- Інкрементальна синхронізація за `DATE_MODIFY` (`incremental_sync`)
- UTM-фільтр: вивантажуються лише угоди, де є хоча б одне непорожнє UTM-поле
- Upsert за `deal_id` (без дублів)
- Оновлення актуальних значень воронки/стадії, якщо угода перемістилась
- Ручний запуск зі Streamlit UI (зручно для застосунків, що "засинають")
- Підтримка двох режимів запису в Google Sheets:
  - через Apps Script Web App проксі (**рекомендовано**)
  - через service account (fallback)

## Структура проєкту

- `app.py` — інтерфейс Streamlit
- `etl.py` — оркестрація синхронізації та керування станом
- `bitrix.py` — клієнт Bitrix webhook API з ретраями та пагінацією
- `sheets.py` — робота з Google Sheets (Web App або service account)
- `mapping.py` — словники відповідності воронок і стадій
- `config.py` — конфігурація та константи
- `apps_script/Code.gs` — приклад Google Apps Script проксі
- `state.json` — зберігання timestamp останньої синхронізації

## Налаштування (Apps Script Web App)

1. Створіть і активуйте віртуальне середовище Python 3.11.
2. Встановіть залежності:
   ```bash
   pip install -r requirements.txt
   ```
3. Створіть файл секретів Streamlit:
   ```bash
   mkdir -p .streamlit
   cp .streamlit/secrets.example.toml .streamlit/secrets.toml
   ```
4. Заповніть у `.streamlit/secrets.toml`:
   - `bitrix.webhook_url` — webhook Bitrix24
   - `google.url` — URL Google таблиці
   - `google.web_app_url` — URL розгорнутого Apps Script Web App
   - `google.web_app_token` — секретний токен для запитів
   - `auth.username` / `auth.password` — логін і пароль у UI

### Як розгорнути Apps Script

1. Відкрийте Google Apps Script (script.google.com) і створіть проєкт.
2. Скопіюйте код з `apps_script/Code.gs`.
3. У коді встановіть `WEB_APP_TOKEN`.
4. Deploy → New deployment → Web app:
   - Execute as: **Me**
   - Who has access: **Anyone** (токен захищає endpoint)
5. Скопіюйте URL деплою в `google.web_app_url`.

> `secrets.toml` не треба комітити в GitHub. Додайте його тільки в середовище деплою (наприклад Streamlit Cloud).


### Додаткові змінні оточення для стабільності Web App

- `WEB_APP_APPEND_BATCH_SIZE` (default: `200`) — розмір батча для `append_rows` у режимі Apps Script Web App.
- `WEB_APP_APPEND_TIMEOUT` (default: значення `REQUEST_TIMEOUT`) — таймаут (секунди) саме для запитів `append_rows`.

## Запуск Streamlit

```bash
streamlit run app.py
```

## Обов'язкові колонки Google Sheet

`deal_id, pipeline_name, stage_name, date_create, date_modify, amount, utm_source, utm_medium, utm_campaign, utm_content, utm_term`

## Примітки

- Якщо код стадії відсутній у `STAGE_MAP`, використовується сирий `STAGE_ID`.
- Початкова синхронізація видаляє дублікати по `deal_id` перед upsert.
- Інкрементальна синхронізація читає `state.json` та оновлює його після кожного запуску.

## Типові помилки

### ImportError: cannot import name 'read_secret' from 'config'

Це часто похідна помилка: модуль `config.py` падає під час імпорту раніше, ніж Python доходить до визначення `read_secret`.

Один із типових сценаріїв — невалідний JSON у `google.service_account_info` (або `GOOGLE_SERVICE_ACCOUNT_INFO`). Тепер застосунок безпечно обробляє такий випадок і переходить у fallback-режим (`None`) замість падіння імпорту.

Що перевірити:
- якщо використовуєте service account через JSON-рядок, переконайтесь, що це валідний JSON;
- або використовуйте режим Apps Script Web App (`google.web_app_url` + `google.web_app_token`).

### 404 .../crm.deal.list.json/crm.deal.list.json

Це означає, що в `bitrix.webhook_url` (або `BITRIX_WEBHOOK_URL`) передано не базовий webhook, а URL методу (наприклад із хвостом `/crm.deal.list.json`).

Тепер застосунок автоматично нормалізує такий URL до базового формату `/rest/{user_id}/{token}`. Але все одно рекомендовано зберігати у секретах саме базовий webhook без назви методу.


### Apps Script Web App error: `unknown_action`

Якщо інкрементальна синхронізація завершується помилкою `Apps Script Web App error: {'ok': False, 'error': 'unknown_action'}`, зазвичай це означає, що у Web App розгорнута стара версія `Code.gs` з іншим набором action-ів.

Що зроблено в поточній версії:
- `apps_script/Code.gs` приймає canonical action + alias-и (наприклад `deleteRows`, `delete_row`, `append`, `count` тощо);
- клієнт `sheets.py` автоматично пробує alias-и, якщо основний action не підтримується;
- у відповідь `unknown_action` тепер повертається також `action_received`, щоб швидше діагностувати проблему.

Щоб виправити помилку:
1. Оновіть Apps Script код з `apps_script/Code.gs`.
2. Зробіть **Deploy → Manage deployments → Edit → Deploy** (обов'язково перевипустіть deployment).
3. Перевірте, що `google.web_app_url` у `secrets.toml` вказує саме на актуальний deployment URL.


### Apps Script Web App request failed ... Read timed out

Якщо бачите помилку на кшталт `Apps Script Web App request failed for action 'append_rows' ... Read timed out`, це зазвичай означає, що запит на вставку був занадто великим або Apps Script виконувався довше за таймаут клієнта.

Що зроблено в поточній версії:
- `append_rows` у `sheets.py` надсилається батчами (за замовчуванням по 200 рядків);
- для `append_rows` можна задати окремий збільшений таймаут (`WEB_APP_APPEND_TIMEOUT`).

Що спробувати:
1. Зменшити `WEB_APP_APPEND_BATCH_SIZE` (наприклад, до `100` або `50`).
2. Збільшити `WEB_APP_APPEND_TIMEOUT` (наприклад, до `60`–`120`).
3. За потреби підвищити `MAX_RETRIES`.

### inotify watch limit reached

Для локального запуску Streamlit на Linux можна вимкнути file watcher:

```bash
streamlit run app.py --server.fileWatcherType none
```

Це прибирає помилку `inotify watch limit reached` у середовищах з обмеженим лімітом watcher-ів.
