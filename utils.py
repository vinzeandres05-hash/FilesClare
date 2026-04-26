import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

def generate_receipt_pdf(data):
    # Gawa ng PDF sa memory buffer
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    
    # PDF Design / Layout
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 750, "OFFICIAL PAYMENT RECEIPT")
    p.line(100, 742, 500, 742)
    
    p.setFont("Helvetica", 12)
    p.drawString(100, 710, f"Receipt ID: RCPT-{data['id']}")
    p.drawString(100, 690, f"Date: {data['date_uploaded']}")
    p.drawString(100, 670, f"Reference No: {data['reference_no']}")
    
    p.drawString(100, 630, "Document Requested:")
    p.setFont("Helvetica-Bold", 12)
    p.drawString(250, 630, f"{data['document']}")
    
    p.setFont("Helvetica", 12)
    p.drawString(100, 610, "Amount Paid:")
    p.setFont("Helvetica-Bold", 12)
    p.drawString(250, 610, f"PHP {data['final_price']}")
    
    p.setFont("Helvetica-Oblique", 10)
    p.drawString(100, 560, "Status: TRANSACTION COMPLETED")
    p.drawString(100, 545, "Thank you for your payment!")
    
    p.showPage()
    p.save()
    
    buffer.seek(0)
    return buffer