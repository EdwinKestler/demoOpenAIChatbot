# Filename: app/llm_logic.py
# New file (~1-120)
# Reason:
#  - Isolate ALL OpenAI LLM logic into a single module for modularity & testing.
#  - Keep token-economy defaults (short system prompt, low max_tokens, stop).
#  - Provide a single public function: `llm_sales_reply()`.

from __future__ import annotations

from decouple import config  # [ADDED] load env OPENAI_API_KEY
from openai import OpenAI    # [ADDED] OpenAI SDK client
import time                  # [ADDED] backoff on transient errors

# [ADDED ~20] Initialize once per process to reuse connections
_client = OpenAI(api_key=config("OPENAI_API_KEY"))

# [ADDED ~25] Short, rules-only system prompt (saves tokens each call)
_SYS_PROMPT_SALES = (
    "Eres asistente de ventas de la ferretería Freund. Habla español, claro y breve. "
    "Solo atiende consultas de FERRETERÍA (herramientas, materiales, precios, stock, cotizaciones). "
    "Si el usuario pide algo fuera de ese ámbito, redirígelo con 1 oración a nuestro catálogo. "
    "No inventes precios ni stock; usa solo lo indicado por el usuario o reglas del sistema. "
    "Responde en 1–2 oraciones máximo."
)

# [ADDED ~35] Token-economy defaults for WhatsApp
_OPENAI_MAX_TOKENS = 160
_OPENAI_TEMP = 0.2
_OPENAI_STOP = ["\n\n"]
_TRIM_LEN = 3000  # defensive trim in case caller forgets

def _trim(text: str, limit: int = _TRIM_LEN) -> str:
    """[ADDED] Keep only last `limit` chars to control prompt size."""
    t = (text or "").strip()
    return t if len(t) <= limit else t[-limit:]

def llm_sales_reply(user_text: str, *, max_retries: int = 3) -> str:
    """
    [ADDED ~55] Single entry-point for LLM sales replies.
    - Keeps on-topic with `_SYS_PROMPT_SALES`
    - Short answers thanks to stop + max_tokens
    - Trims input defensively to protect token budget
    - Retries on transient errors with exponential backoff
    """
    text = _trim(user_text)
    if not text:
        return ""

    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            completion = _client.chat.completions.create(
                model="gpt-4o-mini",  # [UNCHANGED] low-cost default
                messages=[
                    {"role": "system", "content": _SYS_PROMPT_SALES},
                    {"role": "user", "content": text},
                ],
                max_tokens=_OPENAI_MAX_TOKENS,
                temperature=_OPENAI_TEMP,
                stop=_OPENAI_STOP,
            )
            return (completion.choices[0].message.content or "").strip()
        except Exception as e:
            last_err = e
            # [ADDED] Simple exponential backoff
            if attempt < max_retries:
                time.sleep(2 ** (attempt - 1))

    # [ADDED] If we reach here, all attempts failed
    return ""  # caller decides the final fallback
