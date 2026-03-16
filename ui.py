import json
import sqlite3
import base64
from pathlib import Path
import streamlit as st
from maily import build_email_graph, build_send_graph
from components.tools import (
    get_email_history,
    get_all_history,
    clear_recipient_history,
    clear_all_history
)

METADATA_FILE = "schema_metadata.json"
DB_NAME       = "database.sqlite"
PIC_DIR       = Path("pictures")

st.set_page_config(page_title="Maily", page_icon="✉️", layout="wide")

# ==========================================
# REFACTORED CSS: True Dark Blue & White Theme
# ==========================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* 1. Force Global Dark Blue Background */
.stApp, .main, .block-container {
    background-color: #0b1120 !important; 
}

/* 2. Force All Text to White/Light Gray */
html, body, p, span, h1, h2, h3, h4, h5, h6, label, div { 
    font-family: 'Inter', sans-serif; 
    color: #f8fafc !important; 
}

#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none; }

/* 3. Input Fields & Text Areas (Making them readable) */
.stTextInput input, .stTextArea textarea, div[data-baseweb="select"] > div {
    background-color: #1e293b !important;
    color: #ffffff !important;
    border: 1px solid #3b82f6 !important;
    border-radius: 8px !important;
}

/* 4. Expander Boxes */
[data-testid="stExpander"] {
    background-color: #1e293b !important;
    border: 1px solid #334155 !important;
    border-radius: 8px !important;
}
[data-testid="stExpander"] p, [data-testid="stExpander"] span {
    color: #f8fafc !important;
}

/* 5. Buttons */
.stButton > button {
    background-color: #1e3a8a !important;
    border: 1px solid #60a5fa !important;
    color: #ffffff !important;
    border-radius: 8px !important;
    padding: 0.75rem 1rem !important;
    font-weight: 600 !important;
    box-shadow: 0 4px 10px rgba(59, 130, 246, 0.2) !important;
    transition: all 0.2s;
}
.stButton > button:hover {
    background-color: #2563eb !important;
    box-shadow: 0 4px 15px rgba(59, 130, 246, 0.5) !important;
    border-color: #93c5fd !important;
}

