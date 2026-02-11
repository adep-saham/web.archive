import json
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

import streamlit as st
from playwright.sync_api import sync_playwright

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


# =========================
# Config
# =========================
TARGET_FILE = Path("targets.json")
ARCHIVE_DIR = Path("archives")
ARCHIVE_DIR.mkdir(exist_ok=True)

st.set_page_config(page_title="Daily Web Archive Manager", layout="wide")
st.title("📦 Daily Web Archive Manager")


# =========================
# Helpers
# =========================
def domain_from_url(url: str) -> str:
    return urlparse(url).netloc.replace(":", "_").strip() or "unknown-domain"


def load_targets() -> list[str]:
    if TARGET_FILE.exists():
        try:
            return json.loads(TARGET_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_targets(tgts: list[str]) -> None:
    TARGET_FILE.write_text(json.dumps(tgts, indent=2), encoding="utf-8")


def _drive_service():
    """
    Reuse credential dari [connections.gsheets] di secrets.
    Wajib: di secrets harus ada gdrive_folder_id di dalam [connections.gsheets]
    """
    info = dict(st.secrets["connections"]["gsheets"])
    folder_id = info.get("gdrive_folder_id")
    if not folder_id:
        raise RuntimeError("gdrive_folder_id belum ada di secrets pada [connections.gsheets].")

    # buang field non-service-account kalau ada
    info.pop("spreadsheet", None)

    creds = service_account.Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/drive.file"],
    )
    return build("drive", "v3", credentials=creds)


def upload_pdf_to_drive(pdf_path: str, filename: str) -> str | None:
    """
    Upload PDF ke folder Drive yang ada di secrets.
    Return link webViewLink jika tersedia.
    """
    info = dict(st.secrets["connections"]["gsheets"])
    folder_id = info.get("gdrive_folder_id")
    if not folder_id:
        raise RuntimeError("gdrive_folder_id belum ada di secrets pada [connections.gsheets].")

    service = _drive_service()

    media = MediaFileUpload(pdf_path, mimetype="application/pdf", resumable=True)
    meta = {"name": filename, "parents": [folder_id]}

    created = service.files().create(
        body=meta,
        media_body=media,
        fields="id, webViewLink"
    ).execute()

    return created.get("webViewLink")


def archive_all_now(upload_to_drive: bool = True):
    targets = load_targets()
    if not targets:
        st.warning("Belum ada URL di daftar target.")
        return

    results = []

    with st.spinner("Mengarsipkan semua website..."):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            for url in targets:
                ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                domain = domain_from_url(url)

                out_dir = ARCHIVE_DIR / domain / ts
                out_dir.mkdir(parents=True, exist_ok=True)

                try:
                    page.goto(url, wait_until="networkidle", timeout=90_000)

                    html_file = out_dir / "page.html"
                    png_file = out_dir / "screenshot.png"
                    pdf_file = out_dir / "page.pdf"
                    meta_file = out_dir / "meta.txt"

                    html_file.write_text(page.content(), encoding="utf-8")
                    page.screenshot(path=str(png_file), full_page=True)
                    page.pdf(path=str(pdf_file), format="A4", print_background=True)

                    meta_file.write_text(f"url={url}\narchived_at={ts}\n", encoding="utf-8")

                    drive_link = None
                    if upload_to_drive:
                        drive_name = f"{domain}_{ts}.pdf"
                        drive_link = upload_pdf_to_drive(str(pdf_file), drive_name)

                    results.append((url, "OK", str(out_dir), drive_link))

                except Exception as e:
                    results.append((url, f"FAILED: {e}", str(out_dir), None))

            browser.close()

    st.success("Selesai.")
    st.session_state["last_results"] = results
    st.rerun()


# =========================
# UI - Targets
# =========================
targets = load_targets()

st.subheader("➕ Tambah Website")
new_url = st.text_input("Masukkan URL (contoh: https://stargold.id/price/)")
col_add1, col_add2 = st.columns([1, 5])

with col_add1:
    if st.button("Tambah"):
        if new_url:
            new_url = new_url.strip()
            if new_url not in targets:
                targets.append(new_url)
                save_targets(targets)
                st.success("URL ditambahkan.")
                st.rerun()
            else:
                st.info("URL sudah ada di daftar.")

st.subheader("🌐 Daftar Target Archive")
if not targets:
    st.info("Belum ada target. Tambahkan URL di atas.")
else:
    for url in targets:
        c1, c2 = st.columns([8, 1])
        c1.write(url)
        if c2.button("❌", key=f"del-{url}"):
            targets.remove(url)
            save_targets(targets)
            st.rerun()

# =========================
# UI - Run Now
# =========================
st.divider()
st.subheader("▶️ Jalankan Archive Sekarang")

upload_to_drive = st.toggle("Upload PDF ke Google Drive", value=True)

if st.button("🚀 Jalankan Sekarang"):
    archive_all_now(upload_to_drive=upload_to_drive)

# tampilkan hasil run terakhir (kalau ada)
if "last_results" in st.session_state:
    st.subheader("📋 Hasil Run Terakhir")
    for url, status, out_dir, drive_link in st.session_state["last_results"]:
        st.write(f"- **{status}** — {url}")
        st.caption(f"Local: {out_dir}")
        if drive_link:
            st.write(f"Drive: {drive_link}")

# =========================
# UI - Viewer Arsip Lokal
# =========================
st.divider()
st.subheader("🗂️ Viewer Arsip (Lokal)")

domains = sorted([d.name for d in ARCHIVE_DIR.iterdir() if d.is_dir()])
if not domains:
    st.info("Belum ada arsip lokal.")
else:
    domain = st.selectbox("Pilih Domain", domains)
    runs = sorted([r.name for r in (ARCHIVE_DIR / domain).iterdir() if r.is_dir()], reverse=True)
    run = st.selectbox("Pilih Snapshot", runs)

    folder = ARCHIVE_DIR / domain / run

    png = folder / "screenshot.png"
    if png.exists():
        st.image(str(png), use_container_width=True)

    for fn, mime in [("page.pdf", "application/pdf"), ("page.html", "text/html"), ("screenshot.png", "image/png")]:
        f = folder / fn
        if f.exists():
            st.download_button(
                label=f"Download {fn}",
                data=f.read_bytes(),
                file_name=f"{domain}_{run}_{fn}",
                mime=mime
            )
