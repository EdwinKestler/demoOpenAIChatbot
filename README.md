# demoOpenAIChatbot

## Overview
This project is a WhatsApp chatbot powered by [OpenAI's GPT‑4](https://openai.com/) and built with [FastAPI](https://fastapi.tiangolo.com/). Incoming WhatsApp messages are received through Twilio's sandbox, processed by the FastAPI application, and routed to the OpenAI API for a response. Conversations are stored in a PostgreSQL database and replies are sent back to the user via Twilio.

## Architecture
- **FastAPI** exposes a `/message` endpoint that Twilio calls when a WhatsApp message arrives.
- **OpenAI** provides natural‑language responses through the `ChatCompletion` API.
- **Twilio** delivers WhatsApp messages both to and from the chatbot.
- **PostgreSQL** stores each conversation for later analysis or auditing.
- **PDF Service** demonstrates generating a PDF quote when the user requests a "cotización".

## Setup
### Environment variables
Create a `.env` file or export the following variables before running the app:

```bash
# OpenAI
OPENAI_API_KEY="your-openai-api-key"

# Twilio
TWILIO_ACCOUNT_SID="your-twilio-account-sid"
TWILIO_AUTH_TOKEN="your-twilio-auth-token"
TWILIO_NUMBER="whatsapp-sandbox-number"
TO_NUMBER="recipient-number"  # the WhatsApp number to send replies to

# Database
DB_USER="postgres-user"
DB_PASSWORD="postgres-password"
```

### Install dependencies
```bash
python -m pip install -r requirements.txt
```

## Running the server
1. Start the FastAPI development server:
   ```bash
   uvicorn app.main:app --reload
   ```
2. Expose the server to the internet using a tunnelling service such as ngrok:
   ```bash
   ngrok http 8000
   ```
3. In the [Twilio WhatsApp sandbox](https://www.twilio.com/console/sms/whatsapp/sandbox), set the **WHEN A MESSAGE COMES IN** URL to the publicly accessible URL followed by `/message` (e.g. `https://<ngrok-id>.ngrok.io/message`).

## Project structure
After refactoring, the project is organised as:

```
├── app
│   ├── __init__.py
│   ├── database.py       # Database connection and session management
│   ├── main.py           # FastAPI application and webhook endpoint
│   ├── models.py         # SQLAlchemy models
│   ├── services
│   │   └── pdf.py        # PDF generation service
│   └── utils.py          # Twilio utilities and logging
├── examples
│   └── helloworld_pythonconf.py
├── requirements.txt
└── README.md
```

## Notes
- The server expects a running PostgreSQL instance reachable at `localhost:5432` with a database named `mydb`.
- Use this project as a starting point for more advanced WhatsApp assistants.
