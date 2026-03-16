import subprocess
import sys
from langgraph.graph import StateGraph, END

from components.state import MailyState
from components.nodes import (
    node_detect,
    node_process,
    node_generate_description,
    node_save,
    route_after_process,
    node_summarize_history,
    node_analyze_prompt,
    node_draft_email,
    node_send_email,
    route_after_analyze
)
from components.tools import load_metadata


# ─────────────────────────────────────────────
# GRAPH 1 — Setup Graph
# ─────────────────────────────────────────────
def build_setup_graph():
    graph = StateGraph(MailyState)

    graph.add_node("detect",   node_detect)
    graph.add_node("process",  node_process)
    graph.add_node("describe", node_generate_description)
    graph.add_node("save",     node_save)

    graph.set_entry_point("detect")
    graph.add_edge("detect", "process")
    graph.add_conditional_edges(
        "process",
        route_after_process,
        {"loop": "process", "done": "describe"}
    )
    graph.add_edge("describe", "save")
    graph.add_edge("save", END)

    return graph.compile()


# ─────────────────────────────────────────────
# GRAPH 2 — Email Compose Graph
# history → analyze → (clarification?) → draft
# ─────────────────────────────────────────────
def build_email_graph():
    graph = StateGraph(MailyState)

    graph.add_node("history", node_summarize_history)
    graph.add_node("analyze", node_analyze_prompt)
    graph.add_node("draft",   node_draft_email)

    graph.set_entry_point("history")
    graph.add_edge("history", "analyze")
    graph.add_conditional_edges(
        "analyze",
        route_after_analyze,
        {
            "ask_user": END,
            "draft"   : "draft"
        }
    )
    graph.add_edge("draft", END)

    return graph.compile()


# ─────────────────────────────────────────────
# GRAPH 3 — Send Graph
# ─────────────────────────────────────────────
def build_send_graph():
    graph = StateGraph(MailyState)

    graph.add_node("send", node_send_email)

    graph.set_entry_point("send")
    graph.add_edge("send", END)

    return graph.compile()


# ─────────────────────────────────────────────
# Run setup graph + launch UI
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("  MAILY AGENT — Starting")
    print("=" * 50)

    metadata = load_metadata()
    app      = build_setup_graph()

    result = app.invoke({
        "base_tables"          : metadata.get("base_tables", {}),
        "email_tables"         : [],
        "pending_tables"       : [],
        "created_tables"       : [],
        "maily_info"           : {},
        "db_description"       : None,
        "recipient_id"         : None,
        "recipient_name"       : None,
        "recipient_email"      : None,
        "entity_type"          : None,
        "user_prompt"          : None,
        "needs_clarification"  : None,
        "clarification_question": None,
        "clarification_answer" : None,
        "email_subject"        : None,
        "email_body"           : None,
        "finalized"            : None,
        "attachments"          : None,
        "history_summary"      : None,
        "email_sent"           : None,
        "error"                : None
    })

    print("\n" + "=" * 50)
    print("  MAILY AGENT — Done!")
    print(f"  Tables created : {result['created_tables']}")
    print(f"  Description    : {result['db_description'][:80]}...")
    print("=" * 50)

    print("\n  Launching Maily UI...")
    subprocess.run([
        sys.executable, "-m", "streamlit", "run", "ui.py",
        "--server.headless", "false",
        "--browser.gatherUsageStats", "false"
    ])