#!/usr/bin/env python3
"""
main.py – Minimal FastAPI + Google ADK + Redis MCP
Now with persistent ADK session storage and reloading.
"""
import asyncio
import contextlib
import json
import logging
import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, Body, HTTPException
from pydantic import BaseModel

# ---------- Google ADK imports ----------
try:
    from google.adk.agents import LlmAgent
    from google.adk.runners import Runner, RunConfig
    from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioConnectionParams
    from google.adk.sessions import DatabaseSessionService
    from google.genai import types
    from google.adk.models.lite_llm import LiteLlm
    ADK_AVAILABLE = True
except Exception:
    ADK_AVAILABLE = False

# ---------- MCP stdio imports ----------
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.session import ClientSession

# ---------- Setup ----------
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("minimal_adk")

app = FastAPI(title="minimal-adk-mcp")

# Config
MCP_SERVER_CMD = os.getenv("MCP_SERVER_CMD", "python3")
MCP_SERVER_ARGS = os.getenv("MCP_SERVER_ARGS", "server.py").split()
DB_URL = "sqlite:///./adk_sessions.db"
SESSION_FILE = Path("adk_session.json")
FLOW_MD = """
You are Mahindra’s internal travel-help AI.  
Your ONLY source of truth is the Redis instance exposed by the MCP “Redis Knowledge Access Tool”.

HOW TO WORK  
1.  **Never guess** – if you don’t see the data, it isn’t there.  
2.  **Always start** with `list_keys_tool()` to discover what is available.  
3.  **Pattern-search** next: the first three segments of every key are identical  
    (`travel_data_25017514_1c0814f0-741f-4f9f-84e2-3f6598eb13f6_`) – only the **suffix** changes.  
    Use `search_keys_tool(pattern="travel_data_25017514_1c0814f0-741f-4f9f-84e2-3f6598eb13f6_*")` to list all variants.  
4.  **Fetch** every matching key with `get_key_tool(key=…)` until you find the **exact** field the user asked for.  
5.  If the value is a JSON string, **parse it** and continue drilling **inside** that document.  
6.  If after exhaustive search the key/field is missing, reply:  
   “I could not locate that information in the current Redis dump.”

THINKING FORMAT (private)  
Thought: I need the status of trip 2200118440.  
Action: list_keys_tool() → 3 keys found.  
Action: search_keys_tool(pattern="travel_data_25017514_1c0814f0-741f-4f9f-84e2-3f6598eb13f6_*") → 3 suffixes.  
Action: get_key_tool(key="travel_data_25017514_1c0814f0-741f-4f9f-84e2-3f6598eb13f6_session_state.json") → JSON inside.  
Action: parse JSON, extract “trip_status” field.  
Answer: Trip 2200118440 is currently “APPROVED”.

Return only the final answer to the user – no JSON, no internal tool names.
"""

# Runtime state
app.state.mcp_client = None
app.state.runner = None
app.state.db_session_service = None
app.state.context = {}
app.state.session_id = None

# ---------- MCP CLIENT ----------
async def start_mcp_client():
    params = StdioServerParameters(command=MCP_SERVER_CMD, args=MCP_SERVER_ARGS)
    async with stdio_client(params) as (read, write):
        client = ClientSession(read, write)
        async with client:
            await client.initialize()
            app.state.mcp_client = client
            logger.info("[MCP] Client initialized and active")
            await asyncio.Event().wait()  # keep alive

