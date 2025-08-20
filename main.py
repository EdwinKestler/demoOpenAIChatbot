# Third-party imports
import openai
import os
from fastapi import FastAPI, Form, Depends
from fastapi.responses import FileResponse
from decouple import config
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

# Internal imports
from models import Conversation, SessionLocal
from utils import send_message, logger

from fpdf import FPDF

current_directory = os.getcwd()
print(current_directory)

def generate_pdf(content):
    class PDF(FPDF):
        def header(self):
            # Seleccionar fuente Arial bold 15
            self.set_font('Arial', 'B', 15)
            # Mover a la derecha
            self.cell(80)
            # Título
            self.cell(30, 10, 'Cotizacion', 1, 0, 'C')
            # Salto de línea
            self.ln(20)

    # Instancia de la clase para construir el PDF
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size = 12)
    pdf.multi_cell(0, 10, content)
    
    file_name = os.path.join("cotizacion.pdf") 

    pdf.output(file_name)
    return file_name


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
        print(pdf_file_path)
        return FileResponse(pdf_file_path, media_type="application/pdf", filename="/cotizacion.pdf")
    else:
        completion = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Eres un asistente virtual de la ferreteria Freund identifica si te piden herramienta y cuale son los precios"},
                {"role": "user", "content": Body}
            ],
            max_tokens=1000,
        )
        chat_response = completion.choices[0].message['content']


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
