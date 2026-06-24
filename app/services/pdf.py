import os
import uuid

from fpdf import FPDF


def generate_pdf(content: str, out_dir: str = ".") -> tuple[str, str]:
    os.makedirs(out_dir, exist_ok=True)

    class PDF(FPDF):
        def header(self):
            self.set_font("Arial", "B", 15)
            self.cell(80)
            self.cell(30, 10, "Cotizacion", 1, 0, "C")
            self.ln(20)

    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, content)
    filename = f"cotizacion_{uuid.uuid4().hex}.pdf"
    file_path = os.path.join(out_dir, filename)
    pdf.output(file_path)
    return file_path, filename