# ---------- ADK SETUP ----------
async def init_adk_runner():
    """Initialize Google ADK runner with persistent session handling."""
    if not ADK_AVAILABLE:
        logger.warning("google.adk not installed — running in fallback mode.")
        return None

    # 1️⃣ Init DB session service
    session_service = DatabaseSessionService(db_url=DB_URL)
    app.state.db_session_service = session_service

    # 2️⃣ Connect ADK toolset (Redis MCP)
    toolset = MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(command=MCP_SERVER_CMD, args=MCP_SERVER_ARGS),
            timeout=3000,
        )
    )

    # 3️⃣ LLM agent
    agent = LlmAgent(
        model="gemini-2.5-pro",
        name="minimal_agent",
        instruction=FLOW_MD,
        tools=[toolset],
    )

    # 4️⃣ Runner
    runner = Runner(
        app_name="travel_bot",
        agent=agent,
        session_service=session_service,
    )
    app.state.runner = runner

    # 5️⃣ Create or reload persistent session
    if SESSION_FILE.exists():
        data = json.loads(SESSION_FILE.read_text())
        session_id = data.get("session_id", "default_session")
        logger.info(f"[ADK] Reusing saved session_id={session_id}")
    else:
        session_id = "default_session"
        try:
            await session_service.create_session(
                session_id=session_id,
                user_id="default_user",
                app_name="travel_bot"
            )
            SESSION_FILE.write_text(json.dumps({"session_id": session_id}))
            logger.info(f"[ADK] Created and saved session_id={session_id}")
        except Exception as e:
            logger.warning(f"[ADK] Session creation failed: {e}")
    app.state.session_id = session_id

    logger.info("[ADK] Runner initialized successfully")
    return runner

# ---------- STARTUP ----------
@app.on_event("startup")
async def startup():
    # Start MCP
    app.state._mcp_task = asyncio.create_task(start_mcp_client())
    for _ in range(50):
        if getattr(app.state, "mcp_client", None):
            break
        await asyncio.sleep(0.1)

    # Init ADK Runner
    await init_adk_runner()

# ---------- SHUTDOWN ----------
@app.on_event("shutdown")
async def shutdown():
    if getattr(app.state, "_mcp_task", None):
        app.state._mcp_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await app.state._mcp_task
    logger.info("Shutdown complete.")

# ---------- MODELS ----------
class ChatRequest(BaseModel):
    query: str

# ---------- ENDPOINT ----------
@app.post("/chat")
async def chat(body: ChatRequest):
    query = body.query
    logger.info(f"[CHAT] query={query}")

    # If ADK is not available, echo fallback
    if not (ADK_AVAILABLE and app.state.runner):
        logger.warning("ADK unavailable — echo mode.")
        return {"response": f"Echo: {query}"}

    # Ensure session exists
    session_id = app.state.session_id
    try:
        # Run LLM agent
        prompt = f"USER QUERY:\n{query}\n\nCONTEXT:\n{json.dumps(app.state.context, indent=2)}"
        content = types.Content(role="user", parts=[types.Part(text=prompt)])

        texts = []
        async for event in app.state.runner.run_async(
            session_id=session_id,
            user_id="default_user",
            new_message=content,
            run_config=RunConfig(),
        ):
            if getattr(event, "data", None):
                texts.append(str(event.data))
            elif getattr(event, "content", None):
                for p in getattr(event.content, "parts", []):
                    if getattr(p, "text", None):
                        texts.append(p.text)

        raw_output = " ".join(texts).strip()
        logger.info(f"[ADK] Output: {raw_output[:800]}")
        return {"session_id": session_id, "response": raw_output}

    except ValueError as ve:
        if "Session not found" in str(ve):
            # recreate and save new session
            session_id = f"session_{os.urandom(3).hex()}"
            await app.state.db_session_service.create_session(
                session_id=session_id,
                user_id="default_user",
                app_name="travel_bot"
            )
            SESSION_FILE.write_text(json.dumps({"session_id": session_id}))
            app.state.session_id = session_id
            logger.info(f"[ADK] Recreated session_id={session_id} after invalidation")
            raise HTTPException(status_code=503, detail="Session recreated, retry your request.")
        raise
    except Exception as e:
        logger.exception("[CHAT] Failed processing message")
        raise HTTPException(status_code=500, detail=str(e))

# ---------- HEALTH ----------
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "adk": ADK_AVAILABLE and bool(app.state.runner),
        "session_id": app.state.session_id,
        "mcp_ready": bool(app.state.mcp_client),
    }
