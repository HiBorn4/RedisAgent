#!/usr/bin/env python3
# server.py  -- Minimal Redis MCP server (stdio transport)
from mcp.server.fastmcp import FastMCP
import redis
import json
import os
from loguru import logger

# ----- Config (via ENV) -----
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ----- Init MCP -----
mcp = FastMCP("minimal-redis-mcp")

# ----- Redis Connection -----
def _redis():
    return redis.from_url(REDIS_URL, decode_responses=True)

# ----- Tools -----
@mcp.tool()
def ping_redis() -> str:
    try:
        r = _redis()
        return json.dumps({"ok": r.ping()})
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def list_keys(pattern: str = "*") -> str:
    try:
        r = _redis()
        keys = r.keys(pattern)
        return json.dumps({"count": len(keys), "keys": keys}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def get_key(key: str) -> str:
    try:
        r = _redis()
        val = r.get(key)
        return json.dumps({"key": key, "value": val}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def set_key(key: str, value: str, ttl_seconds: int = 0) -> str:
    try:
        r = _redis()
        r.set(key, value, ex=ttl_seconds or None)
        return json.dumps({"key": key, "set": True})
    except Exception as e:
        return json.dumps({"error": str(e)})

# ---------- Run ----------
if __name__ == "__main__":
    logger.info("Starting minimal Redis MCP server (stdio).")
    mcp.run(transport="stdio")
