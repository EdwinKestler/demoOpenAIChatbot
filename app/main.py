# Filename: app/main.py
# Approx lines modified: ~1-40 (imports & removed OpenAI client), ~60-95 (removed SYS_PROMPT & OpenAI constants),
# ~170-210 (LLM call site), minor comments; rest unchanged.
# Reason:
#  - Import `llm_sales_reply` from new module app/llm_logic.py
#  - Remove OpenAI client and LLM constants from this file
#  - Keep off-topic/image/cotización logic here
#  - Maintain early input trim (local) and post-LLM off-topic guard

import time
import re
from typing import Optional

from fastapi import FastAPI, Form, Depends, Request, Query
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from decouple import config
from sqlalchemy import or_, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

# [DELETED] from openai import OpenAI
# [DELETED] OpenAI client construction here; moved to app/llm_logic.py

from app.models import Conversation
from app.database import SessionLocal, Base, engine
from app.utils import send_message, logger
from app.services.pdf import generate_pdf  # [CHANGED] ensure correct import path for your project layout
from app.llm_logic import llm_sales_reply  # [ADDED] centralized LLM entry-point

app = FastAPI()

# Serve static + public (for media)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/public", StaticFiles(directory="public"), name="public")
templates = Jinja2Templates(directory="app/templates")

PUBLIC_BASE_URL = config("PUBLIC_BASE_URL", default="")  # e.g., https://xxxx.ngrok-free.app

# ----------------------------
# SALES guardrails & menu
# ----------------------------

# [DELETED ~60-80] SYS_PROMPT_SALES and OpenAI constants (now in app/llm_logic.py)

# [UNCHANGED] concise “menu”
HARDWARE_MENU = (
    "¿Qué necesitas? Ejemplos: martillos, taladros, brocas, lijas, tornillos, pintura, mangueras, "
    "tubería PVC, guantes, cascos, silicón."
)

# [UNCHANGED] default short replies
REPLY_IMAGE_RECEIVED = (
    "Gracias por la imagen. Por ahora no analizo fotos. ¿Buscas un producto similar? " + HARDWARE_MENU
)
REPLY_OFF_TOPIC = (
    "Puedo ayudarte con productos de ferretería (precios, stock, cotizaciones). " + HARDWARE_MENU
)
REPLY_DONT_KNOW = "Puedo ayudarte con productos de ferretería. " + HARDWARE_MENU

# [UNCHANGED] local early trim keeps webhook payloads bounded
TRIM_LEN = 3000

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.on_event("startup")
def on_startup():
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables ensured on startup.")
    except Exception as e:
        logger.error(f"DB init failed at startup: {e}")

@app.get("/")
def root():
    return RedirectResponse(url="/conversations")

