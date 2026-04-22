import streamlit as st
import fitz 
import os
import tempfile
import re
# On utilise le client OpenAI car GitHub est compatible
from openai import OpenAI 
from concurrent.futures import ProcessPoolExecutor
from reportlab.pdfgen import canvas
from io import BytesIO

# --- CONFIGURATION ET API GITHUB ---
st.set_page_config(page_title="Sci-Translate GitHub Edition", page_icon="🧪")

def translate_engine(text, discipline):
    # Récupération du token GitHub dans les secrets
    try:
        token = st.secrets["GH_TOKEN"]
    except:
        st.error("Token GH_TOKEN manquant dans les Secrets !")
        return text

    # Configuration pour GitHub Models
    client = OpenAI(
        base_url="https://models.inference.ai.azure.com",
        api_key=token,
    )
    
    masked_text, vault = protect_content(text)
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini", # Nom du modèle sur GitHub Models
            messages=[
                {"role": "system", "content": f"Tu es un traducteur expert en {discipline}. Garde les tags [[SCI_X]] intacts."},
                {"role": "user", "content": f"Traduis en français : {masked_text}"}
            ],
            temperature=0
        )
        translated = response.choices[0].message.content
        return restore_content(translated, vault)
    except Exception as e:
        # En cas de limite de taux (Rate Limit) atteinte sur GitHub
        return text 

# --- LE RESTE DU CODE (PROTECTION, RECONSTRUCTION) RESTE LE MÊME ---

def protect_content(text):
    vault = {}
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

def process_page_range(pdf_path, start, end, discipline):
    doc = fitz.open(pdf_path)
    results = []
    for i in range(start, end):
        if i >= len(doc): break
        page = doc[i]
        raw_text = page.get_text().strip()
        if len(raw_text) < 15 or not any(c.isalpha() for c in raw_text):
            results.append((i, raw_text))
        else:
            results.append((i, translate_engine(raw_text, discipline)))
    return results

def main():
    st.title("🔬 Sci-Translate (Free GitHub Edition)")
    discipline = st.sidebar.selectbox("Domaine", ["Physique", "Chimie", "Maths", "Biologie"])
    file = st.file_uploader("Fichier PDF", type="pdf")

    if file:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = os.path.join(tmp_dir, "input.pdf")
            with open(tmp_path, "wb") as f:
                f.write(file.getbuffer())
            
            doc_orig = fitz.open(tmp_path)
            num_pages = len(doc_orig)

            if st.button(f"Traduire {num_pages} pages"):
                prog = st.progress(0)
                all_texts = []
                chunk_size = 5
                ranges = [(tmp_path, i, i+chunk_size, discipline) for i in range(0, num_pages, chunk_size)]
                
                with ProcessPoolExecutor() as ex:
                    futures = [ex.submit(process_page_range, *r) for r in ranges]
                    for idx, f in enumerate(futures):
                        all_texts.extend(f.result())
                        prog.progress(int((idx+1)/len(futures) * 100))

                all_texts.sort()
                out_pdf = fitz.open()
                for i in range(num_pages):
                    page = doc_orig[i]
                    for b in page.get_text("blocks"):
                        page.add_redact_annotation(b[:4], fill=(1,1,1))
                    page.apply_redactions()
                    overlay = fitz.open("pdf", create_overlay(all_texts[i][1], page.rect))
                    page.show_pdf_page(page.rect, overlay, 0)
                    out_pdf.insert_pdf(doc_orig, from_page=i, to_page=i)
                
                st.success("Terminé !")
                st.download_button("📥 Télécharger PDF", out_pdf.tobytes(), "traduit.pdf")

if __name__ == "__main__":
    main()
