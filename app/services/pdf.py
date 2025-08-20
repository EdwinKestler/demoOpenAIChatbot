# Filename: app/services/pdf.py
# Approx lines modified: ~1-50
# Reason: Save PDFs under a public folder and return (path, filename) so we can build a media_url.

import os
from fpdf import FPDF

def generate_pdf(content: str, out_dir: str = ".") -> tuple[str, str]:  # [CHANGED] return (path, filename)
    os.makedirs(out_dir, exist_ok=True)  # [ADDED]
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
    filename = "cotizacion.pdf"                     # [CHANGED]
    file_path = os.path.join(out_dir, filename)     # [CHANGED]
    pdf.output(file_path)
    return file_path, filename                      # [CHANGED]
