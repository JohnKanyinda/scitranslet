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

# --- LOGIQUE DE PROTECTION DES FORMULES ---
def protect_content(text):
    vault = {}
    # Pattern pour LaTeX ($...$), formules chimiques et constantes
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

# --- MOTEUR DE TRADUCTION (ANGLAIS -> FRANÇAIS) ---
def translate_engine(text, discipline):
    try:
        token = st.secrets["GH_TOKEN"]
        client = OpenAI(
            base_url="https://models.inference.ai.azure.com",
            api_key=token,
        )
        
        masked_text, vault = protect_content(text)
        
        # Instructions strictes pour forcer la traduction en Français
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": (
                        f"Tu es un traducteur expert en {discipline}. "
                        "Ta mission est de traduire le texte de l'ANGLAIS vers le FRANÇAIS uniquement. "
                        "Garde un ton académique et professionnel. "
                        "CONSIGNE CRITIQUE : Ne modifie jamais les balises [[SCI_X]]. "
                        "Ne renvoie que la traduction, sans commentaires."
                    )
                },
                {"role": "user", "content": f"Translate this scientific text into French: {masked_text}"}
            ],
            temperature=0.2 # Précision maximale
        )
        translated = response.choices[0].message.content
        return restore_content(translated, vault)
    except Exception as e:
        return text 

# --- RECONSTRUCTION DU CALQUE PDF ---
def create_overlay(text, rect):
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(rect.width, rect.height))
    # Police légèrement plus petite (9) car le français est plus long que l'anglais
    can.setFont("Helvetica", 9) 
    to = can.beginText(50, rect.height - 50)
    
    # Découpage basique des lignes pour le calque
    for line in text.split('\n')[:50]:
        to.textLine(line[:100])
    can.drawText(to)
    can.save()
    packet.seek(0)
    return packet

# --- TRAITEMENT PARALLÈLE ---
def process_page_range(pdf_path, start, end, discipline):
    doc = fitz.open(pdf_path)
    results = []
    for i in range(start, end):
        if i >= len(doc): break
        page = doc[i]
        raw_text = page.get_text().strip()
        
        # Filtre de sécurité (pages vides ou schémas sans texte)
        if len(raw_text) < 15 or not any(c.isalpha() for c in raw_text):
            results.append((i, raw_text))
        else:
            results.append((i, translate_engine(raw_text, discipline)))
    return results

# --- INTERFACE UTILISATEUR ---
def main():
    st.title("🔬 Sci-Translate Pro")
    st.subheader("Traduction spécialisée Anglais ➡️ Français")

    discipline = st.sidebar.selectbox("Domaine Scientifique", ["Physique", "Chimie", "Mathématiques", "Biologie"])
    file = st.file_uploader("Téléverser votre PDF original (Anglais)", type="pdf")

    if file:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = os.path.join(tmp_dir, "input.pdf")
            with open(tmp_path, "wb") as f:
                f.write(file.getbuffer())
            
            doc_orig = fitz.open(tmp_path)
            num_pages = len(doc_orig)

            if st.button(f"Traduire les {num_pages} pages en Français"):
                prog = st.progress(0)
                status = st.empty()
                
                # Phase 1 : Traduction
                all_texts = []
                chunk_size = 4 # Réduit pour éviter les limites de débit (Rate Limits)
                ranges = [(tmp_path, i, i+chunk_size, discipline) for i in range(0, num_pages, chunk_size)]
                
                with ProcessPoolExecutor() as ex:
                    futures = [ex.submit(process_page_range, *r) for r in ranges]
                    for idx, f in enumerate(futures):
                        all_texts.extend(f.result())
                        prog.progress(int((idx+1)/len(futures) * 70))
                        status.text(f"Traduction en cours... {len(all_texts)}/{num_pages}")

                all_texts.sort()

                # Phase 2 : Reconstruction
                status.text("Reconstruction du PDF traduit...")
                out_pdf = fitz.open()
                
                for i in range(num_pages):
                    page = doc_orig[i]
                    
                    # On efface le texte anglais proprement
                    try:
                        for b in page.get_text("blocks"):
                            page.add_redact_annotation(b[:4], fill=(1,1,1))
                        page.apply_redactions()
                    except:
                        pass
                    
                    # On pose le calque français
                    translated_content = all_texts[i][1]
                    overlay_pdf = fitz.open("pdf", create_overlay(translated_content, page.rect))
                    page.show_pdf_page(page.rect, overlay_pdf, 0)
                    out_pdf.insert_pdf(doc_orig, from_page=i, to_page=i)
                
                prog.progress(100)
                status.success("Traduction terminée !")
                
                st.download_button(
                    label="📥 Télécharger le livre en Français",
                    data=out_pdf.tobytes(garbage=4, deflate=True),
                    file_name=f"Livre_{discipline}_FR.pdf",
                    mime="application/pdf"
                )

if __name__ == "__main__":
    main()
