#!/usr/bin/env bash
# start.sh — One-command local dev startup for RedisAgent
# Usage: ./start.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

echo ""
echo -e "${RED}${BOLD}🔴 RedisAgent — Local Dev Startup${RESET}"
echo -e "${CYAN}─────────────────────────────────────${RESET}"
echo ""

# Check .env exists
if [ ! -f ".env" ]; then
  echo -e "${YELLOW}⚠️  .env not found — copying from .env.example${RESET}"
  cp .env.example .env
  echo -e "   Edit ${BOLD}.env${RESET} and set your ${BOLD}GOOGLE_API_KEY${RESET}, then re-run this script."
  exit 1
fi

# Check Redis
echo -e "${CYAN}[1/4] Checking Redis...${RESET}"
if command -v redis-cli &>/dev/null; then
  if redis-cli ping &>/dev/null; then
    echo -e "  ${GREEN}✓ Redis is running${RESET}"
  else
    echo -e "  ${YELLOW}⚡ Starting Redis server in background...${RESET}"
    redis-server --daemonize yes
    sleep 1
    echo -e "  ${GREEN}✓ Redis started${RESET}"
  fi
else
  echo -e "  ${YELLOW}⚠️  redis-cli not found. Make sure Redis is running at localhost:6379${RESET}"
fi

# Backend venv + install
echo -e "\n${CYAN}[2/4] Setting up backend...${RESET}"
cd backend
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install -q -r requirements.txt
echo -e "  ${GREEN}✓ Backend dependencies installed${RESET}"

# Start backend in background
echo -e "\n${CYAN}[3/4] Starting FastAPI backend on :8001...${RESET}"
nohup uvicorn main:app --host 0.0.0.0 --port 8001 > ../backend.log 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > ../backend.pid
sleep 2

if kill -0 $BACKEND_PID 2>/dev/null; then
  echo -e "  ${GREEN}✓ Backend running (PID $BACKEND_PID)${RESET}"
  echo -e "  Logs: ${BOLD}backend.log${RESET} | Health: ${BOLD}http://localhost:8001/health${RESET}"
else
  echo -e "  ${RED}✗ Backend failed to start — check backend.log${RESET}"
  deactivate
  exit 1
fi

deactivate
cd ..

# Frontend
echo -e "\n${CYAN}[4/4] Starting Streamlit frontend on :8501...${RESET}"
cd frontend

if [ ! -d "venv" ]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install -q -r requirements.txt

if [ ! -f ".streamlit/secrets.toml" ]; then
  mkdir -p .streamlit
  echo 'BACKEND_URL = "http://localhost:8001"' > .streamlit/secrets.toml
fi

echo ""
echo -e "${GREEN}${BOLD}══════════════════════════════════════════${RESET}"
echo -e "${GREEN}${BOLD}  🔴 RedisAgent is starting up!${RESET}"
echo -e "${GREEN}${BOLD}──────────────────────────────────────────${RESET}"
echo -e "  UI:      ${BOLD}http://localhost:8501${RESET}"
echo -e "  API:     ${BOLD}http://localhost:8001${RESET}"
echo -e "  Health:  ${BOLD}http://localhost:8001/health${RESET}"
echo -e "${GREEN}${BOLD}──────────────────────────────────────────${RESET}"
echo -e "  Press ${BOLD}Ctrl+C${RESET} to stop the frontend."
echo -e "  To stop backend: ${BOLD}kill \$(cat ../backend.pid)${RESET}"
echo -e "${GREEN}${BOLD}══════════════════════════════════════════${RESET}"
echo ""

streamlit run app.py
