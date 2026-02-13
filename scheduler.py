import os
import json
import traceback
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

NAV_TIMEOUT_MS = 180_000  # 3 menit
POST_LOAD_WAIT_MS = 4000  # jeda setelah DOM ready
RETRIES = 2               # retry untuk error intermittent


# =========================
# Helpers
# =========================
def domain_from_url(url: str) -> str:
    return urlparse(url).netloc.replace(":", "_") or "unknown"


def is_tokopedia(url: str) -> bool:
    return "tokopedia.com" in url.lower()


def drive_service():
    """
    Ambil creds dari env var:
      - GDRIVE_TOKEN_JSON: string JSON hasil OAuth (authorized_user)
      - GDRIVE_FOLDER_ID: folder tujuan upload
    """
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


def apply_fast_mode(page):
    """
    Block resource berat supaya lebih cepat dan mengurangi timeout.
    Cocok untuk Tokopedia (dan situs berat lainnya).
    """
    def route_handler(route):
        rtype = route.request.resource_type
        if rtype in ("image", "media", "font"):
            return route.abort()
        return route.continue_()

    page.route("**/*", route_handler)


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
        # Args ini membantu mengurangi ERR_HTTP2_PROTOCOL_ERROR (sering di CI),
        # dan stabil di GitHub Actions.
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

        for url in targets:
            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            domain = domain_from_url(url)

            out_dir = ARCHIVE_DIR / domain / ts
            out_dir.mkdir(parents=True, exist_ok=True)

            print("Archiving:", url)

            # ✅ 1 URL = 1 page (kunci agar tidak saling “interrupt”)
            page = context.new_page()
            page.set_default_navigation_timeout(NAV_TIMEOUT_MS)
            page.set_default_timeout(NAV_TIMEOUT_MS)

            try:
                if is_tokopedia(url):
                    # Tokopedia: mode khusus (lebih stabil pakai screenshot)
                    apply_fast_mode(page)

                    # Jangan tunggu domcontentloaded (sering tidak selesai di Tokopedia)
                    page.goto(url, wait_until="commit", timeout=120_000)
                    page.wait_for_timeout(8000)

                    png_file = out_dir / "page.png"
                    page.screenshot(path=str(png_file), full_page=True)

                    out_name = f"{domain}_{ts}.png"
                    upload_file(service, folder_id, str(png_file), out_name, "image/png")
                    print("Uploaded:", out_name)

                else:
                    # Situs normal: PDF
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
                try:
                    page.close()
                except Exception:
                    pass

        try:
            context.close()
        except Exception:
            pass

        try:
            browser.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
