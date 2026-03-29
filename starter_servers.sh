#!/bin/bash
# ----------------------------------------------------------------
# start_servers.sh — Kill stuck ports and start backend + frontend
# ----------------------------------------------------------------

# --- Kill stuck backend ports ---
echo "🔹 Killing backend ports 5001 and 5002..."
for port in 5001 5002; do
    pids=$(lsof -t -i:$port)
    if [ -n "$pids" ]; then
        echo "  Killing PID(s) on port $port: $pids"
        kill -9 $pids
    fi
done

# --- Kill stuck frontend ports ---
echo "🔹 Killing frontend ports 3000 and 3001..."
for port in 3000 3001; do
    pids=$(lsof -t -i:$port)
    if [ -n "$pids" ]; then
        echo "  Killing PID(s) on port $port: $pids"
        kill -9 $pids
    fi
done

# --- Start backend ---
echo "🔹 Starting backend on port 5002..."
cd backend || exit
nohup ../backend/venv/bin/python3 run.py > backend.log 2>&1 &
sleep 3
echo "  Backend started."

# --- Start frontend ---
echo "🔹 Starting frontend on port 3000..."
cd ../frontend || exit
nohup npm run dev > frontend.log 2>&1 &
sleep 3
echo "  Frontend started."

# --- Finished ---
echo "✅ All servers started!"
echo "  Backend: http://localhost:5002"
echo "  Frontend: http://localhost:3000"