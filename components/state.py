from typing import Optional
from typing_extensions import TypedDict

class MailyState(TypedDict):

    # ── Setup graph fields ───────────────────────
    base_tables    : dict
    email_tables   : list
    pending_tables : list
    created_tables : list
    maily_info     : dict
    db_description : Optional[str]

    # ── Email compose graph fields ───────────────
    recipient_id    : Optional[str]
    recipient_name  : Optional[str]
    recipient_email : Optional[str]
    entity_type     : Optional[str]
    user_prompt     : Optional[str]

    needs_clarification    : Optional[bool]
    clarification_question : Optional[str]
    clarification_answer   : Optional[str]

    email_subject  : Optional[str]
    email_body     : Optional[str]
    finalized      : Optional[bool]

    attachments   : Optional[list] # List of dicts: [{"filename": "doc.pdf", "data": bytes}]
    
    # ── History ──────────────────────────────────
    # LLM generated summary of past emails to this recipient
    history_summary : Optional[str]

    # ── Send ─────────────────────────────────────
    email_sent     : Optional[bool]
    error          : Optional[str]