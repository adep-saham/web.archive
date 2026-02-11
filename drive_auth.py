# drive_auth.py
from __future__ import annotations

from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

CREDENTIALS_FILE = Path("credentials.json")
TOKEN_FILE = Path("token.json")

def main():
    if not CREDENTIALS_FILE.exists():
        raise SystemExit("credentials.json tidak ditemukan (taruh di folder project).")

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)

    # Ini akan buka browser untuk login dan consent
    creds = flow.run_local_server(port=0)

    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    print("✅ token.json berhasil dibuat. Simpan aman, jangan dipush ke repo publik.")

if __name__ == "__main__":
    main()
