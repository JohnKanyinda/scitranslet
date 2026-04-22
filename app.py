import streamlit as st
import fitz  # PyMuPDF
import os
import tempfile
import time
from groq import Groq
from reportlab.pdfgen import canvas
from io import BytesIO

# --- CONFIGURATION ---
st.set_page_config(page_title="Sci-Translate Groq", page_icon="⚡", layout="wide")

def translate_engine(text, discipline):
    """Moteur de traduction ultra-rapide avec Llama 3.1 70B sur Groq"""
    try:
        client = Groq(api_key=st.secrets["GROQ_API_KEY"])
        
        # On utilise le modèle 70B car il est bien plus performant pour la science
        response = client.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=[
                {
                    "role": "system", 
                    "content": (
                        f"Tu es un traducteur expert en {discipline}. "
                        "Traduis TOUT le texte de l'anglais vers le français. "
                        "Ne laisse aucune phrase en anglais. "
                        "Réponds uniquement par la traduction française, sans aucun commentaire."
                    )
                },
                {"role": "user", "content": text}
            ],
            temperature=0.2
        )
        return response.choices[0].message.content
    except Exception as e:
        if "429" in str(e): # Erreur de limite de débit (Rate Limit)
            return "RETRY_LATER"
        return f"[Erreur : {str(e)}]"

def create_overlay(text, rect):
    """Crée le calque PDF avec le texte français"""
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(rect.width, rect.height))
    can.setFont("Helvetica", 10)
    to = can.beginText(45, rect.height - 50)
    
    # Découpage intelligent pour éviter que le texte ne dépasse du PDF
    lines = text.split('\n')
    for line in lines:
        words = line.strip().split(' ')
        current_line = ""
        for word in words:
            if len(current_line + word) < 80:
                current_line += word + " "
            else:
                to.textLine(current_line)
                current_line = word + " "
        to.textLine(current_line)
    
    can.drawText(to)
    can.save()
    packet.seek(0)
    return packet

def main():
    st.title("⚡ Sci-Translate : Version Groq (Llama 3.1)")
    st.info("Utilisation de l'API Groq pour une traduction quasi-instantanée.")

    discipline = st.sidebar.selectbox("Domaine Scientifique", ["Mécanique des Fluides", "Physique", "Chimie", "Maths"])
    file = st.file_uploader("Téléverser le PDF Anglais", type="pdf")

    if file and st.button("Traduire avec Groq"):
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = os.path.join(tmp_dir, "input.pdf")
            with open(input_path, "wb") as f:
                f.write(file.getbuffer())
            
            doc = fitz.open(input_path)
            out_pdf = fitz.open()
            
            progress = st.progress(0)
            status = st.empty()

            for i in range(len(doc)):
                status.text(f"Traduction de la page {i+1} sur {len(doc)}...")
                page = doc[i]
                
                original_text = page.get_text().strip()
                
                if len(original_text) > 15:
                    translated = translate_engine(original_text, discipline)
                    
                    # Gestion du délai si Groq demande de ralentir
                    if translated == "RETRY_LATER":
                        status.warning("Limite de vitesse atteinte. Pause de 5 secondes...")
                        time.sleep(5)
                        translated = translate_engine(original_text, discipline)

                    # Effacement de l'anglais
                    for block in page.get_text("blocks"):
                        page.add_redact_annotation(block[:4], fill=(1,1,1))
                    page.apply_redactions()

                    # Ajout du français
                    overlay_bytes = create_overlay(translated, page.rect)
                    overlay_doc = fitz.open("pdf", overlay_bytes)
                    page.show_pdf_page(page.rect, overlay_doc, 0)
                
                out_pdf.insert_pdf(doc, from_page=i, to_page=i)
                progress.progress((i + 1) / len(doc))
                
                # Petite pause pour respecter les quotas gratuits de Groq
                time.sleep(0.3)

            status.success("Félicitations ! Le livre est traduit.")
            st.download_button("📥 Télécharger le PDF Français", out_pdf.tobytes(), "Livre_FR_Groq.pdf")

if __name__ == "__main__":
    main()
