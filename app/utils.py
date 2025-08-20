# Filename: app/utils.py
# Approx lines modified: ~1-120
# Reason: STOP using content_sid by default; send free-form text with body=. Optional template fallback.
#         Add use_template flag, optional media_url support, and WA prefix helper.

import logging
import time
import json  # [ADDED] for content_variables
from typing import Optional, List  # [ADDED]

from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from decouple import config

# Twilio credentials from environment
account_sid = config("TWILIO_ACCOUNT_SID")
auth_token = config("TWILIO_AUTH_TOKEN")
twilio_from = config("TWILIO_NUMBER")  # e.g., "whatsapp:+14155238886"
# Optional defaults (you can leave unset)
DEFAULT_CONTENT_SID = config("TWILIO_CONTENT_SID", default="")  # [ADDED] HX... if you want fallback
TWILIO_USE_TEMPLATE = config("TWILIO_USE_TEMPLATE", cast=bool, default=False)  # [ADDED]

client = Client(account_sid, auth_token)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _wa(n: str) -> str:
    """Ensure the whatsapp: prefix is present."""  # [ADDED]
    return n if n.startswith("whatsapp:") else f"whatsapp:{n}"

def send_message(
    to_number: str,
    body_text: Optional[str] = None,
    *,
    media_urls: Optional[List[str]] = None,     # [ADDED] send PDFs/images via URL
    use_template: Optional[bool] = None,        # [ADDED] override per call; default uses env flag
    template_sid: Optional[str] = None,         # [ADDED] HX... (Twilio Content SID)
    template_vars: Optional[dict] = None,       # [ADDED] {"1": "value", ...}
    max_retries: int = 3,
):
    """
    Send a WhatsApp message via Twilio.

    Default behavior: **free-form** message with `body=` (works inside 24h window).
    If `use_template=True` (or TWILIO_USE_TEMPLATE env), sends with `content_sid`.

    Automatic fallback: if Twilio returns a 24-hour window error (e.code in {63016, 63051}),
    and a template SID is available, we retry once with the template.
    """
    use_template = TWILIO_USE_TEMPLATE if use_template is None else use_template
    _from = _wa(twilio_from)
    _to = _wa(to_number)

    for attempt in range(1, max_retries + 1):
        try:
            if use_template:
                # [CHANGED] Explicitly use Content API only when asked
                sid = template_sid or DEFAULT_CONTENT_SID
                if not sid:
                    raise ValueError("Requested template send but no TWILIO_CONTENT_SID/template_sid configured")

                message = client.messages.create(
                    from_=_from,
                    to=_to,
                    content_sid=sid,
                    content_variables=json.dumps(template_vars or {"1": body_text or ""}),
                )
            else:
                # [CHANGED] Default: free-form reply using 'body' (what we want)
                # NOTE: media_urls -> Twilio param is 'media_url'
                message = client.messages.create(
                    from_=_from,
                    to=_to,
                    body=(body_text or ""),
                    media_url=media_urls or None,
                )

            logger.info(f"Message sent OK (attempt {attempt}) SID={message.sid}")
            return message.sid

        except TwilioRestException as e:
            logger.error(
                f"Twilio error (attempt {attempt}) status={getattr(e, 'status', None)} "
                f"code={getattr(e, 'code', None)} msg={e}"
            )

            # [ADDED] 24-hour window fallback to template once
            if getattr(e, "code", None) in {63016, 63051} and not use_template and (template_sid or DEFAULT_CONTENT_SID):
                logger.info("Detected 24-hour window error; retrying once with template send.")
                use_template = True
                # do not increment attempt here; let loop retry
                continue

            if attempt < max_retries:
                time.sleep(2 ** (attempt - 1))
            else:
                raise
