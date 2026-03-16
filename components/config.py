import os
from dotenv import load_dotenv

load_dotenv()

# ── LLM ──────────────────────────────────────
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY")
MODEL            = "llama3.1-8b"

# ── Database ──────────────────────────────────
DB_NAME       = "database.sqlite"
METADATA_FILE = "schema_metadata.json"
MAILY_PREFIX  = "maily__"

# ── SMTP (Gmail) ──────────────────────────────
SMTP_HOST     = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER     = os.environ.get("SMTP_USER")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SENDER_NAME   = os.environ.get("SENDER_NAME", "Maily")