@app.get("/conversations")
def conversations_page(
    request: Request,
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    base_query = db.query(Conversation)
    if q:
        like = f"%{q}%"
        base_query = base_query.filter(
            or_(
                Conversation.sender.ilike(like),
                Conversation.message.ilike(like),
                Conversation.response.ilike(like),
            )
        )

    total = db.query(func.count()).select_from(base_query.subquery()).scalar()
    items = (
        base_query.order_by(Conversation.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    total_pages = max((total + per_page - 1) // per_page, 1)

    return templates.TemplateResponse(
        "conversations.html",
        {
            "request": request,
            "items": items,
            "q": q or "",
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
    )

# ---------------------------------
# WhatsApp webhook w/ intent routing
# ---------------------------------
@app.post("/message")
async def reply(
    Body: str = Form(...),
    From_: str = Form(..., alias="From"),
    To: str = Form(..., alias="To"),
    # Twilio media fields (first media only; extend N as needed)
    NumMedia: str = Form("0"),
    MediaUrl0: Optional[str] = Form(None),
    MediaContentType0: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Prioridad de respuesta:
      1) Si imagen/archivo -> acuse + redirección a ventas (sin LLM).
      2) Si “cotización/cotizacion” -> PDF y envío (si PUBLIC_BASE_URL está definido).
      3) Si intención hardware simple -> responder directo (sin LLM).
      4) Si no concluyente -> UN solo turno LLM (vía app.llm_logic.llm_sales_reply).
      5) Si el LLM deriva -> respuesta de redirección.
    """

    # [UNCHANGED] early trim para controlar tokens si eventualmente pasamos a LLM
    text = Body.strip()
    if len(text) > TRIM_LEN:
        text = text[-TRIM_LEN:]
    lower = text.lower()
    n_media = _safe_int(NumMedia)

    # --- (1) MEDIA HANDLING ---
    if n_media > 0:
        chat_response = REPLY_IMAGE_RECEIVED
        _send_and_store(db, From_, Body, chat_response)
        return JSONResponse({"ok": True})

    # --- (2) COTIZACIÓN FLOW ---
    if _contains_quote_intent(lower):
        content = (
            "Detalle de Cotización:\n"
            "El precio del martillo es de $3 dólares y hay 4 unidades disponibles."
        )
        pdf_path, pdf_name = generate_pdf(content, out_dir="public")  # guarda en ./public

        media_url = None
        if PUBLIC_BASE_URL:
            media_url = f"{PUBLIC_BASE_URL}/public/{pdf_name}"
            chat_response = "Te envío la cotización en PDF adjunta."
        else:
            chat_response = (
                "Generé la cotización, pero falta PUBLIC_BASE_URL para adjuntarla. "
                "Puedes descargarla desde el panel /public."
            )

        try:
            send_message(From_, chat_response, media_urls=[media_url] if media_url else None)
        except Exception as e:
            logger.error(f"Failed to send cotizacion PDF: {e}")

        _store(db, From_, Body, chat_response)
        return JSONResponse({"ok": True})

    # --- (3) KEYWORDS DIRECTOS (sin LLM) ---
    if "precio" in lower and "martillo" in lower:
        chat_response = "El precio del martillo es de $3 dólares y hay 4 unidades disponibles."
        _send_and_store(db, From_, Body, chat_response)
        return JSONResponse({"ok": True})

    # --- OFF-TOPIC rápido (sin LLM) ---
    if _is_off_topic(lower):
        chat_response = REPLY_OFF_TOPIC
        _send_and_store(db, From_, Body, chat_response)
        return JSONResponse({"ok": True})

    # --- (4) ÚNICO TURNO LLM (aislado en app/llm_logic) ---
    chat_response = llm_sales_reply(text)  # [CHANGED] centralizado
    if not chat_response:
        chat_response = REPLY_DONT_KNOW

    # Forzar on-topic si el modelo se desvió
    if _is_off_topic(chat_response.lower()):
        chat_response = REPLY_OFF_TOPIC

    _send_and_store(db, From_, Body, chat_response)
    return JSONResponse({"ok": True})


# -----------------
# Helper functions
# -----------------

def _send_and_store(db: Session, to_number: str, user_msg: str, reply_text: str) -> None:
    """Send WA message and store conversation in DB."""
    try:
        send_message(to_number, reply_text)
    except Exception as e:
        logger.error(f"Failed to send WA message: {e}")
    _store(db, to_number, user_msg, reply_text)

def _store(db: Session, sender: str, message: str, response: str):
    try:
        conversation = Conversation(sender=sender, message=message, response=response)
        db.add(conversation)
        db.commit()
        logger.info("Conversation stored in database.")
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"DB store error: {e}")

def _safe_int(s: str, default: int = 0) -> int:
    try:
        return int(s)
    except Exception:
        return default

# --- Intent heuristics (sin LLM) ---

_OFF_TOPIC_PATTERNS = [
    r"\bseguro(s)?\b", r"\bbanco(s)?\b", r"\bbitcoin\b", r"\bsolana\b", r"\bcript[o|omoneda]",
    r"\bpizza\b", r"\bmedicina\b", r"\bmascota(s)?\b", r"\bdieta\b", r"\bpoema\b",
    r"\balquiler\b", r"\bviaje(s)?\b", r"\bhotel(es)?\b", r"\bmusica\b", r"\bcancion\b",
    r"\bpolitica\b", r"\beleccion(es)?\b", r"\bimpuesto(s)?\b", r"\bllc\b", r"\btarjeta(s)?\b",
]
_HARDWARE_ANCHORS = [
    "martillo", "taladro", "broca", "lija", "tornillo", "pintura", "manguera", "tubería", "tuberia",
    "pvc", "guantes", "casco", "silicón", "silicon", "cinta", "escuadra", "tuerca", "perno",
    "alicate", "destornillador", "sierra", "pegamento", "adhesivo", "cemento", "yeso", "lamina",
    "cable", "multímetro", "multimetro", "escalera", "llave inglesa",
]

def _contains_quote_intent(text: str) -> bool:
    return "cotización" in text or "cotizacion" in text or "presupuesto" in text or "coti" in text

def _is_off_topic(text: str) -> bool:
    for pat in _OFF_TOPIC_PATTERNS:
        if re.search(pat, text):
            return True
    if len(text.split()) >= 4 and not any(a in text for a in _HARDWARE_ANCHORS):
        if not re.search(r"\b(hola|buen[oa]s|qué tal|que tal)\b", text):
            return True
    return False

