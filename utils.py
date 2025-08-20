# Standard library import
import logging
import time

# Third-party imports
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from decouple import config


# Find your Account SID and Auth Token at twilio.com/console
# and set the environment variables. See http://twil.io/secure
account_sid = config("TWILIO_ACCOUNT_SID")
auth_token = config("TWILIO_AUTH_TOKEN")
client = Client(account_sid, auth_token, timeout=15)
twilio_number = config('TWILIO_NUMBER')

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Sending message logic through Twilio Messaging API
def send_message(to_number, body_text, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            message = client.messages.create(
                from_=f"whatsapp:{twilio_number}",
                body=body_text,
                to=f"whatsapp:{to_number}"
                )
            logger.info(f"Message sent to {to_number}: {message.body}")
            break
        except TwilioRestException as e:
            logger.error(
                f"Twilio API error on attempt {attempt + 1} sending to {to_number}: {e}"
            )
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
    else:
        logger.error(f"Failed to send message to {to_number} after {max_retries} attempts")
