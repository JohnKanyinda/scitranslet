import streamlit as st
import fitz  # PyMuPDF
import os
import tempfile
import time
from openai import OpenAI
from groq import Groq
from reportlab.pdfgen import canvas
from io import BytesIO

# --- CONFIGURATION ---
st.set_page_config(page_title="Sci-Translate Final", page_icon="🧪", layout="wide")

def translate_engine(text, engine_choice, discipline):
    """Moteur de traduction avec gestion d'erreurs et choix d'IA"""
    try:
        if engine_choice == "Groq (Llama 3.1 - Ultra Rapide)":
            client = Groq(api_key=st.secrets["GROQ_API_KEY"])
            model_name = "llama-3.1-70b-versatile"
        else:
            client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
            model_name = "gpt-4o-mini"
        
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": f"Tu es un traducteur expert en {discipline}. Traduis ce texte de l'anglais vers le français. Ne renvoie que la traduction française brute."},
                {"role": "user", "content": text}
            ],
            temperature=0.2
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Erreur d'API : {str(e)}"

def create_overlay(text, rect):
    """Crée un calque PDF avec le texte traduit"""
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(rect.width, rect.height))
    can.setFont("Helvetica", 10)
    to = can.beginText(40, rect.height - 50)
    
    for line in text.split('\n'):
        if line.strip():
            # Limitation simple de largeur de ligne
            to.textLine(line[:85])
    
    can.drawText(to)
    can.save()
    packet.seek(0)
    return packet

def main():
    st.title("🔬 Traducteur Scientifique Final")
    
    # Barre latérale
    engine = st.sidebar.radio("Moteur d'IA", ["Groq (Llama 3.1 - Ultra Rapide)", "OpenAI (GPT-4o)"])
    discipline = st.sidebar.selectbox("Domaine", ["Mécanique des Fluides", "Physique", "Chimie"])
    
    uploaded_file = st.file_uploader("Charger le PDF (Anglais)", type="pdf")

    if uploaded_file and st.button("Lancer la traduction"):
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = os.path.join(tmp_dir, "input.pdf")
            with open(input_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            doc_orig = fitz.open(input_path)
            out_pdf = fitz.open()
            
            progress_bar = st.progress(0)
            status = st.empty()

            for i in range(len(doc_orig)):
                status.text(f"Traduction de la page {i+1} / {len(doc_orig)}...")
                page = doc_orig[i]
                eng_text = page.get_text().strip()
                
                if len(eng_text) > 15:
                    # 1. Traduction
                    fr_text = translate_engine(eng_text, engine, discipline)
                    
                    # 2. Effacement sécurisé (Correction de l'erreur SharedScreenshot_7.jpg)
                    for block in page.get_text("blocks"):
                        r = fitz.Rect(block[:4])
                        if r.is_valid and not r.is_empty:
                            page.add_redact_annotation(r, fill=(1,1,1))
                    page.apply_redactions()

                    # 3. Superposition du français
                    overlay_bytes = create_overlay(fr_text, page.rect)
                    overlay_doc = fitz.open("pdf", overlay_bytes)
                    page.show_pdf_page(page.rect, overlay_doc, 0)
                
                out_pdf.insert_pdf(doc_orig, from_page=i, to_page=i)
                progress_bar.progress((i + 1) / len(doc_orig))
                
                if "Groq" in engine:
                    time.sleep(0.4) # Protection contre le Rate Limit gratuit

            status.success("Traduction terminée !")
            st.download_button("📥 Télécharger le PDF Français", out_pdf.tobytes(), "Traduction_Finale.pdf")

if __name__ == "__main__":
    main()
