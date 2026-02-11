import streamlit as st
import json
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

TARGET_FILE = Path("targets.json")
ARCHIVE_DIR = Path("archives")
ARCHIVE_DIR.mkdir(exist_ok=True)

st.set_page_config(layout="wide")
st.title("📦 Daily Web Archive Manager")

# ---------- Helpers ----------
def domain_from_url(url):
    return urlparse(url).netloc.replace(":", "_")

def load_targets():
    if TARGET_FILE.exists():
        return json.loads(TARGET_FILE.read_text())
    return []

def save_targets(tgts):
    TARGET_FILE.write_text(json.dumps(tgts, indent=2))

def run_archive_now():
    targets = load_targets()
    if not targets:
        st.warning("Belum ada URL di daftar.")
        return

    with st.spinner("Mengarsipkan semua website..."):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            for url in targets:
                try:
                    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    domain = domain_from_url(url)

                    out_dir = ARCHIVE_DIR / domain / ts
                    out_dir.mkdir(parents=True, exist_ok=True)

                    page.goto(url, wait_until="networkidle", timeout=90_000)

                    # simpan hasil
                    (out_dir / "page.html").write_text(page.content(), encoding="utf-8")
                    page.screenshot(path=str(out_dir / "screenshot.png"), full_page=True)
                    page.pdf(path=str(out_dir / "page.pdf"), format="A4", print_background=True)

                    (out_dir / "meta.txt").write_text(
                        f"url={url}\narchived_at={ts}\n", encoding="utf-8"
                    )

                except Exception as e:
                    st.error(f"Gagal archive {url} : {e}")

            browser.close()

    st.success("Selesai! Arsip berhasil dibuat.")
    st.rerun()

# ---------- Input URL ----------
st.subheader("➕ Tambah Website")
targets = load_targets()

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

# ---------- RUN BUTTON (INI YANG BARU) ----------
st.divider()
st.subheader("▶️ Jalankan Archive Sekarang")

if st.button("🚀 Jalankan Sekarang"):
    run_archive_now()

# ---------- Archive Viewer ----------
st.divider()
st.subheader("🗂️ Arsip")

if ARCHIVE_DIR.exists():
    domains = sorted([d.name for d in ARCHIVE_DIR.iterdir() if d.is_dir()])
    if domains:
        domain = st.selectbox("Pilih Domain", domains)
        runs = sorted([r.name for r in (ARCHIVE_DIR/domain).iterdir()], reverse=True)
        run = st.selectbox("Pilih Snapshot", runs)

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
