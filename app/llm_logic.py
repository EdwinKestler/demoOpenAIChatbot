# Filename: app/llm_logic.py
# New file (~1-120)
# Reason:
#  - Isolate ALL OpenAI LLM logic into a single module for modularity & testing.
#  - Keep token-economy defaults (short system prompt, low max_tokens, stop).
#  - Provide a single public function: `llm_sales_reply()`.

from __future__ import annotations

import time
import json
import logging
import base64                    # [ADDED] for data URL embedding
import mimetypes                 # [ADDED] infer MIME type
from pathlib import Path         # [ADDED] to detect local paths

from decouple import config
from openai import OpenAI, BadRequestError

_client = OpenAI(api_key=config("OPENAI_API_KEY"))
logger = logging.getLogger(__name__)

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

# ---------------- Prompts (unchanged intent, tightened outputs) ----------------
_DEV_PROMPT_VISION = (
    "Developer message\n"
    "# Role and Objective\n"
    "- Implements a multimodal classifier using the GPT-5-nano model to process images and provide structured JSON outputs with classification data.\n"
    "# Instructions\n"
    "- Send prompt to the gpt-5-nano model using the Responses API.\n"
    "- Input consists of a system prompt and a user prompt containing an image and explicit JSON-only reply instruction.\n"
    "- Request minimal reasoning effort and low verbosity to return concise JSON.\n"
    "- Limit output to 180 tokens for predictable structure.\n"
    "- Parse and sanitize the model output (code fences and 'json' labels may appear).\n"
    "- Validate presence/types of keys: anchor (string|null), description (string), confidence (float).\n"
    "- Normalize missing/malformed fields to defaults and clamp confidence to [0.0, 1.0].\n"
    "- No extra commentary; the model MUST output ONLY strict JSON.\n"
)

_VISION_CLASS_PROMPT = (
    "Eres un clasificador de imágenes para una ferretería. Analiza la imagen y responde SOLO JSON válido.\n"
    "El JSON debe tener exactamente estas llaves: anchor, description, confidence.\n"
    "anchor debe ser uno de los 'anchors' de nuestro catálogo si aplica; si no aplica, usa null.\n"
    "description: una breve descripción en español de lo que ves (máx. 12 palabras).\n"
    "confidence: número entre 0 y 1 estimando la certeza de la clasificación.\n"
    "Anchors permitidos: martillo, taladro, broca, lija, tornillo, pintura, manguera, tubería, tuberia, pvc, "
    "guantes, casco, silicón, silicon, cinta, escuadra, tuerca, perno, alicate, destornillador, sierra, "
    "pegamento, adhesivo, cemento, yeso, lamina, cable, multímetro, multimetro, escalera, llave inglesa.\n"
    "Si hay varias opciones, elige la más relevante para venta.\n"
    "TU RESPUESTA DEBE SER SOLO JSON ESTRICTO SIN TEXTO EXTRA, NI '```', NI 'json:'."
)

# ---------------- Utilities ----------------
def _clamp01(x: float) -> float:
    """#comments: clamp helper  # app/llm_logic.py ~160"""
    try:
        xf = float(x)
    except Exception:
        return 0.0
    return 0.0 if xf < 0.0 else (1.0 if xf > 1.0 else xf)

def _parse_strict_json(raw: str) -> dict:
    """
    #comments: strip possible code fences / 'json' prefix and enforce schema  # ~175
    """
    s = (raw or "").strip().strip("` \n")
    if s.lower().startswith("json"):
        s = s[4:].lstrip(":").strip()
    data = json.loads(s)  # may raise

    anchor = data.get("anchor", None)
    if not isinstance(anchor, str):
        anchor = None
    else:
        anchor = anchor.strip().lower()

    description = data.get("description", "")
    if not isinstance(description, str):
        description = ""

    conf = _clamp01(data.get("confidence", 0.0))
    return {"anchor": anchor, "description": description, "confidence": conf}

def _to_data_url(local_path: str) -> str:
    """
    #comments: convert LOCAL image → data URL to avoid external fetch timeouts  # ~200
    """
    p = Path(local_path)
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"Image not found: {local_path}")
    mime, _ = mimetypes.guess_type(str(p))
    if not mime:
        mime = "image/jpeg"  # safe default
    b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{b64}"

