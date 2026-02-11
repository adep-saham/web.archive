import json
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


TARGET_FILE = Path("targets.json")
ARCHIVE_DIR = Path("archives")
ARCHIVE_DIR.mkdir(exist_ok=True)


def domain_from_url(url: str) -> str:
    return urlparse(url).netloc.replace(":", "_").strip() or "unknown-domain"


def load_targets() -> list[str]:
    if TARGET_FILE.exists():
        try:
            return json.loads(TARGET_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def drive_service_from_sa_info(sa_info: dict):
    sa_info = dict(sa_info)
    sa_info.pop("spreadsheet", None)  # kalau ada, buang
    creds = service_account.Credentials.from_service_account_info(
        sa_info,
        scopes=["https://www.googleapis.com/auth/drive.file"],
    )
    return build("drive", "v3", credentials=creds)


def upload_pdf_to_drive(sa_info: dict, folder_id: str, pdf_path: str, filename: str) -> str | None:
    service = drive_service_from_sa_info(sa_info)

    media = MediaFileUpload(pdf_path, mimetype="application/pdf", resumable=True)
    meta = {"name": filename, "parents": [folder_id]}

    created = service.files().create(
        body=meta,
        media_body=media,
        fields="id, webViewLink"
    ).execute()

    return created.get("webViewLink")


def run_archive(sa_info: dict, folder_id: str, upload_to_drive: bool = True):
    targets = load_targets()
    if not targets:
        print("No targets found in targets.json")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for url in targets:
            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            domain = domain_from_url(url)

            out_dir = ARCHIVE_DIR / domain / ts
            out_dir.mkdir(parents=True, exist_ok=True)

            try:
                print("Archiving:", url)
                page.goto(url, wait_until="networkidle", timeout=90_000)

                html_file = out_dir / "page.html"
                png_file = out_dir / "screenshot.png"
                pdf_file = out_dir / "page.pdf"
                meta_file = out_dir / "meta.txt"

                html_file.write_text(page.content(), encoding="utf-8")
                page.screenshot(path=str(png_file), full_page=True)
                page.pdf(path=str(pdf_file), format="A4", print_background=True)

                meta_file.write_text(f"url={url}\narchived_at={ts}\n", encoding="utf-8")

                if upload_to_drive:
                    drive_name = f"{domain}_{ts}.pdf"
                    link = upload_pdf_to_drive(sa_info, folder_id, str(pdf_file), drive_name)
                    print("Uploaded to Drive:", drive_name, link or "")

            except Exception as e:
                print("FAILED:", url, e)

        browser.close()


if __name__ == "__main__":
    """
    Cara pakai:
    - Kamu set SERVICE ACCOUNT INFO & folder_id di environment / file lokal (jangan hardcode key di sini).
    - Untuk Streamlit Cloud, lebih enak jalankan lewat app.py (tombol Run), scheduler biasanya di server/VM.
    """
    print("Run this script from your scheduler environment.")
    print("Tip: load secrets/service-account JSON from env var then call run_archive().")
