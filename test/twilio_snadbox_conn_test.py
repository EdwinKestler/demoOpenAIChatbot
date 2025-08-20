import os
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()  # Load environment variables from .env file

account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
from_number = os.getenv("TWILIO_NUMBER")
to_number = os.getenv("TO_NUMBER")

if all([account_sid, auth_token, from_number, to_number]):
    try:
        client = Client(account_sid, auth_token)
        message = client.messages.create(
            from_=from_number,
            content_sid='HXb5b62575e6e4ff6129ad7c8efe1f983e',
            content_variables='{"1":"12/1","2":"3pm"}',
            to=to_number,
        )
        print(message.sid)
    except Exception as exc:
        print(f"Twilio sandbox test failed: {exc}")
else:
    print("Missing Twilio environment variables.")
    