import streamlit as st
import fitz  # PyMuPDF
import os
import tempfile
import time
from groq import Groq
from reportlab.pdfgen import canvas
from io import BytesIO

# --- CONFIGURATION ---
st.set_page_config(page_title="Sci-Translate Groq Speed", page_icon="⚡", layout="wide")

def translate_engine(text, discipline):
    """Moteur de traduction utilisant Groq (Llama 3.1 70B)"""
    try:
        # Initialisation du client Groq avec le secret
        client = Groq(api_key=st.secrets["GROQ_API_KEY"])
        
        # On utilise llama-3.1-70b qui est excellent pour les textes techniques
        completion = client.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=[
                {
                    "role": "system", 
                    "content": (
                        f"Tu es un traducteur expert en {discipline}. "
                        "Traduis TOUT le texte de l'anglais vers le français. "
                        "Ne réponds que par la traduction française, sans aucun commentaire. "
                        "Garde les symboles mathématiques intacts."
                    )
                },
                {"role": "user", "content": text}
            ],
            temperature=0.2,
        )
        return completion.choices[0].message.content
    except Exception as e:
        if "429" in str(e):
            return "RATE_LIMIT" # Signal pour ralentir
        return f"[Erreur : {str(e)}]"

def create_overlay(text, rect):
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(rect.width, rect.height))
    can.setFont("Helvetica", 10)
    to = can.beginText(40, rect.height - 50)
    
    lines = text.split('\n')
    for line in lines:
        if line.strip():
            words = line.split(' ')
            curr_line = ""
            for word in words:
                if len(curr_line + word) < 80:
                    curr_line += word + " "
                else:
                    to.textLine(curr_line)
                    curr_line = word + " "
            to.textLine(curr_line)
    
    can.drawText(to)
    can.save()
    packet.seek(0)
    return packet

def main():
    st.title("⚡ Sci-Translate : Version Groq Ultra-Fast")
    st.markdown("Traduction scientifique propulsée par **Llama 3.1 70B** sur Groq.")

    discipline = st.sidebar.selectbox("Domaine", ["Mécanique des Fluides", "Physique", "Chimie", "Maths"])
    file = st.file_uploader("Charger le PDF Anglais", type="pdf")

    if file and st.button("Traduire à la vitesse de l'éclair"):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "input.pdf")
            with open(path, "wb") as f:
                f.write(file.getbuffer())
            
            doc = fitz.open(path)
            out_pdf = fitz.open()
            
            progress = st.progress(0)
            status = st.empty()

            for i in range(len(doc)):
                status.text(f"Traduction page {i+1}/{len(doc)}...")
                page = doc[i]
                eng_text = page.get_text().strip()
                
                if len(eng_text) > 15:
                    translated = translate_engine(eng_text, discipline)
                    
                    # Gestion du Rate Limit (Limite de requêtes gratuites)
                    if translated == "RATE_LIMIT":
                        status.warning("Limite Groq atteinte. Pause de 10 secondes...")
                        time.sleep(10)
                        translated = translate_engine(eng_text, discipline)

                    # Nettoyage et superposition
                    for b in page.get_text("blocks"):
                        page.add_redact_annotation(b[:4], fill=(1,1,1))
                    page.apply_redactions()

                    overlay = fitz.open("pdf", create_overlay(translated, page.rect))
                    page.show_pdf_page(page.rect, overlay, 0)
                
                out_pdf.insert_pdf(doc, from_page=i, to_page=i)
                progress.progress((i + 1) / len(doc))
                # Petite pause de sécurité pour Groq Free Tier
                time.sleep(0.5)

            status.success("Traduction terminée avec Groq !")
            st.download_button("📥 Télécharger PDF", out_pdf.tobytes(), "Traduit_Groq.pdf")

if __name__ == "__main__":
    main()
