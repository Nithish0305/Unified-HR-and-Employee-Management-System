from fpdf import FPDF
from datetime import datetime
import os

def generate_promotion_pdf(promotion_doc, output_dir="promotion_pdfs"):
    os.makedirs(output_dir, exist_ok=True)
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    # Professional promotion letter format
    pdf.cell(200, 10, txt="Company Name", ln=True, align="C")
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 10, txt="Company Address Line 1", ln=True, align="C")
    pdf.cell(200, 10, txt="Company Address Line 2", ln=True, align="C")
    pdf.ln(20)
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Date: {}".format(datetime.now().strftime('%B %d, %Y')), ln=True)
    pdf.ln(10)
    pdf.cell(200, 10, txt=f"To,", ln=True)
    pdf.cell(200, 10, txt=f"{promotion_doc['employee_id']}", ln=True)
    pdf.ln(10)
    pdf.multi_cell(0, 10, txt=(
        f"Subject: Promotion to {promotion_doc['new_role']}\n\n"
        f"Dear Employee,\n\n"
        f"We are pleased to inform you that, in recognition of your outstanding performance and dedication, you have been promoted from {promotion_doc['old_role']} to {promotion_doc['new_role']}. "
        f"This promotion will be effective from {promotion_doc['effective_date']}.\n\n"
        f"Your new responsibilities will include greater leadership and strategic involvement in your department. We are confident that you will excel in your new role and continue to contribute significantly to the success of our organization.\n\n"
        f"Please accept our heartfelt congratulations on this achievement.\n\n"
        f"Approved By: {promotion_doc.get('approved_by', 'N/A')}\n"
        f"Remarks: {promotion_doc.get('approval_remarks', '')}\n"
        f"\nBest Regards,\nHR Department\nCompany Name"
    ))
    filename = f"promotion_{promotion_doc['promotion_id']}.pdf"
    pdf_path = os.path.join(output_dir, filename)
    pdf.output(pdf_path)
    return pdf_path
