# app.py
import streamlit as st
from pathlib import Path

st.set_page_config(page_title="Web Archive Dashboard", layout="wide")

ARCHIVE_DIR = Path("archives")
ARCHIVE_DIR.mkdir(exist_ok=True)

st.title("📦 Web Archive (Daily Snapshot)")

runs = sorted([p for p in ARCHIVE_DIR.iterdir() if p.is_dir()], reverse=True)

if not runs:
    st.info("Belum ada arsip. Jalankan archiver.py dulu.")
    st.stop()

selected = st.selectbox("Pilih snapshot", [p.name for p in runs])
folder = ARCHIVE_DIR / selected

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Screenshot")
    png = folder / "screenshot.png"
    if png.exists():
        st.image(str(png), use_container_width=True)

with col2:
    st.subheader("Download")
    for fn in ["page.html", "page.pdf", "screenshot.png", "meta.txt"]:
        f = folder / fn
        if f.exists():
            st.download_button(
                label=f"Download {fn}",
                data=f.read_bytes(),
                file_name=f"{selected}_{fn}",
                mime="application/octet-stream",
            )
