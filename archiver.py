# archiver.py
import json
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

TARGET_FILE = "targets.json"
BASE_DIR = Path("archives")
BASE_DIR.mkdir(exist_ok=True)

def domain_from_url(url):
    return urlparse(url).netloc.replace(":", "_")

def archive_one(page, url: str):
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    domain = domain_from_url(url)

    out_dir = BASE_DIR / domain / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    page.goto(url, wait_until="networkidle", timeout=90_000)

    (out_dir / "page.html").write_text(page.content(), encoding="utf-8")
    page.screenshot(path=str(out_dir / "screenshot.png"), full_page=True)
    page.pdf(path=str(out_dir / "page.pdf"), format="A4", print_background=True)

    (out_dir / "meta.txt").write_text(
        f"url={url}\narchived_at={ts}\n", encoding="utf-8"
    )

def main():
    if not Path(TARGET_FILE).exists():
        print("targets.json not found")
        return

    targets = json.loads(Path(TARGET_FILE).read_text())

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for url in targets:
            try:
                print("Archiving:", url)
                archive_one(page, url)
            except Exception as e:
                print("Failed:", url, e)

        browser.close()

if __name__ == "__main__":
    main()