# ---------------- Responses API callers (IMPORTANT: use 'input_text') ----------------
def _responses_call_image_gpt5nano(image_ref: str, *, detail: str = "low"):
    """
    #comments: GPT‑5‑nano, multimodal via Responses API; supports URL or data URL in image_url  # ~220
    """
    return _client.responses.create(
        model="gpt-5-nano",                      # [SET] target model
        input=[
            {
                "role": "system",
                "content": [
                    {"type": "input_text", "text": _DEV_PROMPT_VISION},    # [FIXED] was "text"
                    {"type": "input_text", "text": _VISION_CLASS_PROMPT},  # [FIXED] was "text"
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Clasifica esta imagen y responde SOLO JSON válido."},
                    {"type": "input_image", "image_url": image_ref, "detail": detail},  # "low" saves tokens
                ],
            },
        ],
        reasoning={"effort": "minimal"},         # [PER SPEC] minimal reasoning
        text={"verbosity": "low"},               # [PER SPEC] low verbosity
        max_output_tokens=180,                   # [PER SPEC] hard cap
    )

def _responses_call_image_gpt5(image_ref: str, *, detail: str = "low"):
    """
    #comments: fallback to larger sibling gpt‑5 if -nano refuses  # ~255
    """
    return _client.responses.create(
        model="gpt-5",
        input=[
            {
                "role": "system",
                "content": [
                    {"type": "input_text", "text": _DEV_PROMPT_VISION},
                    {"type": "input_text", "text": _VISION_CLASS_PROMPT},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Clasifica esta imagen y responde SOLO JSON válido."},
                    {"type": "input_image", "image_url": image_ref, "detail": detail},
                ],
            },
        ],
        reasoning={"effort": "minimal"},
        text={"verbosity": "low"},
        max_output_tokens=180,
    )

# ---------------- Public entrypoint ----------------
def llm_classify_image(image_reference: str, *, max_retries: int = 3, force_detail: str = "low") -> dict:
    """
    #comments: Accepts a LOCAL FILE PATH or an HTTP(S) URL.               # ~290
    #comments: If local, we embed it as data URL (preferred).             # ~291
    #comments: Returns dict: {anchor: str|None, description: str, confidence: float in [0,1]}
    """
    last_err = None

    # Decide local vs url
    use_data_url = False
    try:
        use_data_url = Path(image_reference).exists()
    except Exception:
        use_data_url = False

    try:
        img_ref = _to_data_url(image_reference) if use_data_url else image_reference
        if use_data_url:
            logger.info("[Vision] Using base64 data URL (local file).")
    except Exception as e:
        logger.warning(f"[Vision] Could not convert to data URL, using raw reference. err={e}")
        img_ref = image_reference

    for attempt in range(1, max_retries + 1):
        logger.info(f"[Vision attempt {attempt}] steps: (1) gpt-5-nano → (2) gpt-5")

        # (1) gpt-5-nano
        try:
            r = _responses_call_image_gpt5nano(img_ref, detail=force_detail)
            raw = getattr(r, "output_text", "").strip()
            result = _parse_strict_json(raw)
            logger.info(f"[Vision OK nano] anchor={result['anchor']!r} conf={result['confidence']:.2f}")
            return result
        except BadRequestError as e:
            body_text = ""
            try:
                body_text = getattr(getattr(e, "response", None), "text", "") or ""
            except Exception:
                pass
            logger.warning(f"[nano 400] {e} body={body_text[:400]}")
            last_err = e
        except Exception as e:
            logger.warning(f"[nano fail] {type(e).__name__}: {e}")
            last_err = e

        # (2) gpt-5 fallback
        try:
            r = _responses_call_image_gpt5(img_ref, detail=force_detail)
            raw = getattr(r, "output_text", "").strip()
            result = _parse_strict_json(raw)
            logger.info(f"[Vision OK gpt-5] anchor={result['anchor']!r} conf={result['confidence']:.2f}")
            return result
        except BadRequestError as e:
            body_text = ""
            try:
                body_text = getattr(getattr(e, "response", None), "text", "") or ""
            except Exception:
                pass
            logger.warning(f"[gpt-5 400] {e} body={body_text[:400]}")
            last_err = e
        except Exception as e:
            logger.warning(f"[gpt-5 fail] {type(e).__name__}: {e}")
            last_err = e

        if attempt < max_retries:
            time.sleep(2 ** (attempt - 1))

    logger.error(f"[Vision FALLBACK] returning defaults after retries. last_err={last_err}")
    return {"anchor": None, "description": "", "confidence": 0.0}