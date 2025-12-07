#!/bin/bash
# deploy.sh - DecentraStore Deployment Helper
# Usage: ./scripts/deploy.sh [discovery|backend|node]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check Python
check_python() {
    if command -v python3 &> /dev/null; then
        PYTHON=python3
    elif command -v python &> /dev/null; then
        PYTHON=python
    else
        log_error "Python not found. Please install Python 3.8+"
        exit 1
    fi
    
    VERSION=$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    log_info "Using Python $VERSION"
}

# Install dependencies
install_deps() {
    log_info "Installing dependencies..."
    cd "$PROJECT_DIR"
    $PYTHON -m pip install -r requirements.txt --quiet
    log_success "Dependencies installed"
}

# Get local IP
get_local_ip() {
    # Try different methods to get local IP
    if command -v ip &> /dev/null; then
        ip route get 1 2>/dev/null | awk '{print $7; exit}'
    elif command -v hostname &> /dev/null; then
        hostname -I 2>/dev/null | awk '{print $1}'
    else
        echo "127.0.0.1"
    fi
}

# Start Discovery Service
start_discovery() {
    local HOST="${1:-0.0.0.0}"
    local PORT="${2:-4000}"
    
    log_info "Starting Discovery Service on $HOST:$PORT"
    cd "$PROJECT_DIR"
    
    $PYTHON -m discovery.server --host "$HOST" --port "$PORT"
}

# Start Backend Server
start_backend() {
    local HOST="${1:-0.0.0.0}"
    local PORT="${2:-5000}"
    local DISCOVERY="${3:-http://localhost:4000}"
    
    log_info "Starting Backend Server on $HOST:$PORT"
    log_info "Discovery URL: $DISCOVERY"
    cd "$PROJECT_DIR"
    
    DISCOVERY_URL="$DISCOVERY" $PYTHON -m backend.app --host "$HOST" --port "$PORT"
}

# Start Storage Node
start_node() {
    local HOST="${1:-0.0.0.0}"
    local PORT="${2:-6001}"
    local DISCOVERY="${3:-http://localhost:4000}"
    local STORAGE_DIR="${4:-./data/node_storage}"
    local NODE_ID="${5:-}"
    
    log_info "Starting Storage Node on $HOST:$PORT"
    log_info "Discovery URL: $DISCOVERY"
    log_info "Storage Directory: $STORAGE_DIR"
    cd "$PROJECT_DIR"
    
    CMD="$PYTHON -m node.storage_node --host $HOST --port $PORT --discovery $DISCOVERY --storage-dir $STORAGE_DIR"
    if [ -n "$NODE_ID" ]; then
        CMD="$CMD --node-id $NODE_ID"
    fi
    
    $CMD
}

# Print help
print_help() {
    echo "DecentraStore Deployment Helper"
    echo ""
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  discovery [host] [port]"
    echo "      Start the discovery service"
    echo "      Default: 0.0.0.0:4000"
    echo ""
    echo "  backend [host] [port] [discovery_url]"
    echo "      Start the backend server"
    echo "      Default: 0.0.0.0:5000, http://localhost:4000"
    echo ""
    echo "  node [host] [port] [discovery_url] [storage_dir] [node_id]"
    echo "      Start a storage node"
    echo "      Default: 0.0.0.0:6001, http://localhost:4000"
    echo ""
    echo "  install"
    echo "      Install Python dependencies"
    echo ""
    echo "  info"
    echo "      Show system information"
    echo ""
    echo "Examples:"
    echo "  # Start discovery on default port"
    echo "  $0 discovery"
    echo ""
    echo "  # Start backend connecting to remote discovery"
    echo "  $0 backend 0.0.0.0 5000 http://192.168.1.100:4000"
    echo ""
    echo "  # Start node with custom storage"
    echo "  $0 node 0.0.0.0 6001 http://192.168.1.100:4000 /data/chunks my-node-1"
}

# Show system info
show_info() {
    log_info "System Information"
    echo ""
    echo "Local IP: $(get_local_ip)"
    echo "Project Directory: $PROJECT_DIR"
    echo ""
    check_python
    echo ""
    
    if [ -f "$PROJECT_DIR/requirements.txt" ]; then
        log_info "Required packages:"
        cat "$PROJECT_DIR/requirements.txt" | grep -v "^#" | grep -v "^$"
    fi
}

# Main
case "${1:-help}" in
    discovery)
        check_python
        install_deps
        start_discovery "${2:-0.0.0.0}" "${3:-4000}"
        ;;
    backend)
        check_python
        install_deps
        start_backend "${2:-0.0.0.0}" "${3:-5000}" "${4:-http://localhost:4000}"
        ;;
    node)
        check_python
        install_deps
        start_node "${2:-0.0.0.0}" "${3:-6001}" "${4:-http://localhost:4000}" "${5:-./data/node_storage}" "${6:-}"
        ;;
    install)
        check_python
        install_deps
        ;;
    info)
        show_info
        ;;
    help|--help|-h)
        print_help
        ;;
    *)
        log_error "Unknown command: $1"
        print_help
        exit 1
        ;;
esac
