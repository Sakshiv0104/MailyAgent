import os
import json
import smtplib
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase
from email import encoders

from cerebras.cloud.sdk import Cerebras
from components.config import (
    CEREBRAS_API_KEY, MODEL,
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SENDER_NAME
)
from components.state import MailyState
from components.tools import (
    load_metadata, save_metadata, create_maily_table,
    get_email_history, save_sent_email
)

client = Cerebras(api_key=CEREBRAS_API_KEY)

def llm(prompt: str, max_tokens: int = 300, temperature: float = 0.3) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()

def parse_json_from_llm(raw: str, context: str = "unknown") -> dict:
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON found for '{context}'.\nGot: {raw}")
    return json.loads(raw[start:end].strip())

# ═════════════════════════════════════════════
# SETUP GRAPH NODES
# ═════════════════════════════════════════════

def node_detect(state: MailyState) -> MailyState:
    print("\n[Node 1 - Detect] Scanning for email tables...")
    email_tables = []
    for table_name, sample in state["base_tables"].items():
        for col, val in sample.items():
            if "email" in col.lower() or "mail" in col.lower():
                email_tables.append(table_name)
                break
            if isinstance(val, str) and "@" in val and "." in val:
                email_tables.append(table_name)
                break
    print(f"[Node 1 - Detect] Found: {email_tables}")
    return {**state, "email_tables": email_tables, "pending_tables": email_tables.copy()}

def node_process(state: MailyState) -> MailyState:
    pending    = state["pending_tables"]
    table_name = pending[0]
    sample     = state["base_tables"][table_name]
    print(f"\n[Node 2 - Process] Working on '{table_name}'...")

    KNOWN = [
        "customer", "supplier", "employee", "vendor", "partner",
        "user", "member", "agent", "client", "staff",
        "buyer", "seller", "merchant", "distributor", "contractor"
    ]
    entity_type = None

    clean = table_name.lower().rstrip("s")
    for e in KNOWN:
        if e in clean or clean in e:
            entity_type = e
            print(f"  Entity: {entity_type} (table name)")
            break

    if not entity_type:
        for col in sample.keys():
            for e in KNOWN:
                if col.lower().startswith(e + "_") or col.lower().endswith("_" + e):
                    entity_type = e
                    print(f"  Entity: {entity_type} (column '{col}')")
                    break
            if entity_type:
                break

    if not entity_type:
        p = (
            "Table: " + table_name + "\n"
            "Columns: " + ", ".join(sample.keys()) + "\n"
            "Reply ONE word: customer/supplier/employee/vendor/partner/user/member/agent/client.\n"
            "Never: contact, person, entity, record."
        )
        entity_type = llm(p, max_tokens=10).lower().strip().split()[0]
        print(f"  Entity: {entity_type} (LLM)")

    columns_info = "\n".join(["  - " + col + ": (sample: '" + str(val) + "')" for col, val in sample.items()])
    p = (
        "Table: " + table_name + "\n"
        "Columns:\n" + columns_info + "\n\n"
        "Find these 3 columns:\n"
        "1. id_col - unique identifier\n"
        "2. name_col - entity OWN name. PREFER: supplier_name, company_name, full_name. "
        "If split use 'first_name last_name'. AVOID: contact_name, contact_person\n"
        "3. email_col - email address (look for @ in samples)\n\n"
        "Use ONLY existing column names. Reply valid JSON only, no markdown.\n"
        '{"id_col": "...", "name_col": "...", "email_col": "..."}'
    )
    raw = llm(p, max_tokens=200)
    print(f"  LLM raw: {raw[:150]}")
    mapping = parse_json_from_llm(raw, table_name)
    print(f"  Mapping: {mapping}")

    maily_table_name = create_maily_table(table_name, mapping, entity_type)
    created = state.get("created_tables", []) + [maily_table_name]
    info    = state.get("maily_info", {})
    info[maily_table_name] = {
        "source_table": table_name,
        "entity_type" : entity_type,
        "id_col"      : mapping["id_col"],
        "name_col"    : mapping["name_col"],
        "email_col"   : mapping["email_col"]
    }
    return {**state, "pending_tables": pending[1:], "created_tables": created, "maily_info": info}

