import streamlit as st
import fitz  # PyMuPDF
import os
import tempfile
import re
import openai
from concurrent.futures import ProcessPoolExecutor
from reportlab.pdfgen import canvas
from io import BytesIO

# --- CONFIGURATION ET API ---
st.set_page_config(page_title="Sci-Translate Pro", page_icon="🧪", layout="wide")

# Vérification de la clé API dans les secrets
def get_api_key():
    try:
        return st.secrets["OPENAI_API_KEY"]
    except:
        st.error("Clé API manquante ! Configurez OPENAI_API_KEY dans les Secrets Streamlit.")
        return None

# --- LOGIQUE DE PROTECTION ---
def protect_content(text):
    vault = {}
    latex_pattern = r'(\$\$.*?\$\$|\$.*?\$)'
    chem_pattern = r'\b([A-Z][a-z]?\d+([A-Z][a-z]?\d*)*)\b'
    pattern = f"({latex_pattern}|{chem_pattern})"
    
    def replace(m):
        tag = f"[[SCI_{len(vault)}]]"
        vault[tag] = m.group(0)
        return tag

    masked = re.sub(pattern, replace, text)
    return masked, vault

def restore_content(text, vault):
    for tag, val in vault.items():
        text = text.replace(tag, val)
    return text

# --- MOTEUR DE TRADUCTION RÉEL ---
def translate_engine(text, discipline):
    api_key = get_api_key()
    if not api_key: return text
    
    client = openai.OpenAI(api_key=api_key)
    masked_text, vault = protect_content(text)
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"Tu es un traducteur expert en {discipline}. Garde les tags [[SCI_X]] intacts. Style concis."},
                {"role": "user", "content": f"Traduis : {masked_text}"}
            ],
            temperature=0
        )
        translated = response.choices[0].message.content
        return restore_content(translated, vault)
    except:
        return text # Retourne l'original en cas d'échec

# --- RECONSTRUCTION VISUELLE ---
def create_overlay(text, rect):
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(rect.width, rect.height))
    can.setFont("Helvetica", 10)
    to = can.beginText(50, rect.height - 50)
    for line in text.split('\n')[:45]:
        to.textLine(line[:90])
    can.drawText(to)
    can.save()
    packet.seek(0)
    return packet

# --- FILTRE ET TRAITEMENT ---
def process_page_range(pdf_path, start, end, discipline):
    doc = fitz.open(pdf_path)
    results = []
    for i in range(start, end):
        if i >= len(doc): break
        page = doc[i]
        raw_text = page.get_text().strip()
        
        # Filtre d'économie : Moins de 15 caractères ou pas de lettres = pas de traduction
        if len(raw_text) < 15 or not any(c.isalpha() for c in raw_text):
            results.append((i, raw_text))
        else:
            results.append((i, translate_engine(raw_text, discipline)))
    return results

# --- INTERFACE PRINCIPALE ---
def main():
    st.title("🔬 Sci-Translate Pro")
    st.caption("Traduisez vos livres scientifiques en respectant la mise en page et les formules.")

    discipline = st.sidebar.selectbox("Domaine scientifique", ["Physique", "Chimie", "Maths", "Biologie"])
    file = st.file_uploader("Fichier PDF (Max 5Mo+ recommandé)", type="pdf")

    if file:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = os.path.join(tmp_dir, "input.pdf")
            with open(tmp_path, "wb") as f:
                f.write(file.getbuffer())
            
            doc_orig = fitz.open(tmp_path)
            num_pages = len(doc_orig)

            if st.button(f"Traduire {num_pages} pages"):
                prog = st.progress(0)
                status = st.empty()
                
                # Parallélisation
                chunk_size = 5
                ranges = [(tmp_path, i, i+chunk_size, discipline) for i in range(0, num_pages, chunk_size)]
                all_texts = []
                
                with ProcessPoolExecutor() as ex:
                    futures = [ex.submit(process_page_range, *r) for r in ranges]
                    for idx, f in enumerate(futures):
                        all_texts.extend(f.result())
                        prog.progress(int((idx+1)/len(futures) * 80))
                        status.text(f"Avancement : {len(all_texts)}/{num_pages} pages...")

                all_texts.sort()
                translated_data = [t[1] for t in all_texts]

                # Reconstruction
                status.text("🏗️ Création du PDF final...")
                out_pdf = fitz.open()
                for i in range(num_pages):
                    page = doc_orig[i]
                    # Nettoyage
                    for b in page.get_text("blocks"):
                        page.add_redact_annotation(b[:4], fill=(1,1,1))
                    page.apply_redactions()
                    
                    # Calque
                    overlay = fitz.open("pdf", create_overlay(translated_data[i], page.rect))
                    page.show_pdf_page(page.rect, overlay, 0)
                    out_pdf.insert_pdf(doc_orig, from_page=i, to_page=i)
                
                prog.progress(100)
                st.success("Terminé !")
                st.download_button("📥 Télécharger PDF", out_pdf.tobytes(garbage=4, deflate=True), "traduit.pdf")

if __name__ == "__main__":
    main()
