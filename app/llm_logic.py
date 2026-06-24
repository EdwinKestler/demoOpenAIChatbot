from __future__ import annotations

import base64
import json
import logging
import mimetypes
import time
from pathlib import Path

from decouple import config
from openai import BadRequestError, OpenAI

from app.catalog import hardware_anchors_prompt_list

logger = logging.getLogger(__name__)

_openai_client: OpenAI | None = None

_SYS_PROMPT_SALES = (
    "Eres asistente de ventas de la ferretería Freund. Habla español, claro y breve. "
    "Solo atiende consultas de FERRETERÍA (herramientas, materiales, precios, stock, cotizaciones). "
    "Si el usuario pide algo fuera de ese ámbito, redirígelo con 1 oración a nuestro catálogo. "
    "No inventes precios ni stock; usa solo lo indicado por el usuario o reglas del sistema. "
    "Responde en 1–2 oraciones máximo."
)

_OPENAI_MAX_TOKENS = 160
_OPENAI_TEMP = 0.2
_OPENAI_STOP = ["\n\n"]
_TRIM_LEN = 3000

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


def _vision_class_prompt() -> str:
    anchors = hardware_anchors_prompt_list()
    return (
        "Eres un clasificador de imágenes para una ferretería. Analiza la imagen y responde SOLO JSON válido.\n"
        "El JSON debe tener exactamente estas llaves: anchor, description, confidence.\n"
        "anchor debe ser uno de los 'anchors' de nuestro catálogo si aplica; si no aplica, usa null.\n"
        "description: una breve descripción en español de lo que ves (máx. 12 palabras).\n"
        "confidence: número entre 0 y 1 estimando la certeza de la clasificación.\n"
        f"Anchors permitidos: {anchors}.\n"
        "Si hay varias opciones, elige la más relevante para venta.\n"
        "TU RESPUESTA DEBE SER SOLO JSON ESTRICTO SIN TEXTO EXTRA, NI '```', NI 'json:'."
    )


def get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=config("OPENAI_API_KEY"))
    return _openai_client


def _trim(text: str, limit: int = _TRIM_LEN) -> str:
    trimmed = (text or "").strip()
    return trimmed if len(trimmed) <= limit else trimmed[-limit:]


def llm_sales_reply(user_text: str, *, max_retries: int = 3) -> str:
    text = _trim(user_text)
    if not text:
        return ""

    client = get_openai_client()
    for attempt in range(1, max_retries + 1):
        try:
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": _SYS_PROMPT_SALES},
                    {"role": "user", "content": text},
                ],
                max_tokens=_OPENAI_MAX_TOKENS,
                temperature=_OPENAI_TEMP,
                stop=_OPENAI_STOP,
            )
            return (completion.choices[0].message.content or "").strip()
        except Exception:
            if attempt < max_retries:
                time.sleep(2 ** (attempt - 1))

    return ""


def _clamp01(value: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        return 0.0
    return 0.0 if parsed < 0.0 else (1.0 if parsed > 1.0 else parsed)


def _parse_strict_json(raw: str) -> dict:
    text = (raw or "").strip().strip("` \n")
    if text.lower().startswith("json"):
        text = text[4:].lstrip(":").strip()
    data = json.loads(text)

    anchor = data.get("anchor", None)
    if not isinstance(anchor, str):
        anchor = None
    else:
        anchor = anchor.strip().lower()

    description = data.get("description", "")
    if not isinstance(description, str):
        description = ""

    confidence = _clamp01(data.get("confidence", 0.0))
    return {"anchor": anchor, "description": description, "confidence": confidence}


def _to_data_url(local_path: str) -> str:
    path = Path(local_path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Image not found: {local_path}")
    mime, _ = mimetypes.guess_type(str(path))
    if not mime:
        mime = "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def _responses_call_image_gpt5nano(image_ref: str, *, detail: str = "low"):
    client = get_openai_client()
    return client.responses.create(
        model="gpt-5-nano",
        input=[
            {
                "role": "system",
                "content": [
                    {"type": "input_text", "text": _DEV_PROMPT_VISION},
                    {"type": "input_text", "text": _vision_class_prompt()},
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


def _responses_call_image_gpt5(image_ref: str, *, detail: str = "low"):
    client = get_openai_client()
    return client.responses.create(
        model="gpt-5",
        input=[
            {
                "role": "system",
                "content": [
                    {"type": "input_text", "text": _DEV_PROMPT_VISION},
                    {"type": "input_text", "text": _vision_class_prompt()},
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


def llm_classify_image(
    image_reference: str, *, max_retries: int = 3, force_detail: str = "low"
) -> dict:
    last_err = None

    use_data_url = False
    try:
        use_data_url = Path(image_reference).exists()
    except Exception:
        use_data_url = False

    try:
        image_ref = _to_data_url(image_reference) if use_data_url else image_reference
        if use_data_url:
            logger.info("[Vision] Using base64 data URL (local file).")
    except Exception as exc:
        logger.warning("[Vision] Could not convert to data URL, using raw reference. err=%s", exc)
        image_ref = image_reference

    for attempt in range(1, max_retries + 1):
        logger.info("[Vision attempt %s] steps: (1) gpt-5-nano → (2) gpt-5", attempt)

        try:
            response = _responses_call_image_gpt5nano(image_ref, detail=force_detail)
            raw = getattr(response, "output_text", "").strip()
            result = _parse_strict_json(raw)
            logger.info(
                "[Vision OK nano] anchor=%r conf=%.2f",
                result["anchor"],
                result["confidence"],
            )
            return result
        except BadRequestError as exc:
            logger.warning("[nano 400] %s", exc)
            last_err = exc
        except Exception as exc:
            logger.warning("[nano fail] %s: %s", type(exc).__name__, exc)
            last_err = exc

        try:
            response = _responses_call_image_gpt5(image_ref, detail=force_detail)
            raw = getattr(response, "output_text", "").strip()
            result = _parse_strict_json(raw)
            logger.info(
                "[Vision OK gpt-5] anchor=%r conf=%.2f",
                result["anchor"],
                result["confidence"],
            )
            return result
        except BadRequestError as exc:
            logger.warning("[gpt-5 400] %s", exc)
            last_err = exc
        except Exception as exc:
            logger.warning("[gpt-5 fail] %s: %s", type(exc).__name__, exc)
            last_err = exc

        if attempt < max_retries:
            time.sleep(2 ** (attempt - 1))

    logger.error("[Vision FALLBACK] returning defaults after retries. last_err=%s", last_err)
    return {"anchor": None, "description": "", "confidence": 0.0}