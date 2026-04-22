import streamlit as st
import fitz  # PyMuPDF
import os
import tempfile
import re
from concurrent.futures import ProcessPoolExecutor
from reportlab.pdfgen import canvas
from io import BytesIO

# --- CONFIGURATION ---
st.set_page_config(page_title="Sci-Translate Pro", page_icon="🧪", layout="wide")

# --- LOGIQUE DE PROTECTION & TRADUCTION ---
def protect_scientific_content(text):
    protected_vault = {}
    latex_pattern = r'(\$\$.*?\$\$|\$.*?\$)'
    chem_pattern = r'\b([A-Z][a-z]?\d+([A-Z][a-z]?\d*)*)\b'
    combined_pattern = f"({latex_pattern}|{chem_pattern})"
    
    def replace_match(match):
        placeholder = f"[[SCI_REF_{len(protected_vault)}]]"
        protected_vault[placeholder] = match.group(0)
        return placeholder

    masked_text = re.sub(combined_pattern, replace_match, text)
    return masked_text, protected_vault

def restore_scientific_content(translated_text, vault):
    for placeholder, original_value in vault.items():
        translated_text = translated_text.replace(placeholder, original_value)
    return translated_text

def translate_engine(text, discipline):
    # Simulation d'appel API (À remplacer par OpenAI/DeepL)
    masked_text, vault = protect_scientific_content(text)
    translated = f"{masked_text}" # Simule la traduction
    return restore_scientific_content(translated, vault)

# --- RECONSTRUCTION VISUELLE ---
def create_overlay(translated_text, rect):
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(rect.width, rect.height))
    can.setFont("Helvetica", 10)
    
    # Écriture simple (Amélioration possible avec calcul de coordonnées)
    text_obj = can.beginText(50, rect.height - 50)
    for line in translated_text.split('\n')[:40]: # Limite pour éviter débordement
        text_obj.textLine(line[:100])
    can.drawText(text_obj)
    
    can.save()
    packet.seek(0)
    return packet

def process_page_range(pdf_path, start, end, discipline):
    doc = fitz.open(pdf_path)
    results = []
    for i in range(start, end):
        if i >= len(doc): break
        page = doc[i]
        translated = translate_engine(page.get_text(), discipline)
        results.append((i, translated))
    return results

# --- INTERFACE STREAMLIT ---
def main():
    st.title("🔬 Traducteur Scientifique Haute Précision")
    
    discipline = st.sidebar.selectbox("Discipline", ["Physique", "Chimie", "Maths", "Biologie"])
    uploaded_file = st.file_uploader("Importer votre PDF (> 5 Mo)", type="pdf")

    if uploaded_file:
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = os.path.join(tmp_dir, "source.pdf")
            with open(input_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            doc_orig = fitz.open(input_path)
            num_pages = len(doc_orig)
            
            if st.button(f"🚀 Traduire les {num_pages} pages"):
                progress = st.progress(0)
                status = st.empty()
                
                # 1. TRADUCTION PARALLÈLE
                all_results = []
                chunk_size = 5
                ranges = [(input_path, i, i+chunk_size, discipline) for i in range(0, num_pages, chunk_size)]
                
                with ProcessPoolExecutor() as executor:
                    futures = [executor.submit(process_page_range, *r) for r in ranges]
                    for idx, f in enumerate(futures):
                        all_results.extend(f.result())
                        progress.progress(int((idx+1)/len(futures) * 80))
                        status.text(f"Traduction : {len(all_results)}/{num_pages} pages...")

                all_results.sort() # Remettre dans l'ordre
                translated_texts = [r[1] for r in all_results]

                # 2. FUSION ET RECONSTRUCTION
                status.text("🏗️ Reconstruction du PDF final...")
                output_pdf = fitz.open()
                
                for i in range(num_pages):
                    page = doc_orig[i]
                    # Nettoyage du texte original
                    for block in page.get_text("blocks"):
                        page.add_redact_annotation(block[:4], fill=(1, 1, 1))
                    page.apply_redactions()
                    
                    # Ajout du calque
                    overlay_pdf = fitz.open("pdf", create_overlay(translated_texts[i], page.rect))
                    page.show_pdf_page(page.rect, overlay_pdf, 0)
                    output_pdf.insert_pdf(doc_orig, from_page=i, to_page=i)
                
                progress.progress(100)
                status.success("Document prêt !")
                
                final_bytes = output_pdf.tobytes(garbage=4, deflate=True)
                st.download_button("📥 Télécharger PDF Traduit", final_bytes, "resultat.pdf", "application/pdf")

if __name__ == "__main__":
    main()
