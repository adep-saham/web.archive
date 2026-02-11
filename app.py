import json
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

import streamlit as st
from playwright.sync_api import sync_playwright

# ===== Google Drive OAuth =====
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]
TOKEN_FILE = Path("token.json")
DRIVE_FOLDER_ID = "1EbdyUhfW1e1vAHTHbTiir44TH0rzEjB_"


# ================= CONFIG =================
TARGET_FILE = Path("targets.json")
ARCHIVE_DIR = Path("archives")
ARCHIVE_DIR.mkdir(exist_ok=True)

st.set_page_config(layout="wide")
st.title("📦 Daily Web Archive Manager")


# ================= Drive Helper =================
def drive_service():
    if not TOKEN_FILE.exists():
        st.error("token.json belum ada. Jalankan: python drive_auth.py")
        st.stop()

    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), DRIVE_SCOPES)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return build("drive", "v3", credentials=creds)


def upload_pdf_to_drive(pdf_path: str, filename: str):
    service = drive_service()
    media = MediaFileUpload(pdf_path, mimetype="application/pdf")

    meta = {
        "name": filename,
        "parents": [DRIVE_FOLDER_ID],
    }

    file = service.files().create(
        body=meta,
        media_body=media,
        fields="webViewLink"
    ).execute()

    return file.get("webViewLink")


# ================= Helpers =================
def domain_from_url(url: str) -> str:
    return urlparse(url).netloc.replace(":", "_")


def load_targets():
    if TARGET_FILE.exists():
        return json.loads(TARGET_FILE.read_text())
    return []


def save_targets(tgts):
    TARGET_FILE.write_text(json.dumps(tgts, indent=2))


# ================= ARCHIVE PROCESS =================
def run_archive():
    targets = load_targets()
    if not targets:
        st.warning("Belum ada URL.")
        return

    results = []

    with st.spinner("Mengarsipkan website..."):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            for url in targets:
                ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                domain = domain_from_url(url)

                out_dir = ARCHIVE_DIR / domain / ts
                out_dir.mkdir(parents=True, exist_ok=True)

                try:
                    page.goto(url, wait_until="networkidle", timeout=90000)

                    html_file = out_dir / "page.html"
                    png_file = out_dir / "screenshot.png"
                    pdf_file = out_dir / "page.pdf"

                    html_file.write_text(page.content(), encoding="utf-8")
                    page.screenshot(path=str(png_file), full_page=True)
                    page.pdf(path=str(pdf_file), format="A4", print_background=True)

                    # Upload PDF ke Drive
                    link = upload_pdf_to_drive(
                        str(pdf_file),
                        f"{domain}_{ts}.pdf"
                    )

                    results.append((url, "OK", link))

                except Exception as e:
                    results.append((url, f"FAILED: {e}", None))

            browser.close()

    st.success("Selesai.")
    for url, status, link in results:
        st.write(f"**{status}** — {url}")
        if link:
            st.write("Drive:", link)


# ================= UI =================
targets = load_targets()

st.subheader("➕ Tambah Website")
new_url = st.text_input("Masukkan URL")

if st.button("Tambah"):
    if new_url and new_url not in targets:
        targets.append(new_url)
        save_targets(targets)
        st.rerun()

st.subheader("🌐 Daftar Target")
for url in targets:
    c1, c2 = st.columns([8,1])
    c1.write(url)
    if c2.button("❌", key=url):
        targets.remove(url)
        save_targets(targets)
        st.rerun()

st.divider()
st.subheader("▶️ Jalankan Archive Sekarang")

if st.button("🚀 Jalankan Sekarang"):
    run_archive()

st.divider()
st.subheader("🗂️ Arsip Lokal")

domains = sorted([d.name for d in ARCHIVE_DIR.iterdir() if d.is_dir()])
if domains:
    domain = st.selectbox("Pilih Domain", domains)
    runs = sorted([r.name for r in (ARCHIVE_DIR/domain).iterdir()], reverse=True)
    run = st.selectbox("Pilih Snapshot", runs)

    folder = ARCHIVE_DIR/domain/run
    st.image(str(folder/"screenshot.png"), use_container_width=True)

    for fn in ["page.pdf", "page.html", "screenshot.png"]:
        f = folder/fn
        if f.exists():
            st.download_button(
                f"Download {fn}",
                f.read_bytes(),
                file_name=f"{domain}_{run}_{fn}"
            )
