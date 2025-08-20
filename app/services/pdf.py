import os
from fpdf import FPDF

def generate_pdf(content):
    class PDF(FPDF):
        def header(self):
            self.set_font('Arial', 'B', 15)
            self.cell(80)
            self.cell(30, 10, 'Cotizacion', 1, 0, 'C')
            self.ln(20)
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, content)
    file_name = os.path.join("cotizacion.pdf")
    pdf.output(file_name)
    return file_name
