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
import json  # [ADDED] to validate JSON coming back


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

# ---------------- NEW: Vision classification to HARDWARE anchors ---------------- #
# We will ask for STRICT JSON: {"anchor": "...", "description": "...", "confidence": 0-1}

_VISION_CLASS_PROMPT = (
    "Eres un clasificador de imágenes para una ferretería. Analiza la imagen y responde SOLO JSON válido.\n"
    "El JSON debe tener exactamente estas llaves: anchor, description, confidence.\n"
    "anchor debe ser uno de los 'anchors' de nuestro catálogo si aplica; si no aplica, usa null.\n"
    "description: una breve descripción en español de lo que ves (máx. 12 palabras).\n"
    "confidence: número entre 0 y 1 estimando la certeza de la clasificación.\n"
    "Anchors permitidos: martillo, taladro, broca, lija, tornillo, pintura, manguera, tubería, tuberia, pvc, "
    "guantes, casco, silicón, silicon, cinta, escuadra, tuerca, perno, alicate, destornillador, sierra, "
    "pegamento, adhesivo, cemento, yeso, lamina, cable, multímetro, multimetro, escalera, llave inglesa.\n"
    "Si hay varias opciones, elige la más relevante para venta."
)

def llm_classify_image(public_image_url: str, *, max_retries: int = 3) -> dict:
    """
    Send a public image URL to OpenAI Vision and request STRICT JSON.
    Returns: dict with keys: anchor (str|None), description (str), confidence (float)
    """
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            completion = _client.chat.completions.create(
                model="gpt-4o-mini",  # #comments: 4o-mini accepts image_url inputs; cheap & fast
                messages=[
                    {"role": "system", "content": _VISION_CLASS_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Clasifica esta imagen y responde SOLO JSON válido."},
                            {"type": "image_url", "image_url": {"url": public_image_url}},
                        ],
                    },
                ],
                max_tokens=180,          # #comments: enough to emit short JSON
                temperature=0.0,         # #comments: deterministic JSON
                stop=None,               # #comments: no stop; we force JSON via prompt
            )
            raw = (completion.choices[0].message.content or "").strip()
            # #comments: Some models wrap JSON in code fences; try to extract
            raw = raw.strip("` \n")
            if raw.lower().startswith("json"):
                raw = raw[4:].lstrip(":").strip()
            data = json.loads(raw)
            # #comments: Minimal schema sanitation
            anchor = data.get("anchor")
            if anchor is None:
                pass
            elif isinstance(anchor, str):
                anchor = anchor.strip().lower()
                data["anchor"] = anchor
            else:
                data["anchor"] = None
            if "description" not in data or not isinstance(data["description"], str):
                data["description"] = ""
            conf = data.get("confidence", 0)
            try:
                data["confidence"] = float(conf)
            except Exception:
                data["confidence"] = 0.0
            return data
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                time.sleep(2 ** (attempt - 1))
    # Fallback if totally failed
    return {"anchor": None, "description": "", "confidence": 0.0}