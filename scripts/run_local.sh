#!/bin/bash
# run_local.sh - Run DecentraStore locally for development/testing
# This starts all services in separate terminals or background processes

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${BLUE}[DecentraStore]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }

# Configuration
DISCOVERY_PORT=4000
BACKEND_PORT=5000
NODE_PORTS=(6001 6002 6003)  # 3 storage nodes

# PID file for cleanup
PID_FILE="$PROJECT_DIR/.pids"

cleanup() {
    log "Stopping all services..."
    if [ -f "$PID_FILE" ]; then
        while read pid; do
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null || true
            fi
        done < "$PID_FILE"
        rm -f "$PID_FILE"
    fi
    success "All services stopped"
}

trap cleanup EXIT INT TERM

cd "$PROJECT_DIR"

# Install dependencies if needed
if ! python3 -c "import flask" 2>/dev/null; then
    log "Installing dependencies..."
    pip install -r requirements.txt --quiet
fi

# Clear old PIDs
rm -f "$PID_FILE"

# Create data directories
mkdir -p data/node1 data/node2 data/node3

log "Starting DecentraStore services..."
echo ""

# Start Discovery Service
log "Starting Discovery Service on port $DISCOVERY_PORT..."
python3 -m discovery.server --port $DISCOVERY_PORT > /dev/null 2>&1 &
echo $! >> "$PID_FILE"
sleep 1
success "Discovery Service started (PID: $(tail -1 "$PID_FILE"))"

# Start Storage Nodes
for i in "${!NODE_PORTS[@]}"; do
    PORT=${NODE_PORTS[$i]}
    NODE_NUM=$((i + 1))
    log "Starting Storage Node $NODE_NUM on port $PORT..."
    python3 -m node.storage_node \
        --port $PORT \
        --discovery http://localhost:$DISCOVERY_PORT \
        --storage-dir "./data/node$NODE_NUM" \
        --node-id "local-node-$NODE_NUM" \
        > /dev/null 2>&1 &
    echo $! >> "$PID_FILE"
    sleep 0.5
    success "Storage Node $NODE_NUM started (PID: $(tail -1 "$PID_FILE"))"
done

# Wait for nodes to register
sleep 2

# Start Backend Server
log "Starting Backend Server on port $BACKEND_PORT..."
DISCOVERY_URL="http://localhost:$DISCOVERY_PORT" \
    python3 -m backend.app --port $BACKEND_PORT > /dev/null 2>&1 &
echo $! >> "$PID_FILE"
sleep 1
success "Backend Server started (PID: $(tail -1 "$PID_FILE"))"

echo ""
echo "=============================================="
echo -e "${GREEN}DecentraStore is running!${NC}"
echo "=============================================="
echo ""
echo "Services:"
echo "  • Discovery:  http://localhost:$DISCOVERY_PORT"
echo "  • Backend:    http://localhost:$BACKEND_PORT"
echo "  • Nodes:      ${NODE_PORTS[*]}"
echo ""
echo "Open http://localhost:$BACKEND_PORT in your browser"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Keep script running
wait
