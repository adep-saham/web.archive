# app.py
import streamlit as st
import json
from pathlib import Path

TARGET_FILE = Path("targets.json")
ARCHIVE_DIR = Path("archives")

st.set_page_config(layout="wide")
st.title("📦 Daily Web Archive Manager")

# ---------- Load / Save targets ----------
def load_targets():
    if TARGET_FILE.exists():
        return json.loads(TARGET_FILE.read_text())
    return []

def save_targets(tgts):
    TARGET_FILE.write_text(json.dumps(tgts, indent=2))

targets = load_targets()

# ---------- Input URL ----------
st.subheader("➕ Tambah Website")
new_url = st.text_input("Masukkan URL")

if st.button("Tambah"):
    if new_url and new_url not in targets:
        targets.append(new_url)
        save_targets(targets)
        st.success("URL ditambahkan")
        st.rerun()

# ---------- List URL ----------
st.subheader("🌐 Daftar Target Archive")
for url in targets:
    col1, col2 = st.columns([8,1])
    col1.write(url)
    if col2.button("❌", key=url):
        targets.remove(url)
        save_targets(targets)
        st.rerun()

# ---------- Archive Viewer ----------
st.subheader("🗂️ Arsip")

if ARCHIVE_DIR.exists():
    domains = sorted([d.name for d in ARCHIVE_DIR.iterdir() if d.is_dir()])
    if domains:
        domain = st.selectbox("Pilih Domain", domains)
        runs = sorted([r.name for r in (ARCHIVE_DIR/domain).iterdir()], reverse=True)
        run = st.selectbox("Pilih Tanggal Snapshot", runs)

        folder = ARCHIVE_DIR/domain/run

        st.image(str(folder/"screenshot.png"), use_container_width=True)

        for fn in ["page.html", "page.pdf", "screenshot.png"]:
            f = folder/fn
            if f.exists():
                st.download_button(
                    f"Download {fn}",
                    data=f.read_bytes(),
                    file_name=f"{domain}_{run}_{fn}"
                )
