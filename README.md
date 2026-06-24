# demoOpenAIChatbot

WhatsApp hardware-store assistant built with FastAPI, OpenAI, Twilio, and PostgreSQL.

## Features

- WhatsApp webhook at `POST /message` with Twilio signature validation
- Text replies via OpenAI (`gpt-4o-mini`)
- Image classification via OpenAI Vision (`gpt-5-nano` with `gpt-5` fallback)
- Product lookup from a catalog database
- PDF quote generation for cotización requests
- Conversation browser at `/conversations` (HTTP Basic Auth protected)
- JSON API at `/api/conversations`

## Architecture

```text
WhatsApp → Twilio → POST /message → FastAPI
                         ├─ OpenAI (text + vision)
                         ├─ Chat DB (conversations)
                         ├─ Catalog DB (products)
                         └─ /public (media + PDFs)
```

## Prerequisites

- Python 3.10+
- PostgreSQL (two databases: chat + catalog)
- OpenAI API key
- Twilio WhatsApp sandbox or production number
- Public HTTPS URL (ngrok or deployed host) for Twilio webhooks

## Quick start

1. Copy environment template:

```bash
cp .env.example .env
```

2. Edit `.env` with your credentials.

3. Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

4. Start PostgreSQL (Docker option):

```bash
docker compose up -d postgres
```

5. Run the app:

```bash
uvicorn app.main:app --reload
```

6. Expose locally with ngrok and set Twilio webhook to `https://<host>/message`.

## Docker

Run app + PostgreSQL together:

```bash
cp .env.example .env
docker compose up --build
```

The app listens on `http://localhost:8000`.

## Environment variables

See [`.env.example`](.env.example) for the full list. Required variables:

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | OpenAI API access |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_NUMBER` | WhatsApp messaging |
| `PUBLIC_BASE_URL` | Public app URL for Twilio signature validation |
| `DB_USER`, `DB_PASSWORD`, `DB_CHAT_NAME` | Chat/conversations database |
| `DB_CATALOG_USER`, `DB_CATALOG_PASSWORD`, `DB_CATALOG_NAME` | Product catalog database |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | Protect `/conversations` routes |

Optional:

| Variable | Default | Purpose |
|----------|---------|---------|
| `TWILIO_VALIDATE_SIGNATURE` | `True` | Validate Twilio webhook signatures |
| `MAX_REQUEST_BODY_BYTES` | `1048576` | Reject oversized webhook payloads |

## Routes

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | None | Health check |
| POST | `/message` | Twilio signature | WhatsApp webhook |
| GET | `/conversations` | Basic Auth | Conversation browser UI |
| GET | `/api/conversations` | Basic Auth | Conversation JSON API |

## Tests

Credential smoke tests (require real `.env`):

```bash
python test/postgres_cred_conn_test.py
python test/openai_credentials_connection_test.py
python test/twilio_snadbox_conn_test.py
```

Automated tests:

```bash
pytest tests/ -v
```

## Project structure

```text
app/
  main.py           # FastAPI routes and webhook logic
  catalog.py        # Shared hardware anchor definitions
  security.py       # Twilio validation, admin auth, body limits
  llm_logic.py      # OpenAI text + vision calls
  utils.py          # Twilio send + media download
  database.py       # Dual PostgreSQL setup
  models.py         # SQLAlchemy models
  services/pdf.py   # PDF quote generation
  templates/        # Conversation browser UI
  static/           # CSS
tests/              # pytest suite
scripts/            # Database init for Docker
```

## Security notes

- Twilio webhooks are validated with `X-Twilio-Signature` when `TWILIO_VALIDATE_SIGNATURE=True`
- Set `PUBLIC_BASE_URL` to your public HTTPS URL so signature validation uses the correct URL
- Conversation history requires HTTP Basic Auth
- User-uploaded media in `public/` is gitignored; only `.gitkeep` is tracked