import os
import json
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
import traceback
import time

from playwright.sync_api import sync_playwright

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request

# =========================
# Config
# =========================
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]

TARGET_FILE = Path("targets.json")
ARCHIVE_DIR = Path("archives")
ARCHIVE_DIR.mkdir(exist_ok=True)

NAV_TIMEOUT_MS = 180_000  # 3 menit
POST_LOAD_WAIT_MS = 4000  # kasih napas setelah DOM ready
RETRIES = 2               # retry untuk error jaringan

# =========================
# Helpers
# =========================
def domain_from_url(url: str) -> str:
    return urlparse(url).netloc.replace(":", "_") or "unknown"

def drive_service():
    token_info = json.loads(os.environ["GDRIVE_TOKEN_JSON"])
    creds = Credentials.from_authorized_user_info(token_info, DRIVE_SCOPES)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return build("drive", "v3", credentials=creds)

def upload_pdf(service, folder_id: str, pdf_path: str, filename: str):
    media = MediaFileUpload(pdf_path, mimetype="application/pdf", resumable=True)
    meta = {"name": filename, "parents": [folder_id]}
    service.files().create(body=meta, media_body=media, fields="id").execute()

def goto_with_retry(page, url: str):
    last_err = None
    for attempt in range(RETRIES + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            page.wait_for_timeout(POST_LOAD_WAIT_MS)
            return
        except Exception as e:
            last_err = e
            # backoff kecil
            if attempt < RETRIES:
                page.wait_for_timeout(1500)
                continue
            raise last_err

# =========================
# Main
# =========================
def main():
    if not TARGET_FILE.exists():
        print("targets.json tidak ditemukan. Tidak ada yang dijalankan.")
        return

    targets = json.loads(TARGET_FILE.read_text(encoding="utf-8"))
    if not targets:
        print("targets.json kosong. Tidak ada target.")
        return

    folder_id = os.environ["GDRIVE_FOLDER_ID"]
    service = drive_service()

    with sync_playwright() as p:
        # Args ini bantu mengurangi ERR_HTTP2_PROTOCOL_ERROR (sering di CI),
        # dan juga stabilin environment GitHub Actions
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-http2",
                "--disable-quic",
            ],
        )

        # Pakai context biar setting “nempel” ke semua page
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            ignore_https_errors=True,
        )

        for url in targets:
            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            domain = domain_from_url(url)

            out_dir = ARCHIVE_DIR / domain / ts
            out_dir.mkdir(parents=True, exist_ok=True)

            print("Archiving:", url)

            # ✅ 1 URL = 1 page (ini kunci hilangkan “interrupted by another navigation”)
            page = context.new_page()
            page.set_default_navigation_timeout(NAV_TIMEOUT_MS)
            page.set_default_timeout(NAV_TIMEOUT_MS)

            try:
                goto_with_retry(page, url)

                pdf_file = out_dir / "page.pdf"
                page.pdf(path=str(pdf_file), format="A4", print_background=True)

                out_name = f"{domain}_{ts}.pdf"
                upload_pdf(service, folder_id, str(pdf_file), out_name)
                print("Uploaded:", out_name)

            except Exception:
                print("FAILED:", url)
                traceback.print_exc()

            finally:
                page.close()

        context.close()
        browser.close()


if __name__ == "__main__":
    main()
