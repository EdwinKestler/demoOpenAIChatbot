import json
import logging
import os
import time
import uuid
from functools import lru_cache
from typing import List, Optional

import requests
from decouple import config
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@lru_cache
def _twilio_account_sid() -> str:
    return config("TWILIO_ACCOUNT_SID")


@lru_cache
def _twilio_auth_token() -> str:
    return config("TWILIO_AUTH_TOKEN")


@lru_cache
def _twilio_from_number() -> str:
    return config("TWILIO_NUMBER")


@lru_cache
def _default_content_sid() -> str:
    return config("TWILIO_CONTENT_SID", default="")


@lru_cache
def _twilio_use_template() -> bool:
    return config("TWILIO_USE_TEMPLATE", cast=bool, default=False)


@lru_cache
def _public_base_url() -> str:
    return config("PUBLIC_BASE_URL", default="")


_twilio_client: Client | None = None


def get_twilio_client() -> Client:
    global _twilio_client
    if _twilio_client is None:
        _twilio_client = Client(_twilio_account_sid(), _twilio_auth_token())
    return _twilio_client


def _wa(number: str) -> str:
    return number if number.startswith("whatsapp:") else f"whatsapp:{number}"


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
    use_template = _twilio_use_template() if use_template is None else use_template
    client = get_twilio_client()
    sender = _wa(_twilio_from_number())
    recipient = _wa(to_number)

    for attempt in range(1, max_retries + 1):
        try:
            if use_template:
                sid = template_sid or _default_content_sid()
                if not sid:
                    raise ValueError(
                        "Requested template send but no TWILIO_CONTENT_SID/template_sid configured"
                    )
                message = client.messages.create(
                    from_=sender,
                    to=recipient,
                    content_sid=sid,
                    content_variables=json.dumps(template_vars or {"1": body_text or ""}),
                )
            else:
                message = client.messages.create(
                    from_=sender,
                    to=recipient,
                    body=(body_text or ""),
                    media_url=media_urls or None,
                )

            logger.info("Message sent OK (attempt %s) SID=%s", attempt, message.sid)
            return message.sid

        except TwilioRestException as exc:
            logger.error(
                "Twilio error (attempt %s) status=%s code=%s msg=%s",
                attempt,
                getattr(exc, "status", None),
                getattr(exc, "code", None),
                exc,
            )
            if (
                getattr(exc, "code", None) in {63016, 63051}
                and not use_template
                and (template_sid or _default_content_sid())
            ):
                logger.info("Detected 24-hour window error; retrying once with template send.")
                use_template = True
                continue

            if attempt < max_retries:
                time.sleep(2 ** (attempt - 1))
            else:
                raise


def download_twilio_media_to_public(
    media_url: str, out_dir: str = "public"
) -> tuple[str, str, Optional[str]]:
    os.makedirs(out_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.jpg"
    file_path = os.path.join(out_dir, filename)

    response = requests.get(
        media_url,
        auth=(_twilio_account_sid(), _twilio_auth_token()),
        timeout=20,
    )
    response.raise_for_status()
    with open(file_path, "wb") as handle:
        handle.write(response.content)

    public_base = _public_base_url()
    public_url = f"{public_base}/public/{filename}" if public_base else None
    logger.info("Saved media to %s public_url=%s", file_path, public_url)
    return file_path, filename, public_url