import os

os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_CATALOG_USER", "test")
os.environ.setdefault("DB_CATALOG_PASSWORD", "test")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "ACtest")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-token")
os.environ.setdefault("TWILIO_NUMBER", "whatsapp:+10000000000")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "secret")
os.environ.setdefault("TWILIO_VALIDATE_SIGNATURE", "false")
os.environ.setdefault("PUBLIC_BASE_URL", "http://testserver")

import pytest


@pytest.fixture(autouse=True)
def reset_clients():
    import app.llm_logic as llm_logic
    import app.utils as utils

    llm_logic._openai_client = None
    utils._twilio_client = None
    utils._twilio_account_sid.cache_clear()
    utils._twilio_auth_token.cache_clear()
    utils._twilio_from_number.cache_clear()
    utils._default_content_sid.cache_clear()
    utils._twilio_use_template.cache_clear()
    utils._public_base_url.cache_clear()
    yield