def node_generate_description(state: MailyState) -> MailyState:
    print("\n[Node 3 - Description] Generating database description...")
    metadata    = load_metadata()
    base_tables = metadata.get("base_tables", {})
    maily_info  = state.get("maily_info", {})

    tables_summary = ["- " + t + ": " + ", ".join(list(s.keys())) for t, s in base_tables.items()]
    email_summary  = ["- " + i["entity_type"].title() + "s (" + i["source_table"] + ")" for i in maily_info.values()]

    p = (
        "You are describing a business database to a non-technical user. "
        "Write 2-3 sentences MAX. Be warm and clear.\n\n"
        "Tables:\n" + "\n".join(tables_summary) + "\n\n"
        "For email I can reach:\n" + "\n".join(email_summary) + "\n\n"
        "Start with: 'I currently hold a database of...'"
    )
    description = llm(p, max_tokens=150)
    print(f"[Node 3 - Description] {description}")
    return {**state, "db_description": description}

def node_save(state: MailyState) -> MailyState:
    print("\n[Node 4 - Save] Writing to schema_metadata.json...")
    metadata = load_metadata()
    metadata["maily"]          = state["maily_info"]
    metadata["db_description"] = state.get("db_description", "")
    save_metadata(metadata)
    print("[Node 4 - Save] Done.")
    return state

def route_after_process(state: MailyState) -> str:
    return "loop" if state["pending_tables"] else "done"

# ═════════════════════════════════════════════
# EMAIL COMPOSE GRAPH NODES
# ═════════════════════════════════════════════

def node_summarize_history(state: MailyState) -> MailyState:
    print("\n[Node 0 - History] Checking past emails...")

    history = get_email_history(state["recipient_id"])

    if not history:
        print("[Node 0 - History] No history found.")
        return {**state, "history_summary": None}

    past = "\n".join([f"- [{h['sent_at']}] Subject: {h['subject']}" for h in history[:10]])

    p = (
        "Summarize the email history with this person in 1-2 short sentences.\n"
        "Be concise and informative — mention the topics and rough timeframe.\n\n"
        "Recipient: " + state["recipient_name"] + "\n"
        "Past emails sent:\n" + past + "\n\n"
        "Write only the summary, no preamble."
    )

    summary = llm(p, max_tokens=100, temperature=0.3)
    print(f"[Node 0 - History] Summary: {summary}")
    return {**state, "history_summary": summary}

def node_analyze_prompt(state: MailyState) -> MailyState:
    print("\n[Node A - Analyze] Reading user prompt...")

    p = (
        "You help compose business emails. Analyze this request and decide if you need to ask ONE question.\n\n"
        "Recipient: " + state["recipient_name"] + " (" + state["entity_type"] + ")\n"
        "Request: " + state["user_prompt"] + "\n\n"
        "RULES:\n"
        "- If the request mentions something vague that needs a specific value, ASK.\n"
        "  Examples of when to ask:\n"
        "  'ask about delivery' -> ask: which order or product?\n"
        "  'follow up on invoice' -> ask: what is the invoice number or amount?\n"
        "  'remind about meeting' -> ask: what is the date and time?\n"
        "  'ask about price' -> ask: which product or service?\n"
        "- If the request is specific enough, do NOT ask.\n"
        "  Examples of when NOT to ask:\n"
        "  'tell him payment is overdue' -> clear, no question\n"
        "  'introduce ourselves' -> clear, no question\n\n"
        "Reply valid JSON only:\n"
        '{"needs_clarification": true, "question": "your specific question"}\n'
        "or\n"
        '{"needs_clarification": false, "question": null}'
    )

    raw    = llm(p, max_tokens=150, temperature=0.7)
    result = parse_json_from_llm(raw, "analyze_prompt")

    needs    = result.get("needs_clarification", False)
    question = result.get("question", None)

    print(f"[Node A - Analyze] Needs clarification: {needs}")
    if needs:
        print(f"[Node A - Analyze] Question: {question}")

    return {**state, "needs_clarification": needs, "clarification_question": question}

