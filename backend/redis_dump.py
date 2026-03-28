"""
Push every *.json file inside redis_dump/ into Redis.
Key = file name without extension
Value = raw file contents (string)

⚠️  INTEGRATED FLUSH-ALL – commented out by default.
    Uncomment the marked line below ONLY when you want to WIPE the whole instance.
"""

import os
import json
from pathlib import Path
import redis
from tqdm import tqdm

# ---------- tweak here ----------
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_PASSWORD = None
REDIS_DB = 0
DUMP_DIR = Path("redis_dumps/non-flight")
# --------------------------------

def flush_redis_instance(r: redis.Redis) -> None:
    """
    Deletes **ALL** keys in the current Redis DB (FLUSHDB).
    Call/enable only when you explicitly want a clean slate.
    """
    print("🧨  FLUSHING ALL DATA IN REDIS DB …")
    r.flushdb()          # <-- wipes only the selected DB (REDIS_DB)
    # r.flushall()       # <-- uncomment this instead if you want to wipe **every** DB on the server
    print("✅ Redis DB is now empty.")


def main():
    r = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        db=REDIS_DB,
        decode_responses=False,  # we store raw bytes
    )
    # quick connectivity check
    r.ping()
    print("✅ Connected to Redis")

    # ------------------------------------------------------------------
    # ⚠️  UNCOMMENT THE NEXT LINE TO ACTIVATE FULL WIPE
    # ------------------------------------------------------------------
    # flush_redis_instance(r)   # <--- activate this when you need to clear everything

    files = list(DUMP_DIR.glob("*.json"))
    if not files:
        print("No JSON files found in", DUMP_DIR.resolve())
        return

    for file in tqdm(files, desc="Uploading"):
        key = file.stem  # travel_data_25017514_….json → travel_data_25017514_….
        value = file.read_text(encoding="utf-8")
        r.set(key, value)

    print(f"🎉 Done! Uploaded {len(files)} keys into Redis.")


if __name__ == "__main__":
    main()