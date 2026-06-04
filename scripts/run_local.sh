#!/usr/bin/env bash
# Start both the FastAPI server and Streamlit dashboard locally.
set -euo pipefail

echo "→ Starting FastAPI server on http://localhost:8000 ..."
uvicorn src.web.main:app --reload --host 0.0.0.0 --port 8000 &
API_PID=$!

echo "→ Starting Streamlit dashboard on http://localhost:8501 ..."
streamlit run app/dashboard.py --server.port 8501 --server.address 0.0.0.0 &
DASH_PID=$!

echo ""
echo "✅ Running:"
echo "   API:       http://localhost:8000"
echo "   API docs:  http://localhost:8000/docs"
echo "   Dashboard: http://localhost:8501"
echo ""
echo "Press Ctrl+C to stop both."

trap "kill $API_PID $DASH_PID 2>/dev/null; echo 'Stopped.'" EXIT INT TERM
wait
