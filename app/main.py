from contextlib import asynccontextmanager
from typing import Optional

from decouple import config
from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.catalog import HARDWARE_ANCHORS
from app.database import (
    CatalogBase,
    CatalogSessionLocal,
    ChatBase,
    ChatSessionLocal,
    catalog_engine,
    chat_engine,
)
from app.llm_logic import llm_classify_image, llm_sales_reply
from app.models import Conversation, Product
from app.security import LimitBodySizeMiddleware, validate_twilio_signature, verify_admin
from app.services.pdf import generate_pdf
from app.utils import download_twilio_media_to_public, logger, send_message

PUBLIC_BASE_URL = config("PUBLIC_BASE_URL", default="")
MAX_REQUEST_BODY_BYTES = config("MAX_REQUEST_BODY_BYTES", cast=int, default=1_048_576)

HARDWARE_MENU = (
    "¿Qué necesitas? Ejemplos: martillos, taladros, brocas, lijas, tornillos, pintura, mangueras, "
    "tubería PVC, guantes, cascos, silicón."
)
REPLY_DONT_KNOW = "Puedo ayudarte con productos de ferretería. " + HARDWARE_MENU
TRIM_LEN = 3000


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        ChatBase.metadata.create_all(bind=chat_engine)
        CatalogBase.metadata.create_all(bind=catalog_engine)
        logger.info("Database tables ensured on startup for both DBs.")
    except Exception as exc:
        logger.error("DB init failed at startup: %s", exc)
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(LimitBodySizeMiddleware, max_bytes=MAX_REQUEST_BODY_BYTES)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/public", StaticFiles(directory="public"), name="public")
templates = Jinja2Templates(directory="app/templates")


def get_chat_db():
    db = ChatSessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_catalog_db():
    db = CatalogSessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return RedirectResponse(url="/conversations")


