# Filename: app/utils.py
# Approx lines modified: ~1-180
# Reason:
#  - ADD helper to download Twilio media (requires HTTP Basic Auth) and save into ./public
#  - RETURN the local path, filename and public URL so we can pass it to OpenAI Vision and WA
#  - Reuse existing Twilio/env config; read PUBLIC_BASE_URL for public link composition.

import logging
import time
import json
import os                 # [ADDED]
import uuid               # [ADDED]
import requests           # [ADDED] to fetch Twilio media with basic auth
from typing import Optional, List

from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from decouple import config

# Twilio credentials from environment
account_sid = config("TWILIO_ACCOUNT_SID")
auth_token = config("TWILIO_AUTH_TOKEN")
twilio_from = config("TWILIO_NUMBER")
DEFAULT_CONTENT_SID = config("TWILIO_CONTENT_SID", default="")
TWILIO_USE_TEMPLATE = config("TWILIO_USE_TEMPLATE", cast=bool, default=False)
PUBLIC_BASE_URL = config("PUBLIC_BASE_URL", default="")  # [ADDED] used to build public file URL

client = Client(account_sid, auth_token)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _wa(n: str) -> str:
    """Ensure the whatsapp: prefix is present."""
    return n if n.startswith("whatsapp:") else f"whatsapp:{n}"

def send_message(
    to_number: str,
    body_text: Optional[str] = None,
    *,
    media_urls: Optional[List[str]] = None,
    use_template: Optional[bool] = None,
    template_sid: Optional[str] = None,
    template_vars: Optional[dict] = None,
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
            
# ---------------- NEW HELPER: Download WA image to public ---------------- #
def download_twilio_media_to_public(media_url: str, out_dir: str = "public") -> tuple[str, str, Optional[str]]:
    """
    Download a Twilio-hosted media (requires basic auth) and save under ./public
    Returns: (file_path, filename, public_url or None)
    - file_path: local absolute/relative path saved
    - filename: basename saved under out_dir
    - public_url: PUBLIC_BASE_URL + /public/filename if base is configured, else None
    """
    os.makedirs(out_dir, exist_ok=True)  #comments: ensure folder exists
    # Twilio media URLs often lack filename, so we generate one with uuid and keep jpg extension by default.
    fname = f"{uuid.uuid4().hex}.jpg"  # #comments: you may detect content-type to pick extension
    fpath = os.path.join(out_dir, fname)

    # #comments: Twilio requires HTTP Basic Auth (Account SID, Auth Token)
    resp = requests.get(media_url, auth=(account_sid, auth_token), timeout=20)
    resp.raise_for_status()
    with open(fpath, "wb") as f:
        f.write(resp.content)

    public_url = f"{PUBLIC_BASE_URL}/public/{fname}" if PUBLIC_BASE_URL else None
    logger.info(f"Saved media to {fpath} public_url={public_url}")
    return fpath, fname, public_url