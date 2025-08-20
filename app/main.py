# Third-party imports
import openai
import time
from fastapi import FastAPI, Form, Depends
from fastapi.responses import FileResponse
from decouple import config
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

# Internal imports
from app.models import Conversation
from app.database import SessionLocal
from app.utils import send_message, logger
from app.services.pdf import generate_pdf

app = FastAPI()
# Set up the OpenAI API client
openai.api_key = config("OPENAI_API_KEY")
whatsapp_number = config("TO_NUMBER")

# Dependency
def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()

@app.post("/message")
async def reply(Body: str = Form(), db: Session = Depends(get_db)):
    # Call the OpenAI API to generate text with GPT-4
    if "precio" in Body.lower() and "martillo" in Body.lower():
        chat_response = "El precio del martillo es de $3 dólares y hay 4 unidades disponibles."
    elif "cotización" in Body.lower():
        content = "Detalle de Cotización:\nEl precio del martillo es de $3 dólares y hay 4 unidades disponibles."
        pdf_file_path = generate_pdf(content)
        return FileResponse(pdf_file_path, media_type="application/pdf", filename="/cotizacion.pdf")
    else:
        chat_response = ""
        for attempt in range(3):
            try:
                completion = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Eres un asistente virtual de la ferreteria Freund identifica si te piden herramienta y cuales son los precios"
                            ),
                        },
                        {"role": "user", "content": Body},
                    ],
                    max_tokens=1000,
                    timeout=15,
                )
                chat_response = completion.choices[0].message['content']
                break
            except openai.error.OpenAIError as e:
                logger.error(
                    f"OpenAI API call failed on attempt {attempt + 1} for input '{Body}': {e}"
                )
                if attempt < 2:
                    time.sleep(2 ** attempt)
        else:
            chat_response = "Lo siento, no puedo responder en este momento."

    # Store the conversation in the database
    try:
        conversation = Conversation(
            sender=whatsapp_number,
            message=Body,
            response=chat_response
        )
        db.add(conversation)
        db.commit()
        logger.info(f"Conversation #{conversation.id} stored in database")
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error storing conversation in database: {e}")
    send_message(whatsapp_number, chat_response)
    return ""
