import streamlit as st
import fitz  # PyMuPDF
import os
import tempfile
from openai import OpenAI
from reportlab.pdfgen import canvas
from io import BytesIO

# --- CONFIGURATION ---
st.set_page_config(page_title="Sci-Translate OpenAI", page_icon="🧪")

def translate_engine(text, discipline):
    try:
        # Utilisation de la clé OpenAI configurée dans les secrets
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        
        response = client.chat.completions.create(
            model="gpt-4o-mini", # Modèle très performant et peu coûteux
            messages=[
                {
                    "role": "system", 
                    "content": (
                        f"Tu es un traducteur expert en {discipline}. "
                        "Traduis le texte de l'anglais vers le français. "
                        "Ne conserve aucune phrase en anglais. "
                        "Garde les termes techniques et formules mathématiques. "
                        "Ne réponds QUE par la traduction française."
                    )
                },
                {"role": "user", "content": text}
            ],
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"[Erreur API : {str(e)}]"

def create_overlay(text, rect):
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(rect.width, rect.height))
    can.setFont("Helvetica", 10)
    to = can.beginText(40, rect.height - 50)
    
    # Découpage du texte pour qu'il tienne dans la page
    lines = text.split('\n')
    for line in lines:
        if len(line.strip()) > 0:
            # On découpe les lignes trop longues
            words = line.split(' ')
            current_line = ""
            for word in words:
                if len(current_line + word) < 85:
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
    st.title("🔬 Traducteur Scientifique (Moteur OpenAI)")
    st.info("Cette version utilise GPT-4o-mini pour une traduction Anglais -> Français parfaite.")

    discipline = st.sidebar.selectbox("Discipline", ["Physics", "Chemistry", "Mathematics", "Biology"])
    file = st.file_uploader("Fichier PDF en Anglais", type="pdf")

    if file and st.button("Traduire le livre"):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "input.pdf")
            with open(path, "wb") as f:
                f.write(file.getbuffer())
            
            doc = fitz.open(path)
            out_pdf = fitz.open()
            
            bar = st.progress(0)
            status = st.empty()

            for i in range(len(doc)):
                status.text(f"Traduction de la page {i+1} / {len(doc)}...")
                page = doc[i]
                
                # 1. Extraction
                original_text = page.get_text()
                
                if len(original_text.strip()) > 20:
                    # 2. Traduction Réelle
                    translated = translate_engine(original_text, discipline)
                else:
                    translated = original_text

                # 3. Effacement TOTAL du texte original
                for block in page.get_text("blocks"):
                    page.add_redact_annotation(block[:4], fill=(1,1,1))
                page.apply_redactions()

                # 4. Insertion du Français
                overlay_bytes = create_overlay(translated, page.rect)
                overlay_doc = fitz.open("pdf", overlay_bytes)
                page.show_pdf_page(page.rect, overlay_doc, 0)
                
                out_pdf.insert_pdf(doc, from_page=i, to_page=i)
                bar.progress((i + 1) / len(doc))

            status.success("Traduction réussie !")
            st.download_button("📥 Télécharger en Français", out_pdf.tobytes(), "Resultat_FR.pdf")

if __name__ == "__main__":
    main()