@app.get("/conversations")
async def list_conversations(
    request: Request,
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=200),
    db: Session = Depends(get_chat_db),
    _: str = Depends(verify_admin),
):
    query = db.query(Conversation)
    if q:
        q_lower = f"%{q.lower()}%"
        query = query.filter(
            or_(
                func.lower(Conversation.sender).like(q_lower),
                func.lower(Conversation.message).like(q_lower),
                func.lower(Conversation.response).like(q_lower),
            )
        )
    total = query.count()
    items = (
        query.order_by(Conversation.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    total_pages = (total + per_page - 1) // per_page if per_page > 0 else 1
    return templates.TemplateResponse(
        "conversations.html",
        {
            "request": request,
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "q": q or "",
        },
    )


@app.get("/api/conversations")
async def api_list_conversations(
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=200),
    db: Session = Depends(get_chat_db),
    _: str = Depends(verify_admin),
):
    query = db.query(Conversation)
    if q:
        q_lower = f"%{q.lower()}%"
        query = query.filter(
            or_(
                func.lower(Conversation.sender).like(q_lower),
                func.lower(Conversation.message).like(q_lower),
                func.lower(Conversation.response).like(q_lower),
            )
        )
    total = query.count()
    items = (
        query.order_by(Conversation.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    total_pages = (total + per_page - 1) // per_page if per_page > 0 else 1
    return {
        "items": [
            {"id": item.id, "sender": item.sender, "message": item.message, "response": item.response}
            for item in items
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "q": q or "",
    }


@app.post("/message")
async def reply(
    request: Request,
    db_chat: Session = Depends(get_chat_db),
    db_catalog: Session = Depends(get_catalog_db),
):
    form = await request.form()
    await validate_twilio_signature(request, form)

    body = str(form.get("Body", "")).strip()
    sender = str(form.get("From", ""))
    num_media = _safe_int(str(form.get("NumMedia", "0")))
    media_url = form.get("MediaUrl0")
    media_content_type = form.get("MediaContentType0")

    if len(body) > TRIM_LEN:
        body = body[-TRIM_LEN:]
    lower = body.lower()

    if num_media > 0 and media_content_type and str(media_content_type).startswith("image/"):
        try:
            local_path, _, public_url = download_twilio_media_to_public(
                str(media_url), out_dir="public"
            )
        except Exception as exc:
            logger.error("Failed downloading media: %s", exc)
            msg = "Recibí tu imagen, pero tuve un problema al procesarla. ¿Puedes describir el producto?"
            _send_and_store(db_chat, sender, body, msg)
            return JSONResponse({"ok": True})

        image_ref_for_llm = local_path if local_path else (public_url or "")
        result = llm_classify_image(image_ref_for_llm, max_retries=3, force_detail="low")
        anchor = (result.get("anchor") or "").strip().lower()
        description = result.get("description") or ""

        if anchor in HARDWARE_ANCHORS:
            product = db_catalog.query(Product).filter(Product.anchor == anchor).first()
            if product:
                price_usd = product.price_cents / 100.0
                reply_text = (
                    f"Puedo venderte: {description} ({anchor}). "
                    f"Tenemos {product.name}: ${price_usd:.2f}, stock {product.stock}."
                )
                media_list = [product.image_url] if product.image_url else None
                _send_and_store(db_chat, sender, body, reply_text, media_urls=media_list)
                return JSONResponse({"ok": True})

            reply_text = (
                f"Identifiqué {description} ({anchor}). "
                "Aún no lo tengo cargado en inventario. ¿Deseas una cotización?"
            )
            _send_and_store(db_chat, sender, body, reply_text)
            return JSONResponse({"ok": True})

        reply_text = (
            "Gracias por la imagen. No identifiqué un producto de ferretería de nuestro catálogo. "
            + HARDWARE_MENU
        )
        _send_and_store(db_chat, sender, body, reply_text)
        return JSONResponse({"ok": True})

    if "precio" in lower and "martillo" in lower:
        product = db_catalog.query(Product).filter(Product.anchor == "martillo").first()
        if product:
            price_usd = product.price_cents / 100.0
            msg = f"El {product.name} cuesta ${price_usd:.2f} y hay {product.stock} en stock."
            media_list = [product.image_url] if product.image_url else None
            _send_and_store(db_chat, sender, body, msg, media_urls=media_list)
        else:
            _send_and_store(
                db_chat, sender, body, "Martillo disponible. ¿Deseas una cotización?"
            )
        return JSONResponse({"ok": True})

    if any(keyword in lower for keyword in ("cotización", "cotizacion", "presupuesto")):
        content = "Detalle de Cotización:\nMartillo demo $3.00, 4 unidades."
        _, pdf_name = generate_pdf(content, out_dir="public")
        media_url = f"{PUBLIC_BASE_URL}/public/{pdf_name}" if PUBLIC_BASE_URL else None
        msg = (
            "Te envío la cotización en PDF adjunta."
            if media_url
            else "Generé la cotización (revisa /public)."
        )
        _send_and_store(
            db_chat,
            sender,
            body,
            msg,
            media_urls=[media_url] if media_url else None,
        )
        return JSONResponse({"ok": True})

    chat_response = llm_sales_reply(body) or REPLY_DONT_KNOW
    _send_and_store(db_chat, sender, body, chat_response)
    return JSONResponse({"ok": True})


def _send_and_store(
    db: Session,
    to_number: str,
    user_msg: str,
    reply_text: str,
    *,
    media_urls=None,
) -> None:
    try:
        send_message(to_number, reply_text, media_urls=media_urls)
    except Exception as exc:
        logger.error("Failed to send WA message: %s", exc)
    _store(db, to_number, user_msg, reply_text)


def _store(db: Session, sender: str, message: str, response: str) -> None:
    try:
        conversation = Conversation(sender=sender, message=message, response=response)
        db.add(conversation)
        db.commit()
        logger.info("Conversation stored in database.")
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("DB store error: %s", exc)


def _safe_int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default