import streamlit as st
import fitz  # PyMuPDF
import os
import tempfile
import re
from openai import OpenAI
from concurrent.futures import ProcessPoolExecutor
from reportlab.pdfgen import canvas
from io import BytesIO

# --- CONFIGURATION ---
st.set_page_config(page_title="Sci-Translate Pro", page_icon="🧪", layout="wide")

# --- LOGIQUE DE PROTECTION ---
def protect_content(text):
    vault = {}
    # Pattern pour LaTeX et Formules Chimiques
    pattern = r'(\$\$.*?\$\$|\$.*?\$|\b([A-Z][a-z]?\d+([A-Z][a-z]?\d*)*)\b)'
    def replace(m):
        tag = f"[[SCI_{len(vault)}]]"
        vault[tag] = m.group(0)
        return tag
    return re.sub(pattern, replace, text), vault

def restore_content(text, vault):
    for tag, val in vault.items():
        text = text.replace(tag, val)
    return text

# --- MOTEUR DE TRADUCTION (GITHUB MODELS) ---
def translate_engine(text, discipline):
    try:
        token = st.secrets["GH_TOKEN"]
        client = OpenAI(
            base_url="https://models.inference.ai.azure.com",
            api_key=token,
        )
        
        masked_text, vault = protect_content(text)
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"Tu es un traducteur expert en {discipline}. Garde les tags [[SCI_X]] intacts. Traduis uniquement le texte."},
                {"role": "user", "content": masked_text}
            ],
            temperature=0
        )
        translated = response.choices[0].message.content
        return restore_content(translated, vault)
    except Exception as e:
        return text # Retourne l'original si l'API échoue

# --- RECONSTRUCTION VISUELLE ---
def create_overlay(text, rect):
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(rect.width, rect.height))
    can.setFont("Helvetica", 10)
    to = can.beginText(50, rect.height - 50)
    # Limitation simple pour éviter que le texte ne sorte de la page
    for line in text.split('\n')[:45]:
        to.textLine(line[:90])
    can.drawText(to)
    can.save()
    packet.seek(0)
    return packet

# --- TRAITEMENT DES PAGES ---
def process_page_range(pdf_path, start, end, discipline):
    doc = fitz.open(pdf_path)
    results = []
    for i in range(start, end):
        if i >= len(doc): break
        page = doc[i]
        raw_text = page.get_text().strip()
        
        # Filtre d'économie (Pages vides ou images seules)
        if len(raw_text) < 15 or not any(c.isalpha() for c in raw_text):
            results.append((i, raw_text))
        else:
            results.append((i, translate_engine(raw_text, discipline)))
    return results

# --- INTERFACE PRINCIPALE ---
def main():
    st.title("🔬 Sci-Translate (Free GitHub Edition)")
    st.markdown("Traduisez vos documents scientifiques en préservant les schémas.")

    discipline = st.sidebar.selectbox("Domaine", ["Physique", "Chimie", "Maths", "Biologie"])
    file = st.file_uploader("Charger le PDF", type="pdf")

    if file:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = os.path.join(tmp_dir, "input.pdf")
            with open(tmp_path, "wb") as f:
                f.write(file.getbuffer())
            
            doc_orig = fitz.open(tmp_path)
            num_pages = len(doc_orig)

            if st.button(f"🚀 Traduire {num_pages} pages"):
                prog = st.progress(0)
                status = st.empty()
                
                # 1. TRADUCTION
                all_texts = []
                chunk_size = 5
                ranges = [(tmp_path, i, i+chunk_size, discipline) for i in range(0, num_pages, chunk_size)]
                
                with ProcessPoolExecutor() as ex:
                    futures = [ex.submit(process_page_range, *r) for r in ranges]
                    for idx, f in enumerate(futures):
                        all_texts.extend(f.result())
                        prog.progress(int((idx+1)/len(futures) * 70))
                        status.text(f"Traduction : {len(all_texts)}/{num_pages} pages...")

                all_texts.sort() # Remettre dans l'ordre des pages

                # 2. RECONSTRUCTION DU PDF
                status.text("🏗️ Reconstruction du fichier final...")
                out_pdf = fitz.open()
                
                for i in range(num_pages):
                    page = doc_orig[i]
                    
                    # Bloc de nettoyage sécurisé
                    try:
                        for b in page.get_text("blocks"):
                            page.add_redact_annotation(b[:4], fill=(1,1,1))
                        page.apply_redactions()
                    except:
                        pass # Continue si la rédaction échoue sur une page
                    
                    # Superposition du texte traduit
                    translated_content = all_texts[i][1]
                    overlay_pdf = fitz.open("pdf", create_overlay(translated_content, page.rect))
                    page.show_pdf_page(page.rect, overlay_pdf, 0)
                    out_pdf.insert_pdf(doc_orig, from_page=i, to_page=i)
                
                prog.progress(100)
                status.success("Traduction terminée avec succès !")
                
                st.download_button(
                    label="📥 Télécharger le PDF Traduit",
                    data=out_pdf.tobytes(garbage=4, deflate=True),
                    file_name=f"Traduction_{discipline}.pdf",
                    mime="application/pdf"
                )

if __name__ == "__main__":
    main()
