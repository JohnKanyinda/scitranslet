import streamlit as st
import fitz
import os
import tempfile
import time
from openai import OpenAI
from groq import Groq
from reportlab.pdfgen import canvas
from io import BytesIO

st.set_page_config(page_title="Sci-Translate Multi-Engine", page_icon="🚀")

def translate_text(text, engine, discipline):
    try:
        if engine == "Groq (Rapide)":
            client = Groq(api_key=st.secrets["GROQ_API_KEY"])
            model = "llama-3.1-70b-versatile"
        else:
            client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
            model = "gpt-4o-mini"

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": f"Traduis ce texte scientifique en français (Domaine: {discipline}). Ne renvoie que la traduction."},
                {"role": "user", "content": text}
            ],
            temperature=0.2
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Erreur: {str(e)}"

def create_overlay(text, rect):
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(rect.width, rect.height))
    can.setFont("Helvetica", 10)
    to = can.beginText(40, rect.height - 50)
    for line in text.split('\n'):
        to.textLine(line[:90])
    can.drawText(to)
    can.save()
    packet.seek(0)
    return packet

def main():
    st.title("📚 Traducteur de Livres Scientifiques")
    
    engine = st.sidebar.radio("Choisir le moteur d'IA", ["Groq (Rapide)", "OpenAI (Précis)"])
    discipline = st.sidebar.selectbox("Discipline", ["Physique", "Mécanique", "Chimie"])
    file = st.file_uploader("PDF original", type="pdf")

    if file and st.button("Lancer la traduction"):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "in.pdf")
            with open(input_path, "wb") as f: f.write(file.getbuffer())
            
            doc = fitz.open(input_path)
            out_pdf = fitz.open()
            
            bar = st.progress(0)
            for i in range(len(doc)):
                page = doc[i]
                txt = page.get_text().strip()
                
                if len(txt) > 20:
                    trad = translate_text(txt, engine, discipline)
                    for b in page.get_text("blocks"):
                        page.add_redact_annotation(b[:4], fill=(1,1,1))
                    page.apply_redactions()
                    
                    overlay = fitz.open("pdf", create_overlay(trad, page.rect))
                    page.show_pdf_page(page.rect, overlay, 0)
                
                out_pdf.insert_pdf(doc, from_page=i, to_page=i)
                bar.progress((i+1)/len(doc))
                if engine == "Groq (Rapide)": time.sleep(0.5)

            st.success("Terminé !")
            st.download_button("📥 Télécharger", out_pdf.tobytes(), "Livre_Traduit.pdf")

if __name__ == "__main__":
    main()
