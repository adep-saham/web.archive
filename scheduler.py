import os
import json
import traceback
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse, quote_plus

import requests
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

NAV_TIMEOUT_MS = 180_000
POST_LOAD_WAIT_MS = 4000
RETRIES = 2


# =========================
# Helpers
# =========================
def domain_from_url(url: str) -> str:
    return urlparse(url).netloc.replace(":", "_") or "unknown"


def is_tokopedia(url: str) -> bool:
    return "tokopedia.com" in url.lower()


def drive_service():
    token_info = json.loads(os.environ["GDRIVE_TOKEN_JSON"])
    creds = Credentials.from_authorized_user_info(token_info, DRIVE_SCOPES)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return build("drive", "v3", credentials=creds)


def upload_file(service, folder_id: str, file_path: str, filename: str, mimetype: str):
    media = MediaFileUpload(file_path, mimetype=mimetype, resumable=True)
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
            if attempt < RETRIES:
                page.wait_for_timeout(1500)
                continue
            raise last_err


# =========================
# Tokopedia via Google WebCache
# =========================
def archive_tokopedia_webcache(url: str, out_dir: Path) -> Path:
    """
    Archive Tokopedia via Google WebCache snapshot
    supaya tidak kena anti-bot CI.
    """
    encoded_url = quote_plus(url)
    cache_url = f"https://webcache.bullseye.net/search?q=cache:{encoded_url}"

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    resp = requests.get(cache_url, headers=headers, timeout=60)
    resp.raise_for_status()

    html_file = out_dir / "tokopedia_webcache.html"
    html_file.write_text(resp.text, encoding="utf-8")

    return html_file


# =========================
# Main
# =========================
def main():
    if not TARGET_FILE.exists():
        print("targets.json tidak ditemukan.")
        return

    targets = json.loads(TARGET_FILE.read_text(encoding="utf-8"))
    if not targets:
        print("targets.json kosong.")
        return

    folder_id = os.environ["GDRIVE_FOLDER_ID"]
    service = drive_service()

    tokopedia_urls = [u for u in targets if is_tokopedia(u)]
    normal_urls = [u for u in targets if not is_tokopedia(u)]

    # =========================
    # NORMAL WEBSITE → PDF
    # =========================
    if normal_urls:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-http2",
                    "--disable-quic",
                ],
            )

            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                ignore_https_errors=True,
            )

            for url in normal_urls:
                ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                domain = domain_from_url(url)

                out_dir = ARCHIVE_DIR / domain / ts
                out_dir.mkdir(parents=True, exist_ok=True)

                print("Archiving:", url)

                page = context.new_page()
                page.set_default_navigation_timeout(NAV_TIMEOUT_MS)

                try:
                    goto_with_retry(page, url)

                    pdf_file = out_dir / "page.pdf"
                    page.pdf(path=str(pdf_file), format="A4", print_background=True)

                    out_name = f"{domain}_{ts}.pdf"
                    upload_file(service, folder_id, str(pdf_file), out_name, "application/pdf")

                    print("Uploaded:", out_name)

                except Exception:
                    print("FAILED:", url)
                    traceback.print_exc()

                finally:
                    page.close()

            context.close()
            browser.close()

    # =========================
    # TOKOPEDIA → WEB CACHE
    # =========================
    for url in tokopedia_urls:
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        domain = domain_from_url(url)

        out_dir = ARCHIVE_DIR / domain / ts
        out_dir.mkdir(parents=True, exist_ok=True)

        print("Archiving (WebCache):", url)

        try:
            html_file = archive_tokopedia_webcache(url, out_dir)

            out_name = f"{domain}_{ts}_webcache.html"
            upload_file(service, folder_id, str(html_file), out_name, "text/html")

            print("Uploaded:", out_name)

        except Exception:
            print("FAILED:", url)
            traceback.print_exc()


if __name__ == "__main__":
    main()