def node_draft_email(state: MailyState) -> MailyState:
    print("\n[Node B - Draft] Composing email...")

    extra_context = ""
    answer = state.get("clarification_answer", None)
    if answer and answer.lower() != "skip":
        extra_context = "\nAdditional info: " + answer

    history_context = ""
    if state.get("history_summary"):
        history_context = "\nPrevious email history with this person: " + state["history_summary"]

    p = (
        "Compose a formal business email.\n\n"
        "Recipient name : " + state["recipient_name"] + "\n"
        "Recipient type : " + state["entity_type"] + "\n"
        "What to say    : " + state["user_prompt"]
        + extra_context
        + history_context + "\n\n"
        "Write a professional, warm email with proper greeting and sign-off.\n\n"
        "YOU MUST reply in EXACTLY this format. First line MUST be SUBJECT:\n"
        "SUBJECT: <subject line>\n"
        "BODY:\n"
        "<email body>\n\n"
        "Do NOT put anything before SUBJECT. Do NOT repeat SUBJECT inside the body."
    )

    raw = llm(p, max_tokens=600, temperature=0.5)

    subject = ""
    body    = raw
    lines   = raw.strip().split("\n")

    subject_idx = None
    body_idx    = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.upper().startswith("SUBJECT:") and subject_idx is None:
            subject     = stripped[len("SUBJECT:"):].strip()
            subject_idx = i
        if stripped.upper().startswith("BODY:") and body_idx is None:
            body_idx = i

    if body_idx is not None:
        body = "\n".join(lines[body_idx + 1:]).strip()
    elif subject_idx is not None:
        body = "\n".join(lines[subject_idx + 1:]).strip()

    body = body.replace("Sent via Maily | Powered by Agent Maily", "").strip()
    body = re.sub(r'--\s*$', '', body).strip()
    
    signature = "\n\n--\nSent via Maily | Powered by Agent Maily"
    body = body + signature

    return {**state, "email_subject": subject, "email_body": body}

def node_send_email(state: MailyState) -> MailyState:
    print(f"\n[Node C - Send] Sending to {state['recipient_email']}...")

    if not SMTP_USER or not SMTP_PASSWORD:
        raise ValueError("SMTP credentials missing. Check SMTP_USER and SMTP_PASSWORD in .env")

    # 1. ROOT Message (mixed) to support attachments
    msg = MIMEMultipart("mixed")
    msg["Subject"] = state["email_subject"]
    msg["From"]    = f"{SENDER_NAME} <{SMTP_USER}>"
    msg["To"]      = f"{state['recipient_name']} <{state['recipient_email']}>"

    # 2. RELATED Message for HTML + Inline Logo
    msg_related = MIMEMultipart("related")
    msg.attach(msg_related)

    # 3. ALTERNATIVE Message for Plain/HTML
    msg_alternative = MIMEMultipart("alternative")
    msg_related.attach(msg_alternative)

    # Attach Plain Text
    text_body = state["email_body"]
    msg_alternative.attach(MIMEText(text_body, "plain"))

    # 👇 SMART HTML CONSTRUCTION (Separates text, logo, and signature) 👇
    # Look for the "--\n" to separate the message from the signature
    parts = text_body.rsplit("--\n", 1)
    
    if len(parts) == 2:
        # If found, split them up so we can sandwich the logo
        main_text = parts[0].strip().replace("\n", "<br>")
        sig_text  = "--<br>" + parts[1].strip().replace("\n", "<br>")
    else:
        # Fallback if the user deleted the dashes in the UI
        main_text = text_body.replace("\n", "<br>")
        sig_text  = ""

    # Build the HTML with explicit ZERO margins between logo and text
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; font-size: 14px; color: #111827; margin: 0; padding: 0;">
            <div style="margin-bottom: 20px;">
                {main_text}
            </div>
            
            <img src="cid:maily_logo" alt="Agent Maily Logo" width="150" style="display: block; width: 150px; height: auto; border: none; margin: 0; padding: 0;" />
            
            <div style="margin: 0; padding: 0; margin-top: 4px; font-size: 13px; color: #4b5563;">
                {sig_text}
            </div>
        </body>
    </html>
    """
    msg_alternative.attach(MIMEText(html_body, "html"))

    # Attach Inline Logo
    logo_path = "pictures/AgentMaily.png"
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            img = MIMEImage(f.read())
        img.add_header("Content-ID", "<maily_logo>")
        img.add_header("Content-Disposition", "inline", filename="AgentMaily.png")
        msg_related.attach(img)

    # Attach User Files (Using robust MIMEBase encoding)
    attachments = state.get("attachments") or []
    if attachments:
        print(f" -> Found {len(attachments)} attachments, preparing to send...")
        for att in attachments:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(att["data"])
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{att["filename"]}"')
            msg.attach(part) # Add to ROOT message

    # Send Email
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, state["recipient_email"], msg.as_string())

    # Save to history
    save_sent_email(state)
    print(f"[Node C - Send] Sent + saved to history!")

    return {**state, "email_sent": True, "error": None}

def route_after_analyze(state: MailyState) -> str:
    if state.get("needs_clarification") and not state.get("clarification_answer"):
        return "ask_user"
    return "draft"