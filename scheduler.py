import os
import json
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

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


# =========================
# Helpers
# =========================
def domain_from_url(url: str) -> str:
    return urlparse(url).netloc.replace(":", "_") or "unknown"


def drive_service():
    token_info = json.loads(os.environ["GDRIVE_TOKEN_JSON"])
    creds = Credentials.from_authorized_user_info(token_info, DRIVE_SCOPES)

    # refresh token jika expired
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return build("drive", "v3", credentials=creds)


def upload_pdf(service, folder_id: str, pdf_path: str, filename: str):
    media = MediaFileUpload(
        pdf_path,
        mimetype="application/pdf",
        resumable=True
    )
    meta = {"name": filename, "parents": [folder_id]}

    service.files().create(
        body=meta,
        media_body=media,
        fields="id"
    ).execute()


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
        browser = p.chromium.launch(headless=True)

        # buat page lebih "normal" (mengurangi kemungkinan timeout/blocked)
        page = browser.new_page(
            viewport={"width": 1280, "height": 720},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        for url in targets:
            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            domain = domain_from_url(url)

            out_dir = ARCHIVE_DIR / domain / ts
            out_dir.mkdir(parents=True, exist_ok=True)

            try:
                print("Archiving:", url)

                # networkidle sering tidak pernah tercapai (polling/analytics),
                # jadi pakai domcontentloaded + wait kecil.
                page.goto(url, wait_until="domcontentloaded", timeout=120_000)
                page.wait_for_timeout(3000)

                pdf_file = out_dir / "page.pdf"
                page.pdf(path=str(pdf_file), format="A4", print_background=True)

                upload_pdf(service, folder_id, str(pdf_file), f"{domain}_{ts}.pdf")
                print("Uploaded:", f"{domain}_{ts}.pdf")

            except Exception as e:
                print("FAILED:", url, e)

        browser.close()


if __name__ == "__main__":
    main()