/* 6. Table Headers */
.col-hdr {
    font-size: 0.8rem;
    font-weight: 700;
    color: #94a3b8 !important;
    text-transform: uppercase;
    border-bottom: 2px solid #3b82f6;
    padding-bottom: 5px;
    margin-bottom: 10px;
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def img_b64(filename: str) -> str:
    p = PIC_DIR / filename
    if not p.exists():
        return ""
    mime = "image/png" if filename.endswith(".png") else "image/jpeg"
    with open(p, "rb") as f:
        return f"data:{mime};base64,{base64.b64encode(f.read()).decode()}"

def load_metadata() -> dict:
    with open(METADATA_FILE, "r") as f:
        return json.load(f)

def get_recipients(maily_table_name: str) -> list:
    conn = sqlite3.connect(DB_NAME)
    try:
        rows = conn.execute(f"SELECT id, name, email FROM [{maily_table_name}] ORDER BY name").fetchall()
        return [{"id": str(r[0]), "name": r[1], "email": r[2]} for r in rows]
    except Exception as e:
        st.error(f"Could not load {maily_table_name}: {e}")
        return []
    finally:
        conn.close()

def get_badge_colors(entity_type: str):
    """Deterministically assign a color palette based on the entity name."""
    colors = [
        ("rgba(59, 130, 246, 0.2)", "#93c5fd", "#3b82f6"), # Blue
        ("rgba(16, 185, 129, 0.2)", "#6ee7b7", "#10b981"), # Green
        ("rgba(168, 85, 247, 0.2)", "#d8b4fe", "#a855f7"), # Purple
        ("rgba(245, 158, 11, 0.2)", "#fcd34d", "#f59e0b"), # Amber
        ("rgba(236, 72, 153, 0.2)", "#f9a8d4", "#ec4899"), # Pink
    ]
    idx = sum(ord(c) for c in entity_type) % len(colors)
    return colors[idx]

def badge_html(entity_type: str) -> str:
    t = (entity_type or "other").title()
    bg, text, border = get_badge_colors(t)
    return f'<span style="display:inline-block; font-size:0.7rem; font-weight:700; padding:4px 10px; border-radius:12px; text-transform:uppercase; letter-spacing:0.05em; background:{bg}; color:{text}; border:1px solid {border};">{t}</span>'

def fmt_datetime(sent_at: str):
    if not sent_at:
        return "", ""
    parts = sent_at.strip().split(" ")
    date  = parts[0] if len(parts) > 0 else ""
    time  = parts[1][:5] if len(parts) > 1 else "" 
    return date, time

def reset_compose():
    st.session_state.compose_state      = None
    st.session_state.clarification_done = False
    st.session_state.draft_ready        = False
    st.session_state.email_sent         = False


# ── Session state ─────────────────────────────
if "metadata"           not in st.session_state: st.session_state.metadata           = load_metadata()
if "page"               not in st.session_state: st.session_state.page               = "home"
if "compose_state"      not in st.session_state: st.session_state.compose_state      = None
if "clarification_done" not in st.session_state: st.session_state.clarification_done = False
if "draft_ready"        not in st.session_state: st.session_state.draft_ready        = False
if "email_sent"         not in st.session_state: st.session_state.email_sent         = False
if "confirm_clear_all"  not in st.session_state: st.session_state.confirm_clear_all  = False
if "confirm_clear_one"  not in st.session_state: st.session_state.confirm_clear_one  = False
if "hist_open"          not in st.session_state: st.session_state.hist_open          = True

metadata    = st.session_state.metadata
maily       = metadata.get("maily", {})
description = metadata.get("db_description", "No description available.")


# ─────────────────────────────────────────────
# HOME PAGE
# ─────────────────────────────────────────────
def show_home():

    # ── STRETCHED HERO BANNER (Fixed Logo) ──
    logo_src = img_b64("AgentMaily.png")
    img_tag = f'<div style="background: white; text-align: center; padding: 1.5rem;"><img src="{logo_src}" style="max-height: 140px; width: auto; object-fit: contain;" /></div>' if logo_src else ''
    
    st.markdown(f"""
    <div style="border: 2px solid #3b82f6; border-radius: 12px; overflow: hidden; margin-bottom: 2rem; box-shadow: 0 0 20px rgba(59,130,246,0.3);">
        {img_tag}
        <div style="background: linear-gradient(180deg, #1e3a8a 0%, #0b1120 100%); padding: 1.5rem; text-align: center;">
            <h1 style="margin:0; font-size:2.5rem; text-shadow: 0 2px 4px rgba(0,0,0,0.8); color: white;">Hi, I'm Maily!</h1>
            <p style="margin: 0.5rem 0 0 0; color: #cbd5e1; font-size:1.1rem;">{description}</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="background: rgba(217, 119, 6, 0.15); border-left: 4px solid #f59e0b; padding: 1rem; border-radius: 4px; margin-bottom: 2rem;">
        <span style="color: #fcd34d;">⚠️ <strong>Developer Note:</strong> To update data, modify it from the backend and re-run <code>python maily.py</code></span>
    </div>
    """, unsafe_allow_html=True)

    # ── Section 1 Header ────────────────
    st.markdown("""
    <div style="background: #1e293b; padding: 1rem 1.5rem; border-left: 6px solid #3b82f6; border-radius: 6px; margin-bottom: 1.5rem;">
        <h2 style="margin:0; font-size: 1.5rem; color: white;">🚀 Send Email To</h2>
    </div>
    """, unsafe_allow_html=True)

    if not maily:
        st.warning("No email tables found. Run `python maily.py` first.")
    else:
        for table, info in maily.items():
            entity = info["entity_type"].title()
            if st.button(f"Connect with {entity}", use_container_width=True, key=f"btn_{entity}"):
                st.session_state.page = info["entity_type"]
                reset_compose()
                st.rerun()

    # ── Section 2 Header ─────────────────
    all_history = get_all_history()
    count       = len(all_history)

    st.markdown("""
    <div style="background: #1e293b; padding: 1rem 1.5rem; border-left: 6px solid #10b981; border-radius: 6px; margin-top: 3rem; margin-bottom: 1.5rem; display: flex; align-items: center;">
        <h2 style="margin:0; font-size: 1.5rem; color: white;">📤 Sent History <span style="font-size:1rem; color:#94a3b8; font-weight:normal;">(""" + str(count) + """)</span></h2>
    </div>
    """, unsafe_allow_html=True)

    col_btn1, col_btn2, _ = st.columns([1.5, 1.5, 7])
    with col_btn1:
        if all_history and not st.session_state.confirm_clear_all:
            if st.button("🗑️ Clear All", key="clear_all_btn", use_container_width=True):
                st.session_state.confirm_clear_all = True
                st.rerun()
    with col_btn2:
        lbl = "Collapse" if st.session_state.hist_open else "Expand"
        if st.button(lbl, key="hist_toggle", use_container_width=True):
            st.session_state.hist_open = not st.session_state.hist_open
            st.rerun()

    if st.session_state.confirm_clear_all:
        st.error("⚠️ Are you sure you want to permanently delete ALL history?")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Yes, clear it all", use_container_width=True, key="confirm_clear"):
                clear_all_history()
                st.session_state.confirm_clear_all = False
                st.rerun()
        with c2:
            if st.button("❌ Cancel", use_container_width=True, key="cancel_clear"):
                st.session_state.confirm_clear_all = False
                st.rerun()

    if not all_history:
        st.caption("No emails sent yet. Select an entity above to get started!")
        return

    if not st.session_state.hist_open:
        return

    st.markdown("<div style='margin-bottom:1rem;'></div>", unsafe_allow_html=True)

    # ── DYNAMIC Per-column filters ────────────────────
    unique_types = sorted(list(set(h["entity_type"].title() for h in all_history if h.get("entity_type"))))
    type_options = ["All"] + unique_types

    fc1, fc2, fc3, fc4, fc5 = st.columns([2, 2.2, 1.5, 1.3, 2.5])
    with fc1: f_name    = st.text_input("n", key="f_name",    label_visibility="collapsed", placeholder="Filter Name...")
    with fc2: f_email   = st.text_input("e", key="f_email",   label_visibility="collapsed", placeholder="Filter Email...")
    with fc3: f_type    = st.selectbox("t", type_options, key="f_type", label_visibility="collapsed")
    with fc4: f_date    = st.text_input("d", key="f_date",    label_visibility="collapsed", placeholder="Filter Date...")
    with fc5: f_subject = st.text_input("s", key="f_subject", label_visibility="collapsed", placeholder="Filter Subject...")

    filtered = all_history
    if f_name.strip():    filtered = [h for h in filtered if f_name.strip().lower()    in (h["recipient_name"]  or "").lower()]
    if f_email.strip():   filtered = [h for h in filtered if f_email.strip().lower()   in (h["recipient_email"] or "").lower()]
    if f_type != "All":   filtered = [h for h in filtered if f_type.lower()            in (h["entity_type"]     or "").lower()]
    if f_date.strip():    filtered = [h for h in filtered if f_date.strip()            in (h["sent_at"]         or "")]
    if f_subject.strip(): filtered = [h for h in filtered if f_subject.strip().lower() in (h["subject"]         or "").lower()]

    st.markdown(f"<p style='font-size:0.85rem; color:#94a3b8; margin-bottom: 1rem;'>Showing {len(filtered)} of {count} entries</p>", unsafe_allow_html=True)

    if not filtered:
        st.info("No results match your filters.")
        return

    h1, h2, h3, h4, h5 = st.columns([2, 2.2, 1.5, 1.3, 2.5])
    with h1: st.markdown('<div class="col-hdr">Recipient</div>',   unsafe_allow_html=True)
    with h2: st.markdown('<div class="col-hdr">Email Address</div>', unsafe_allow_html=True)
    with h3: st.markdown('<div class="col-hdr">Entity</div>',      unsafe_allow_html=True)
    with h4: st.markdown('<div class="col-hdr">Date & Time</div>', unsafe_allow_html=True)
    with h5: st.markdown('<div class="col-hdr">Email Subject</div>', unsafe_allow_html=True)

    for h in filtered:
        date_str, time_str = fmt_datetime(h["sent_at"])

        with st.container():
            c1, c2, c3, c4, c5 = st.columns([2, 2.2, 1.5, 1.3, 2.5])
            with c1: st.markdown(f'<div style="font-weight: 600;">{h["recipient_name"] or ""}</div>', unsafe_allow_html=True)
            with c2: st.markdown(f'<div style="color: #94a3b8;">{h["recipient_email"] or ""}</div>', unsafe_allow_html=True)
            with c3: st.markdown(badge_html(h["entity_type"] or "other"), unsafe_allow_html=True)
            with c4: st.markdown(f'<div>{date_str}<br><span style="font-size:0.8rem; color:#94a3b8;">{time_str}</span></div>', unsafe_allow_html=True)
            with c5: st.markdown(f'<div>{h["subject"] or ""}</div>', unsafe_allow_html=True)

            with st.expander("📄 Read Full Email"):
                st.markdown(f"**To:** {h['recipient_name']}  ·  `{h['recipient_email']}`")
                st.markdown(f"**Subject:** {h['subject']}")
                st.divider()
                st.text(h["body"] or "")
            
            st.markdown('<hr style="border-color: #1e293b; margin: 0.5rem 0 1rem 0;">', unsafe_allow_html=True)


# ─────────────────────────────────────────────
# ENTITY PAGE
# ─────────────────────────────────────────────
def show_entity_page(entity_type: str):
    maily_table = next((t for t, info in maily.items() if info["entity_type"] == entity_type), None)
    
    if not maily_table:
        st.error(f"No table found for: {entity_type}")
        return

    if st.button("⬅️ Back to Home"):
        st.session_state.page = "home"
        reset_compose()
        st.session_state.confirm_clear_one = False
        st.rerun()

    st.markdown(f"""
    <div style="background: #1e293b; padding: 1rem 1.5rem; border-left: 6px solid #3b82f6; border-radius: 6px; margin-top: 1.5rem; margin-bottom: 1.5rem;">
        <h2 style="margin:0; font-size: 1.5rem; color: white;">📫 Compose to {entity_type.title()}</h2>
    </div>
    """, unsafe_allow_html=True)

    recipients = get_recipients(maily_table)
    if not recipients:
        st.warning(f"No {entity_type}s found.")
        return

    options        = {f"{r['name']} ({r['email']})": r for r in recipients}
    selected_label = st.selectbox(f"Choose a {entity_type.title()}:", list(options.keys()))
    selected       = options[selected_label]
    
    st.markdown(f"<div style='background:#1e293b; padding:1rem; border-radius:8px;'><strong>Selected:</strong> <span style='color:#60a5fa;'>{selected['name']}</span> &nbsp;|&nbsp; 📧 <code>{selected['email']}</code></div>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    compose_col, history_col = st.columns([2, 1], gap="large")

    with history_col:
        history = get_email_history(selected["id"])

        st.markdown(f"### 📜 History <span style='font-size:0.9rem; font-weight:normal; color:#94a3b8;'>({len(history)})</span>", unsafe_allow_html=True)

        if not history:
            st.info("No emails sent to this person yet.")
        else:
            if not st.session_state.confirm_clear_one:
                if st.button("🗑️ Clear recipient history", key="clear_one_btn", use_container_width=True):
                    st.session_state.confirm_clear_one = True
                    st.rerun()
            else:
                st.warning("Delete this history?")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("✅ Yes", use_container_width=True, key="confirm_one"):
                        clear_recipient_history(selected["id"])
                        st.session_state.confirm_clear_one = False
                        st.rerun()
                with c2:
                    if st.button("❌ No", use_container_width=True, key="cancel_one"):
                        st.session_state.confirm_clear_one = False
                        st.rerun()

            for h in history:
                date_str, time_str = fmt_datetime(h["sent_at"])
                subj_display = (h["subject"] or "")[:38] + ("…" if len(h["subject"] or "") > 38 else "")
                with st.expander(f"🕰️ {date_str}  ·  {subj_display}"):
                    st.markdown(f"**Subject:** {h['subject']}")
                    st.text(h["body"])

    with compose_col:
        cs = st.session_state.compose_state

        if cs and cs.get("history_summary"):
            st.info("🧠 **Context Memory:** " + cs["history_summary"])

        if not st.session_state.draft_ready and not (cs and cs.get("needs_clarification") and not st.session_state.clarification_done):
            st.markdown("### 📝 Instructions for Agent")
            user_prompt = st.text_area(
                "What do you want to say?",
                placeholder="e.g. tell them their invoice is overdue, ask about delivery status...",
                height=150,
                key="user_prompt_input"
            )
            if st.button("✨ Generate Draft", use_container_width=True, type="primary"):
                if not user_prompt.strip():
                    st.warning("Please enter what you want to say first.")
                else:
                    with st.spinner("Maily is thinking..."):
                        app    = build_email_graph()
                        result = app.invoke({
                            "base_tables": {}, "email_tables": [], "pending_tables": [],
                            "created_tables": [], "maily_info": {}, "db_description": None,
                            "recipient_id"          : selected["id"],
                            "recipient_name"        : selected["name"],
                            "recipient_email"       : selected["email"],
                            "entity_type"           : entity_type,
                            "user_prompt"           : user_prompt,
                            "needs_clarification"   : None,
                            "clarification_question": None,
                            "clarification_answer"  : None,
                            "email_subject"         : None,
                            "email_body"            : None,
                            "finalized"             : None,
                            "attachments"           : None,
                            "history_summary"       : None,
                            "email_sent"            : None,
                            "error"                 : None
                        })
                        st.session_state.compose_state      = result
                        st.session_state.clarification_done = False
                        st.session_state.draft_ready        = bool(result.get("email_body"))
                        st.rerun()

        elif cs and cs.get("needs_clarification") and not st.session_state.clarification_done:
            st.markdown("### 🤔 Maily Needs Details")
            st.warning(f"**Question:** {cs['clarification_question']}")
            answer = st.text_input("Your answer:", key="clarification_input",
                                   placeholder="Type your answer, or leave blank to skip")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Submit Details", use_container_width=True, type="primary"):
                    with st.spinner("Drafting..."):
                        app    = build_email_graph()
                        result = app.invoke({**cs, "clarification_answer": answer.strip() if answer.strip() else "skip"})
                        st.session_state.compose_state      = result
                        st.session_state.clarification_done = True
                        st.session_state.draft_ready        = True
                        st.rerun()
            with col2:
                if st.button("⏭️ Skip & Draft Anyway", use_container_width=True):
                    with st.spinner("Drafting..."):
                        app    = build_email_graph()
                        result = app.invoke({**cs, "clarification_answer": "skip"})
                        st.session_state.compose_state      = result
                        st.session_state.clarification_done = True
                        st.session_state.draft_ready        = True
                        st.rerun()

        elif st.session_state.draft_ready and cs and cs.get("email_body"):
            if st.session_state.email_sent:
                st.success(f"✅ Securely sent to **{selected['name']}** ({selected['email']})!")
                if st.button("✉️ Draft Another Email", use_container_width=True):
                    reset_compose()
                    st.rerun()
                return

            st.markdown("### 📨 Review Your Draft")
            subject = st.text_input("Subject:", value=cs.get("email_subject", ""), key="subject_edit")
            body    = st.text_area("Body:", value=cs.get("email_body", ""), height=350, key="body_edit")
            
            # ---------------------------------------------------------
            # Add File Uploader
            # ---------------------------------------------------------
            uploaded_files = st.file_uploader("📎 Attach files (optional)", accept_multiple_files=True)
            
            attachments_data = []
            if uploaded_files:
                for f in uploaded_files:
                    attachments_data.append({"filename": f.name, "data": f.read()})
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📤 Approve & Send", use_container_width=True, type="primary"):
                    with st.spinner(f"Sending to {selected['email']}..."):
                        try:
                            app    = build_send_graph()
                            # 👇 THIS IS WHERE THE MAGIC HAPPENS: We pass attachments_data inside the dictionary!
                            result = app.invoke({
                                **cs, 
                                "email_subject": subject, 
                                "email_body": body, 
                                "attachments": attachments_data, 
                                "email_sent": None
                            })
                            st.session_state.compose_state = result
                            st.session_state.email_sent    = True
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to send: {e}")
            with col2:
                if st.button("🔄 Discard & Restart", use_container_width=True):
                    reset_compose()
                    st.rerun()

if st.session_state.page == "home":
    show_home()
else:
    show_entity_page(st.session_state.page)