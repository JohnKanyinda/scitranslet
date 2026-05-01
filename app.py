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
st.set_page_config(page_title="Sci-Translate Stable", page_icon="🚀", layout="wide")

def translate_engine(text, engine_choice, discipline):
    try:
        if "Groq" in engine_choice:
            client = Groq(api_key=st.secrets["GROQ_API_KEY"])
            # Passage au modèle 8b pour éviter l'erreur 400 de saturation
            model_name = "llama-3.1-8b-instant"
        else:
            client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
            model_name = "gpt-4o-mini"
        
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": f"Tu es un traducteur expert en {discipline}. Traduis en français. Ne renvoie QUE la traduction."},
                {"role": "user", "content": text}
            ],
            temperature=0.1 # Plus bas pour plus de fidélité technique
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Erreur d'API : {str(e)}"

def create_overlay(text, rect):
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(rect.width, rect.height))
    can.setFont("Helvetica", 9)
    to = can.beginText(50, rect.height - 50)
    
    # Gestion simple du retour à la ligne
    lines = text.split('\n')
    for line in lines:
        if line.strip():
            to.textLine(line[:95])
    
    can.drawText(to)
    can.save()
    packet.seek(0)
    return packet

def main():
    st.title("🔬 Traducteur Scientifique (Version Stable)")
    
    engine = st.sidebar.radio("Moteur d'IA", ["Groq (Llama 8B - Rapide)", "OpenAI (GPT-4o)"])
    discipline = st.sidebar.selectbox("Domaine", ["Mécanique des Fluides", "Physique", "Chimie"])
    
    uploaded_file = st.file_uploader("Charger le PDF original", type="pdf")

    if uploaded_file and st.button("Traduire le document"):
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = os.path.join(tmp_dir, "input.pdf")
            with open(input_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            doc_orig = fitz.open(input_path)
            out_pdf = fitz.open()
            
            progress_bar = st.progress(0)
            status = st.empty()

            for i in range(len(doc_orig)):
                status.text(f"Traitement page {i+1} sur {len(doc_orig)}...")
                page = doc_orig[i]
                eng_text = page.get_text().strip()
                
                # Traduire seulement si la page contient du texte significatif
                if len(eng_text) > 20:
                    fr_text = translate_engine(eng_text, engine, discipline)
                    
                    # Nettoyage de l'anglais
                    try:
                        for b in page.get_text("blocks"):
                            r = fitz.Rect(b[:4])
                            if r.is_valid:
                                page.add_redact_annotation(r, fill=(1,1,1))
                        page.apply_redactions()
                    except:
                        pass

                    # Ajout du français
                    overlay_bytes = create_overlay(fr_text, page.rect)
                    overlay_doc = fitz.open("pdf", overlay_bytes)
                    page.show_pdf_page(page.rect, overlay_doc, 0)
                
                out_pdf.insert_pdf(doc_orig, from_page=i, to_page=i)
                progress_bar.progress((i + 1) / len(doc_orig))
                
                # Pause obligatoire pour ne pas saturer l'API gratuite
                time.sleep(1.5)

            status.success("✅ Document prêt !")
            st.download_button("📥 Télécharger le résultat", out_pdf.tobytes(), "Traduction_Stable.pdf")

if __name__ == "__main__":
    main()
