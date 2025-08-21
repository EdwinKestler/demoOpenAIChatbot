# Filename: app/main.py
# Approx lines modified: ~1-60 (imports), ~150-260 (webhook media branch), ~300-360 (DB query for product)
# Reason:
#  - Handle incoming images: download from Twilio, re-host under /public, classify with OpenAI Vision
#  - If anchor ∈ HARDWARE_ANCHORS → fetch Product from Postgres and reply with product photo
#  - Example path for martillo test included

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

from app.models import Conversation, Product                # [CHANGED] import Product
from app.database import SessionLocal, Base, engine
from app.utils import send_message, logger
from app.utils import download_twilio_media_to_public       # [ADDED] to fetch Twilio images
from app.services.pdf import generate_pdf
from app.llm_logic import llm_sales_reply, llm_classify_image  # [ADDED] vision classify

app = FastAPI()

# Serve static + public (for media)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/public", StaticFiles(directory="public"), name="public")
templates = Jinja2Templates(directory="app/templates")

PUBLIC_BASE_URL = config("PUBLIC_BASE_URL", default="")  # e.g., https://xxxx.ngrok-free.app

# Guardrails/menu text
HARDWARE_MENU = (
    "¿Qué necesitas? Ejemplos: martillos, taladros, brocas, lijas, tornillos, pintura, mangueras, "
    "tubería PVC, guantes, cascos, silicón."
)
REPLY_OFF_TOPIC = "Puedo ayudarte con productos de ferretería (precios, stock, cotizaciones). " + HARDWARE_MENU
REPLY_DONT_KNOW = "Puedo ayudarte con productos de ferretería. " + HARDWARE_MENU

# Keep this in sync with llm prompt anchors
_HARDWARE_ANCHORS = [
    "martillo", "taladro", "broca", "lija", "tornillo", "pintura", "manguera", "tubería", "tuberia",
    "pvc", "guantes", "casco", "silicón", "silicon", "cinta", "escuadra", "tuerca", "perno",
    "alicate", "destornillador", "sierra", "pegamento", "adhesivo", "cemento", "yeso", "lamina",
    "cable", "multímetro", "multimetro", "escalera", "llave inglesa",
]

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
        Base.metadata.create_all(bind=engine)  # #comments: creates Product table if missing
        logger.info("Database tables ensured on startup.")
    except Exception as e:
        logger.error(f"DB init failed at startup: {e}")

@app.get("/")
def root():
    return RedirectResponse(url="/conversations")

# ... (conversations UI unchanged) ...

