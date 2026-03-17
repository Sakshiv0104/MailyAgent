# ✉️ Maily: Autonomous CRM & Context-Aware Communications Agent

![Maily UI Preview](./pictures/AgentMaily.png)

Maily is an autonomous, graph-based AI agent designed to act as an intelligent communications layer over any relational database. Point Maily at a raw folder of CSVs, and she automatically builds a relational SQLite database, identifies human entities (Customers, Suppliers, Employees), maps their contact information, and provides a contextual, Human-in-the-Loop interface for drafting and sending emails.

Built with **LangGraph**, **Streamlit**, and the ultra-low latency **Cerebras LLM**, Maily doesn't just generate text, she understands database relationships, recalls past email history, and knows exactly when to pause and ask the user for clarification.

## ✨ The Maily Experience (Key Features)

I designed Maily to require the absolute minimum amount of human effort while providing maximum control. Here is exactly what happens when you launch the app:

* **1. Dynamic Dashboard:** When you open Maily, she has already scanned your database. The home screen automatically generates buttons *only* for categories that have email addresses (e.g., "Connect with Supplier", "Connect with Customer").
* **2. Instant Context & History:** When you select a person, Maily pulls up your entire past email history with them on the side of the screen. You never have to guess what was said last time.
* **3. "Lazy" Prompting:** You don't need to write a whole email. Just type a tiny prompt like *"ask about the invoice"* or *"tell them the delivery is late"*.
* **4. Smart Clarification (Human-in-the-Loop):** If your prompt is too vague, Maily won't guess. She will stop and ask you: *"Wait, which invoice number?"* You just type the answer, and she resumes drafting.
* **5. Total Editing Control:** Once Maily generates the professional draft, you aren't forced to send it. You can edit the text, change the subject line, or click **Discard & Restart** to completely rewrite it.
* **6. Attachments & Branding:** Before hitting send, you can easily upload files. Maily's complex backend handles the MIME encoding, attaching your files while perfectly sandwiching an inline AgentMaily logo and signature into the HTML body.
---

## The Problem Maily Solves
Standard AI email writers are essentially blind LLM wrappers. They:
1. **Lack Historical Context:** They don't know what you emailed the client last week.
2. **Hallucinate Details:** If you say *"Follow up on the invoice"*, they will invent a fake invoice number.
3. **Are Disconnected from Data:** They require manual copy-pasting of recipient emails and names.

**Maily solves this.** She acts as an intelligent CRM that reads your past outbox, dynamically fetches recipient data from your database, and executes complex SMTP payloads with attachments.

---

## ⚙️ Core Engineering Features

### 1. Human-in-the-Loop "Clarification" Architecture
Maily is engineered with a strict guardrail system using LangGraph conditional edges. 
* When a user submits a prompt (e.g., *"Ask them about the delivery status"*), the `node_analyze_prompt` state machine evaluates the request for ambiguity.
* If the request is vague, **Maily halts execution** and prompts the user: *"Which specific order or product are you referring to?"* * Execution only resumes once the human provides the missing context, mathematically eliminating hallucinated business data.

### 2. Autonomous Relational Schema Discovery
Maily acts as her own DBA upon initialization. By analyzing raw CSV data, she:
* Automatically detects **Primary Keys** and calculates **Foreign Keys** based on data-overlap thresholds (>70%).
* Uses LLM classification to categorize tables into business entities (`Supplier`, `Customer`, `Partner`).
* Builds smart, pre-joined SQL views (`master_views`) to optimize future data retrieval.
* Generates a structural ER Diagram (`schema_diagram.png`) using `networkx`.

### 3. Temporal Context Memory
To prevent repetitive or conflicting emails, Maily maintains a local SQLite history of all sent communications. 
* Before drafting a new email, the `node_summarize_history` function pulls the recipient's past 10 emails.
* It compresses this history into a strict 1-2 sentence summary.
* This micro-state is injected into the drafting prompt, ensuring Maily writes with complete awareness of previous interactions.

### 4. Advanced SMTP & MIME Execution
Sending raw text from an LLM is easy; sending professional business emails is hard. Maily utilizes a sophisticated `MIMEMultipart` engine that programmatically constructs:
* **Alternative Payloads:** Seamless fallback between Plain Text and HTML.
* **Inline CID Images:** Programmatically sandwiches an inline AgentMaily logo between the dynamically generated text and the signature block.
* **Octet-Stream Attachments:** Safely encodes base64 user-uploaded files directly into the execution graph.

---

## 🏗 System Architecture (LangGraph)
Maily's "brain" is divided into three distinct state machines to optimize token usage and separate concerns:

1. **Setup Graph:** Scans the database, maps the schema, and categorizes email entities.
2. **Compose Graph:** Handles the Human-in-the-Loop logic (History Extraction ➔ Prompt Analysis ➔ Clarification Halt ➔ Draft Generation).
3. **Execution Graph:** Packages the final state (subject, HTML body, attachments) and triggers the SMTP protocol.

---

## 🛠 Technology & Model Stack

| Technology | Implementation Details |
| :--- | :--- |
| **Cerebras Cloud SDK** | **The Inference Engine:** Chosen for its industry-leading Time-to-First-Token (TTFT). Maily's real-time clarification loops require sub-second latency to feel like a responsive UI. |
| **LangGraph** | **The Orchestrator:** Manages the cyclic, stateful logic, conditional routing, and Human-in-the-Loop pauses. |
| **Streamlit** | **The Interface:** A custom-styled, dark-theme frontend that acts as the user's CRM dashboard and inbox. |
| **SQLite3** | **The Storage Layer:** Handles both the ingested business data and the persistent email history logs. |
| **smtplib / email.mime** | **The Execution Layer:** Manages secure TLS connections and complex multipart payload construction. |

---

##  Getting Started

### Prerequisites
* Python 3.10+
* Cerebras API Key
* App Password for your Email Provider (e.g., Gmail App Passwords)

### Installation

1. **Clone the repository**
   ```bash
   git clone [https://github.com/YOUR_USERNAME/Maily.git](https://github.com/YOUR_USERNAME/Maily.git)
   cd Maily
