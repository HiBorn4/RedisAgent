"""
RedisAgent UI — Portfolio-ready Streamlit frontend
Connects to the FastAPI backend via /chat and /health endpoints.
"""

import streamlit as st
import requests
import os
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
#  Page Config  (must be first Streamlit call)
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="RedisAgent · AI Data Manager",
    page_icon="🔴",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
#  Custom CSS — dark, modern, portfolio-grade
# ─────────────────────────────────────────────
st.markdown("""
<style>
/* ── Base ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f0f23 0%, #1a1a2e 60%, #16213e 100%);
    border-right: 1px solid #e11d48;
}
section[data-testid="stSidebar"] * { color: #e2e8f0 !important; }
section[data-testid="stSidebar"] .stMarkdown h1,
section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3 { color: #f8fafc !important; }

/* ── Main background ── */
.main .block-container {
    background: #0a0a1a;
    padding-top: 1.5rem;
    max-width: 1100px;
}
.stApp { background: #0a0a1a; }

/* ── Hero header ── */
.hero-header {
    background: linear-gradient(135deg, #1a0a2e 0%, #0f172a 40%, #0a1628 100%);
    border: 1px solid rgba(225, 29, 72, 0.3);
    border-radius: 16px;
    padding: 2rem 2.5rem;
    margin-bottom: 1.5rem;
    position: relative;
    overflow: hidden;
}
.hero-header::before {
    content: '';
    position: absolute;
    top: -50%;
    right: -10%;
    width: 400px;
    height: 400px;
    background: radial-gradient(circle, rgba(225,29,72,0.08) 0%, transparent 70%);
    pointer-events: none;
}
.hero-title {
    font-size: 2rem;
    font-weight: 700;
    background: linear-gradient(135deg, #f8fafc 0%, #e11d48 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 0;
    line-height: 1.2;
}
.hero-subtitle {
    color: #94a3b8;
    font-size: 0.95rem;
    margin-top: 0.5rem;
    font-weight: 400;
}
.hero-badges { margin-top: 1rem; display: flex; gap: 0.5rem; flex-wrap: wrap; }
.badge {
    background: rgba(225, 29, 72, 0.15);
    border: 1px solid rgba(225, 29, 72, 0.35);
    color: #fda4af;
    padding: 0.2rem 0.7rem;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}

/* ── Chat container ── */
.chat-container {
    background: #0f0f23;
    border: 1px solid #1e293b;
    border-radius: 12px;
    padding: 1.2rem;
    min-height: 420px;
    max-height: 520px;
    overflow-y: auto;
    margin-bottom: 1rem;
    scroll-behavior: smooth;
}

/* ── Chat bubbles ── */
.bubble-user {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 1rem;
}
.bubble-user .bubble-inner {
    background: linear-gradient(135deg, #e11d48, #be123c);
    color: #fff;
    border-radius: 16px 16px 4px 16px;
    padding: 0.75rem 1.1rem;
    max-width: 72%;
    font-size: 0.9rem;
    line-height: 1.5;
    box-shadow: 0 4px 15px rgba(225,29,72,0.25);
}
.bubble-assistant {
    display: flex;
    justify-content: flex-start;
    margin-bottom: 1rem;
    align-items: flex-start;
    gap: 0.6rem;
}
.bubble-avatar {
    width: 32px; height: 32px;
    background: linear-gradient(135deg, #7c3aed, #4f46e5);
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.85rem;
    flex-shrink: 0;
    margin-top: 2px;
}
.bubble-assistant .bubble-inner {
    background: #1e293b;
    color: #e2e8f0;
    border-radius: 4px 16px 16px 16px;
    padding: 0.75rem 1.1rem;
    max-width: 72%;
    font-size: 0.9rem;
    line-height: 1.55;
    border: 1px solid #334155;
}
.bubble-meta {
    font-size: 0.7rem;
    color: #475569;
    margin-top: 0.3rem;
    padding-left: 0.2rem;
}

/* ── Input area ── */
.stTextArea textarea {
    background: #0f172a !important;
    border: 1px solid #334155 !important;
    border-radius: 10px !important;
    color: #e2e8f0 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.9rem !important;
    resize: none !important;
}
.stTextArea textarea:focus {
    border-color: #e11d48 !important;
    box-shadow: 0 0 0 2px rgba(225,29,72,0.2) !important;
}

/* ── Buttons ── */
.stButton > button {
    background: linear-gradient(135deg, #e11d48, #9f1239);
    color: white;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    font-size: 0.9rem;
    padding: 0.5rem 1.5rem;
    transition: all 0.2s ease;
    width: 100%;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #f43f5e, #e11d48);
    box-shadow: 0 4px 20px rgba(225,29,72,0.4);
    transform: translateY(-1px);
}

/* ── Status pill ── */
.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    background: rgba(16, 185, 129, 0.12);
    border: 1px solid rgba(16, 185, 129, 0.3);
    color: #34d399;
    border-radius: 999px;
    padding: 0.25rem 0.75rem;
    font-size: 0.75rem;
    font-weight: 600;
}
.status-pill.offline {
    background: rgba(239, 68, 68, 0.12);
    border-color: rgba(239, 68, 68, 0.3);
    color: #f87171;
}
.status-dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    background: currentColor;
    animation: pulse 2s infinite;
}
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
}

/* ── Metrics ── */
.metric-card {
    background: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 10px;
    padding: 1rem;
    text-align: center;
}
.metric-value {
    font-size: 1.5rem;
    font-weight: 700;
    color: #f8fafc;
    font-family: 'JetBrains Mono', monospace;
}
.metric-label {
    font-size: 0.72rem;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-top: 0.2rem;
}

/* ── Sample queries ── */
.sample-query {
    background: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 0.6rem 0.9rem;
    font-size: 0.82rem;
    color: #94a3b8;
    cursor: pointer;
    transition: all 0.2s;
    margin-bottom: 0.4rem;
}
.sample-query:hover {
    border-color: #e11d48;
    color: #fda4af;
    background: rgba(225,29,72,0.05);
}

/* ── Code blocks inside chat ── */
.bubble-inner pre, .bubble-inner code {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    background: rgba(0,0,0,0.3);
    border-radius: 6px;
    padding: 0.2rem 0.4rem;
}

/* Scrollbar */
.chat-container::-webkit-scrollbar { width: 4px; }
.chat-container::-webkit-scrollbar-track { background: transparent; }
.chat-container::-webkit-scrollbar-thumb { background: #334155; border-radius: 2px; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  Session State
# ─────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "total_queries" not in st.session_state:
    st.session_state.total_queries = 0
if "session_id" not in st.session_state:
    st.session_state.session_id = None

BACKEND = os.getenv("BACKEND_URL", "http://localhost:8001")

# ─────────────────────────────────────────────
#  Sidebar
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🔴 RedisAgent")
    st.markdown("*AI-powered Redis data manager*")
    st.divider()

    # Backend health check
    backend_url = st.text_input("Backend URL", value=BACKEND, key="backend_url_input")
    BACKEND = backend_url

    health_status = {"status": "unknown", "adk": False, "mcp_ready": False}
    is_online = False
    try:
        r = requests.get(f"{BACKEND}/health", timeout=3)
        if r.ok:
            health_status = r.json()
            is_online = True
    except Exception:
        pass

    pill_class = "status-pill" if is_online else "status-pill offline"
    status_text = "Backend Online" if is_online else "Backend Offline"
    st.markdown(
        f'<div class="{pill_class}"><span class="status-dot"></span>{status_text}</div>',
        unsafe_allow_html=True,
    )

    st.markdown("")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            f'<div class="metric-card"><div class="metric-value">{"✓" if health_status.get("adk") else "✗"}</div><div class="metric-label">ADK Agent</div></div>',
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f'<div class="metric-card"><div class="metric-value">{"✓" if health_status.get("mcp_ready") else "✗"}</div><div class="metric-label">MCP Redis</div></div>',
            unsafe_allow_html=True,
        )

    st.divider()
    st.markdown("#### 💡 Sample Queries")
    samples = [
        "List all available Redis keys",
        "What is the trip status for the current session?",
        "Fetch the travel data and summarize it",
        "Ping Redis and confirm connection",
        "Search for keys matching travel_data_*",
    ]
    for s in samples:
        if st.button(s, key=f"sample_{s[:20]}", use_container_width=True):
            st.session_state["prefill"] = s

    st.divider()
    st.markdown("#### 📊 Session Stats")
    st.markdown(
        f'<div class="metric-card"><div class="metric-value">{st.session_state.total_queries}</div><div class="metric-label">Total Queries</div></div>',
        unsafe_allow_html=True,
    )
    if st.session_state.session_id:
        st.caption(f"Session: `{st.session_state.session_id}`")

    st.divider()
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.markdown("---")
    st.markdown(
        '<div style="text-align:center;color:#334155;font-size:0.72rem;">Built with Google ADK · FastAPI · Redis MCP · Streamlit</div>',
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────
#  Hero Header
# ─────────────────────────────────────────────
st.markdown("""
<div class="hero-header">
  <p class="hero-title">🔴 RedisAgent</p>
  <p class="hero-subtitle">Conversational AI agent that reads, queries, and reasons over your Redis data in real time.</p>
  <div class="hero-badges">
    <span class="badge">Google ADK</span>
    <span class="badge">MCP Protocol</span>
    <span class="badge">Redis</span>
    <span class="badge">FastAPI</span>
    <span class="badge">Gemini 2.5 Pro</span>
  </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  Chat Display
# ─────────────────────────────────────────────
def render_messages():
    if not st.session_state.messages:
        st.markdown("""
        <div style="text-align:center;padding:3rem 2rem;color:#334155;">
            <div style="font-size:3rem;margin-bottom:1rem;">🔴</div>
            <div style="font-size:1.1rem;font-weight:600;color:#475569;margin-bottom:0.5rem;">Ready to query Redis</div>
            <div style="font-size:0.85rem;color:#334155;">Ask anything about your Redis data — the agent will discover keys, fetch values, and reason over JSON structures automatically.</div>
        </div>
        """, unsafe_allow_html=True)
        return

    bubbles_html = ""
    for msg in st.session_state.messages:
        ts = msg.get("ts", "")
        if msg["role"] == "user":
            bubbles_html += f"""
            <div class="bubble-user">
              <div>
                <div class="bubble-inner">{msg['text']}</div>
                <div class="bubble-meta" style="text-align:right">{ts}</div>
              </div>
            </div>"""
        else:
            bubbles_html += f"""
            <div class="bubble-assistant">
              <div class="bubble-avatar">🤖</div>
              <div>
                <div class="bubble-inner">{msg['text']}</div>
                <div class="bubble-meta">{ts}</div>
              </div>
            </div>"""

    st.markdown(f'<div class="chat-container">{bubbles_html}</div>', unsafe_allow_html=True)

render_messages()

# ─────────────────────────────────────────────
#  Input
# ─────────────────────────────────────────────
prefill = st.session_state.pop("prefill", "")

col_input, col_btn = st.columns([5, 1])
with col_input:
    user_input = st.text_area(
        "Message",
        value=prefill,
        placeholder="Ask about your Redis data… e.g. 'List all keys' or 'What is the trip status?'",
        height=80,
        label_visibility="collapsed",
        key="user_input_area",
    )
with col_btn:
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    send = st.button("Send ➤", use_container_width=True)

# ─────────────────────────────────────────────
#  Send Logic
# ─────────────────────────────────────────────
if send:
    text = user_input.strip()
    if not text:
        st.warning("Please type a message before sending.")
        st.stop()

    ts_now = datetime.now().strftime("%H:%M")
    st.session_state.messages.append({"role": "user", "text": text, "ts": ts_now})
    st.session_state.total_queries += 1

    with st.spinner("🤖 Agent is querying Redis…"):
        try:
            resp = requests.post(
                f"{BACKEND}/chat",
                json={"query": text},
                timeout=120,
            )
            if resp.ok:
                data = resp.json()
                agent_text = data.get("response", "(no response)")
                st.session_state.session_id = data.get("session_id", st.session_state.session_id)
                st.session_state.messages.append({"role": "assistant", "text": agent_text, "ts": datetime.now().strftime("%H:%M")})
            else:
                st.session_state.messages.append({
                    "role": "assistant",
                    "text": f"⚠️ Backend error `{resp.status_code}`: {resp.text[:200]}",
                    "ts": datetime.now().strftime("%H:%M"),
                })
        except requests.exceptions.ConnectionError:
            st.session_state.messages.append({
                "role": "assistant",
                "text": "⚠️ Cannot reach backend. Make sure `uvicorn main:app --port 8001` is running.",
                "ts": datetime.now().strftime("%H:%M"),
            })
        except Exception as e:
            st.session_state.messages.append({
                "role": "assistant",
                "text": f"⚠️ Error: {str(e)}",
                "ts": datetime.now().strftime("%H:%M"),
            })

    st.rerun()
