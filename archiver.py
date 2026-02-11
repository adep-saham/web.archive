# archiver.py
from pathlib import Path
from datetime import datetime
import argparse

from playwright.sync_api import sync_playwright

def archive(url: str, out_dir: str):
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    base = Path(out_dir) / ts
    base.mkdir(parents=True, exist_ok=True)

    html_path = base / "page.html"
    png_path = base / "screenshot.png"
    pdf_path = base / "page.pdf"
    meta_path = base / "meta.txt"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=90_000)

        # save rendered HTML
        html = page.content()
        html_path.write_text(html, encoding="utf-8")

        # screenshot
        page.screenshot(path=str(png_path), full_page=True)

        # print to PDF (chromium only)
        page.pdf(path=str(pdf_path), format="A4", print_background=True)

        browser.close()

    meta_path.write_text(f"url={url}\narchived_at={ts}\n", encoding="utf-8")
    return str(base)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", default="archives")
    args = ap.parse_args()
    folder = archive(args.url, args.out)
    print("Saved to:", folder)
