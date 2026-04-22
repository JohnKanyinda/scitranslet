import streamlit as st
import fitz  # PyMuPDF
import os
import tempfile
from openai import OpenAI
from reportlab.pdfgen import canvas
from io import BytesIO

# --- CONFIGURATION ---
st.set_page_config(page_title="Sci-Translate Fix", page_icon="🧪", layout="wide")

# --- MOTEUR DE TRADUCTION SIMPLIFIÉ ---
def translate_engine(text, discipline):
    try:
        # Récupération sécurisée du Token
        token = st.secrets["GH_TOKEN"]
        client = OpenAI(
            base_url="https://models.inference.ai.azure.com",
            api_key=token,
        )
        
        # Envoi du texte brut pour éviter toute confusion de l'IA
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": f"Tu es un traducteur expert. Traduis le texte suivant de l'ANGLAIS vers le FRANÇAIS. Domaine : {discipline}. "
                               "Garde les termes techniques corrects. Ne réponds QUE par la traduction française."
                },
                {"role": "user", "content": text}
            ],
            temperature=0.1 # Très bas pour éviter les erreurs
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"[Erreur de traduction : {str(e)}]"

# --- CRÉATION DU CALQUE FRANÇAIS ---
def create_overlay(text, rect):
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(rect.width, rect.height))
    can.setFont("Helvetica", 9)
    to = can.beginText(40, rect.height - 50)
    
    # Gestion simple du texte pour le calque
    lines = text.split('\n')
    for line in lines:
        # On coupe les lignes trop longues pour qu'elles restent dans la page
        clean_line = line.strip()
        if len(clean_line) > 0:
            to.textLine(clean_line[:95])
            if len(clean_line) > 95:
                to.textLine(clean_line[95:190])
    
    can.drawText(to)
    can.save()
    packet.seek(0)
    return packet

# --- INTERFACE PRINCIPALE ---
def main():
    st.title("🔬 Sci-Translate : Version Corrective")
    st.info("Cette version traite les pages une par une pour garantir la traduction en Français.")

    discipline = st.sidebar.selectbox("Domaine", ["Physique", "Chimie", "Biologie", "Mathématiques"])
    file = st.file_uploader("Choisir le fichier PDF Anglais", type="pdf")

    if file:
        if st.button("Lancer la traduction intégrale"):
            with tempfile.TemporaryDirectory() as tmp_dir:
                input_path = os.path.join(tmp_dir, "input.pdf")
                with open(input_path, "wb") as f:
                    f.write(file.getbuffer())
                
                doc_orig = fitz.open(input_path)
                out_pdf = fitz.open()
                num_pages = len(doc_orig)
                
                progress_bar = st.progress(0)
                status_text = st.empty()

                # Traitement séquentiel (plus fiable pour les clés gratuites)
                for i in range(num_pages):
                    status_text.text(f"Traduction de la page {i+1} sur {num_pages}...")
                    page = doc_orig[i]
                    
                    # 1. Extraction du texte
                    text_to_translate = page.get_text().strip()
                    
                    if len(text_to_translate) > 20:
                        # 2. Appel IA
                        translated_text = translate_engine(text_to_translate, discipline)
                    else:
                        translated_text = text_to_translate
                    
                    # 3. Effacement du texte original (Rectangle blanc)
                    for block in page.get_text("blocks"):
                        page.add_redact_annotation(block[:4], fill=(1, 1, 1))
                    page.apply_redactions()
                    
                    # 4. Ajout du texte français
                    overlay_pdf_bytes = create_overlay(translated_text, page.rect)
                    overlay_doc = fitz.open("pdf", overlay_pdf_bytes)
                    page.show_pdf_page(page.rect, overlay_doc, 0)
                    
                    # 5. Insertion dans le document final
                    out_pdf.insert_pdf(doc_orig, from_page=i, to_page=i)
                    
                    progress_bar.progress((i + 1) / num_pages)

                status_text.success("C'est fini ! Votre livre est prêt en français.")
                
                # Téléchargement
                final_bytes = out_pdf.tobytes(garbage=4, deflate=True)
                st.download_button(
                    label="📥 Télécharger le PDF en Français",
                    data=final_bytes,
                    file_name="Livre_Traduit_FR.pdf",
                    mime="application/pdf"
                )

if __name__ == "__main__":
    main()