# -------------------- WhatsApp webhook -------------------- #
@app.post("/message")
async def reply(
    Body: str = Form(...),
    From_: str = Form(..., alias="From"),
    To: str = Form(..., alias="To"),
    NumMedia: str = Form("0"),                      # [ADDED] Twilio media count
    MediaUrl0: Optional[str] = Form(None),          # [ADDED] First media URL
    MediaContentType0: Optional[str] = Form(None),  # [ADDED] First media content type (e.g., image/jpeg)
    db: Session = Depends(get_db),
):
    """
    New behavior for images:
      - If the user sends an image, we download it from Twilio, re-host under /public,
        pass that PUBLIC URL to OpenAI Vision, and expect JSON with {anchor, description, confidence}.
      - If anchor ∈ HARDWARE_ANCHORS, we look up Product in Postgres and reply with price/stock
        and attach the product.photo (image_url) from DB.
    """

    text = Body.strip()
    if len(text) > TRIM_LEN:
        text = text[-TRIM_LEN:]
    lower = text.lower()
    n_media = _safe_int(NumMedia)

    # (1) IMAGE HANDLING BRANCH
    if n_media > 0 and MediaContentType0 and MediaContentType0.startswith("image/"):
        # 1.a Download from Twilio to ./public for an accessible URL
        try:
            local_path, filename, public_url = download_twilio_media_to_public(MediaUrl0, out_dir="public")
        except Exception as e:
            logger.error(f"Failed downloading media: {e}")
            msg = "Recibí tu imagen, pero tuve un problema al procesarla. ¿Puedes describir el producto?"
            _send_and_store(db, From_, Body, msg)
            return JSONResponse({"ok": True})

        if not public_url:
            msg = "Recibí tu imagen. Para analizarla, necesito PUBLIC_BASE_URL configurado."
            _send_and_store(db, From_, Body, msg)
            return JSONResponse({"ok": True})

        # 1.b Classify with OpenAI Vision → JSON {anchor, description, confidence}
        result = llm_classify_image(public_url)
        anchor = (result.get("anchor") or "").strip().lower()
        description = result.get("description") or ""
        confidence = float(result.get("confidence") or 0.0)

        # 1.c If we recognize an anchor we sell → fetch from DB and reply attaching product image
        if anchor in _HARDWARE_ANCHORS:
            product = db.query(Product).filter(Product.anchor == anchor).first()
            if product:
                price_usd = product.price_cents / 100.0
                # #comments: Build a short, sales-friendly reply
                reply_text = (
                    f"Puedo venderte: {description} ({anchor}). "
                    f"Tenemos {product.name}: ${price_usd:.2f}, stock {product.stock}."
                )
                media_list = [product.image_url] if product.image_url else None
                _send_and_store(db, From_, Body, reply_text, media_urls=media_list)
                return JSONResponse({"ok": True})
            else:
                # #comments: Anchor recognized but not in DB
                reply_text = (
                    f"Identifiqué {description} ({anchor}). "
                    "Aún no lo tengo cargado en inventario. ¿Deseas una cotización?"
                )
                _send_and_store(db, From_, Body, reply_text)
                return JSONResponse({"ok": True})
        else:
            # #comments: Not a hardware item from our catalog
            reply_text = (
                "Gracias por la imagen. No identifiqué un producto de ferretería de nuestro catálogo. "
                + HARDWARE_MENU
            )
            _send_and_store(db, From_, Body, reply_text)
            return JSONResponse({"ok": True})

    # (2) SIMPLE KEYWORDS WITHOUT LLM (example)
    if "precio" in lower and "martillo" in lower:
        # #comments: demo fallback when no image present
        p = db.query(Product).filter(Product.anchor == "martillo").first()
        if p:
            price_usd = p.price_cents / 100.0
            msg = f"El {p.name} cuesta ${price_usd:.2f} y hay {p.stock} en stock."
            media_list = [p.image_url] if p.image_url else None
            _send_and_store(db, From_, Body, msg, media_urls=media_list)
        else:
            _send_and_store(db, From_, Body, "Martillo disponible. ¿Deseas una cotización?")
        return JSONResponse({"ok": True})

    # (3) COTIZACIÓN FLOW (unchanged demo)
    if any(k in lower for k in ("cotización", "cotizacion", "presupuesto")):
        content = "Detalle de Cotización:\nMartillo demo $3.00, 4 unidades."
        _, pdf_name = generate_pdf(content, out_dir="public")
        media_url = f"{PUBLIC_BASE_URL}/public/{pdf_name}" if PUBLIC_BASE_URL else None
        msg = "Te envío la cotización en PDF adjunta." if media_url else "Generé la cotización (revisa /public)."
        _send_and_store(db, From_, Body, msg, media_urls=[media_url] if media_url else None)
        return JSONResponse({"ok": True})

    # (4) OTHERWISE → one LLM text turn
    chat_response = llm_sales_reply(text) or REPLY_DONT_KNOW
    _send_and_store(db, From_, Body, chat_response)
    return JSONResponse({"ok": True})

# ----------------- Helpers ----------------- #
def _send_and_store(db: Session, to_number: str, user_msg: str, reply_text: str, *, media_urls=None) -> None:
    try:
        send_message(to_number, reply_text, media_urls=media_urls)
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

