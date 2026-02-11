import os, json
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]

def drive_service():
    token_info = json.loads(os.environ["GDRIVE_TOKEN_JSON"])
    creds = Credentials.from_authorized_user_info(token_info, DRIVE_SCOPES)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return build("drive", "v3", credentials=creds)

def upload(pdf, filename):
    service = drive_service()
    media = MediaFileUpload(pdf, mimetype="application/pdf")
    meta = {"name": filename, "parents": [os.environ["GDRIVE_FOLDER_ID"]]}
    service.files().create(body=meta, media_body=media).execute()

def domain(url):
    return urlparse(url).netloc.replace(":", "_")

targets = json.loads(Path("targets.json").read_text())

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()

    for url in targets:
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        d = domain(url)
        out = Path("archives") / d / ts
        out.mkdir(parents=True, exist_ok=True)

        page.goto(url, wait_until="networkidle")

        pdf = out / "page.pdf"
        page.pdf(path=str(pdf), format="A4", print_background=True)

        upload(str(pdf), f"{d}_{ts}.pdf")

    browser.close()
