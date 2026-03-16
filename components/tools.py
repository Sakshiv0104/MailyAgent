import sqlite3
import json
import re
from datetime import datetime
from components.config import DB_NAME, METADATA_FILE, MAILY_PREFIX


def load_metadata() -> dict:
    with open(METADATA_FILE, "r") as f:
        return json.load(f)


def save_metadata(metadata: dict):
    with open(METADATA_FILE, "w") as f:
        json.dump(metadata, f, indent=2)


def build_name_expr(name_col_raw: str) -> str:
    cleaned = re.sub(r'[+,"\'\[\]]', ' ', name_col_raw)
    parts   = [p.strip() for p in cleaned.split() if p.strip()]
    if len(parts) == 1:
        return f"TRIM([{parts[0]}])"
    joined = " || ' ' || ".join([f"COALESCE(TRIM([{p}]), '')" for p in parts])
    return f"TRIM({joined})"


def create_maily_table(table_name: str, mapping: dict, entity_label: str) -> str:
    id_col           = mapping["id_col"]
    name_col_raw     = mapping["name_col"]
    email_col        = mapping["email_col"]
    maily_table_name = f"{MAILY_PREFIX}{entity_label}_email"
    name_expr        = build_name_expr(name_col_raw)

    conn = sqlite3.connect(DB_NAME)
    conn.execute(f"DROP TABLE IF EXISTS [{maily_table_name}]")
    conn.execute(f"""
        CREATE TABLE [{maily_table_name}] AS
        SELECT id, name, email FROM (
            SELECT id, name, email,
                ROW_NUMBER() OVER (PARTITION BY LOWER(TRIM(email)) ORDER BY id) AS rn_email
            FROM (
                SELECT
                    [{id_col}]                 AS id,
                    {name_expr}                AS name,
                    LOWER(TRIM([{email_col}])) AS email,
                    ROW_NUMBER() OVER (PARTITION BY [{id_col}] ORDER BY ROWID) AS rn_id
                FROM [{table_name}]
                WHERE [{email_col}] IS NOT NULL
                  AND TRIM([{email_col}]) != ''
                  AND LOWER(TRIM([{email_col}])) NOT IN ('none','null','n/a','na','-')
            ) WHERE rn_id = 1
        ) WHERE rn_email = 1
        ORDER BY id
    """)
    conn.commit()
    count = conn.execute(f"SELECT COUNT(*) FROM [{maily_table_name}]").fetchone()[0]
    conn.close()
    print(f"  -> Created '{maily_table_name}' with {count} unique records.")
    return maily_table_name


# ─────────────────────────────────────────────
# History — create table if not exists
# ─────────────────────────────────────────────
def ensure_history_table():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS maily_sent_history (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient_id  TEXT,
            recipient_name TEXT,
            recipient_email TEXT,
            entity_type   TEXT,
            subject       TEXT,
            body          TEXT,
            sent_at       TEXT
        )
    """)
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# History — save a sent email
# ─────────────────────────────────────────────
def save_sent_email(state: dict):
    ensure_history_table()
    conn = sqlite3.connect(DB_NAME)
    conn.execute("""
        INSERT INTO maily_sent_history
            (recipient_id, recipient_name, recipient_email, entity_type, subject, body, sent_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        state.get("recipient_id"),
        state.get("recipient_name"),
        state.get("recipient_email"),
        state.get("entity_type"),
        state.get("email_subject"),
        state.get("email_body"),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# History — get emails sent to one recipient
# ─────────────────────────────────────────────
def get_email_history(recipient_id: str) -> list:
    ensure_history_table()
    conn = sqlite3.connect(DB_NAME)
    rows = conn.execute("""
        SELECT subject, body, sent_at
        FROM maily_sent_history
        WHERE recipient_id = ?
        ORDER BY sent_at DESC
    """, (recipient_id,)).fetchall()
    conn.close()
    return [{"subject": r[0], "body": r[1], "sent_at": r[2]} for r in rows]


# ─────────────────────────────────────────────
# History — clear history for one recipient
# ─────────────────────────────────────────────
def clear_recipient_history(recipient_id: str):
    ensure_history_table()
    conn = sqlite3.connect(DB_NAME)
    conn.execute("DELETE FROM maily_sent_history WHERE recipient_id = ?", (recipient_id,))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# History — clear ALL history
# ─────────────────────────────────────────────
def clear_all_history():
    ensure_history_table()
    conn = sqlite3.connect(DB_NAME)
    conn.execute("DELETE FROM maily_sent_history")
    conn.commit()
    conn.close()

# ─────────────────────────────────────────────
# History — get ALL sent emails across everyone
# ─────────────────────────────────────────────
def get_all_history() -> list:
    ensure_history_table()
    conn = sqlite3.connect(DB_NAME)
    rows = conn.execute("""
        SELECT recipient_name, recipient_email, entity_type, subject, body, sent_at
        FROM maily_sent_history
        ORDER BY sent_at DESC
    """).fetchall()
    conn.close()
    return [
        {
            "recipient_name" : r[0],
            "recipient_email": r[1],
            "entity_type"    : r[2],
            "subject"        : r[3],
            "body"           : r[4],
            "sent_at"        : r[5]
        }
        for r in rows
    ]