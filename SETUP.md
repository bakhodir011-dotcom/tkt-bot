# TKT Registration Bot — Setup Guide

## 1. Install dependencies

```bash
pip install -r requirements.txt
```

## 2. Bot Token

1. Open Telegram → search **@BotFather**
2. Send `/newbot`, follow the steps
3. Copy the token and paste it into `bot.py`:
   ```python
   BOT_TOKEN = "YOUR_BOT_TOKEN"
   ```

## 3. Admin Chat ID

- **Personal chat:** send a message to [@userinfobot](https://t.me/userinfobot) — it returns your ID.
- **Group:** add [@userinfobot](https://t.me/userinfobot) to the group, it will show the group ID (starts with `-100`).

Paste it into `bot.py`:
```python
ADMIN_CHAT_ID = "123456789"  # or "-1001234567890" for a group
```

## 4. Google Sheets

### a) Create a Google Cloud project & service account
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or use existing)
3. Enable **Google Sheets API**
4. Go to **IAM & Admin → Service Accounts → Create Service Account**
5. Give it any name, click **Done**
6. Click the service account → **Keys → Add Key → JSON** — download the file
7. Rename it `service_account.json` and put it in the same folder as `bot.py`

### b) Create a Google Sheet
1. Create a new Google Sheet at [sheets.google.com](https://sheets.google.com)
2. Copy the Sheet ID from the URL:
   `https://docs.google.com/spreadsheets/d/**THIS_PART**/edit`
3. Paste it into `bot.py`:
   ```python
   SPREADSHEET_ID = "YOUR_SPREADSHEET_ID"
   ```

### c) Share the sheet with the service account
1. Open your sheet → **Share**
2. Add the service account email (found in `service_account.json` under `"client_email"`)
3. Give it **Editor** access

## 5. Run the bot

```bash
python bot.py
```

## Sheet columns (auto-created on first run)

| Timestamp | Full Name | Exam Date | Module | Passport/ID | Gender | Phone | Email | Language | Telegram ID |
|-----------|-----------|-----------|--------|-------------|--------|-------|-------|----------|-------------|
