#!/usr/bin/env python3
"""
DecentraStore Node Launcher
Interactive GUI for easy node setup - now with WebSocket (NAT-friendly)!
"""

import os
import sys
import json
import subprocess
import socket
from pathlib import Path

# Config file location
CONFIG_DIR = Path.home() / ".decentrastore"
CONFIG_FILE = CONFIG_DIR / "node_config.json"

DEFAULT_CONFIG = {
    "server_url": "",
    "storage_dir": str(Path.home() / "DecentraStore" / "chunks"),
    "node_id": "",
    "capacity_gb": 10
}


def load_config():
    """Load saved configuration."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                saved = json.load(f)
                # Migrate old config format
                if "discovery_url" in saved and "server_url" not in saved:
                    saved["server_url"] = saved["discovery_url"]
                return {**DEFAULT_CONFIG, **saved}
        except:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config):
    """Save configuration."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get_computer_name():
    """Get computer name for node ID."""
    return socket.gethostname()


def check_dependencies():
    """Check and install dependencies."""
    try:
        import socketio
        return True
    except ImportError:
        print("Installing dependencies...")
        subprocess.check_call([sys.executable, "-m", "pip", "install",
                              "python-socketio[client]", "websocket-client", "-q"])
        return True


def run_gui():
    """Run GUI configuration."""
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox, filedialog
    except ImportError:
        return False  # No GUI available

    config = load_config()

    # Create window
    root = tk.Tk()
    root.title("DecentraStore Node Setup")
    root.geometry("520x480")
    root.resizable(False, False)

    # Try to set style
    try:
        root.configure(bg="#1a1a24")
    except:
        pass

    # Style
    style = ttk.Style()
    style.configure("TLabel", padding=5)
    style.configure("TEntry", padding=5)
    style.configure("TButton", padding=10)

    # Main frame
    main_frame = ttk.Frame(root, padding=20)
    main_frame.pack(fill="both", expand=True)

    # Title
    title = ttk.Label(main_frame, text="DecentraStore Node Setup", font=("Helvetica", 16, "bold"))
    title.pack(pady=(0, 10))

    # Subtitle
    subtitle = ttk.Label(main_frame, text="WebSocket Mode - No Port Forwarding Required!", foreground="green")
    subtitle.pack(pady=(0, 20))

    # Server URL
    url_frame = ttk.Frame(main_frame)
    url_frame.pack(fill="x", pady=5)
    ttk.Label(url_frame, text="Server URL:", width=18, anchor="e").pack(side="left")
    url_entry = ttk.Entry(url_frame, width=40)
    url_entry.insert(0, config.get("server_url", ""))
    url_entry.pack(side="left", padx=5)

    # Storage Directory
    storage_frame = ttk.Frame(main_frame)
    storage_frame.pack(fill="x", pady=5)
    ttk.Label(storage_frame, text="Storage Directory:", width=18, anchor="e").pack(side="left")
    storage_entry = ttk.Entry(storage_frame, width=32)
    storage_entry.insert(0, config.get("storage_dir", ""))
    storage_entry.pack(side="left", padx=5)

    def browse_storage():
        folder = filedialog.askdirectory()
        if folder:
            storage_entry.delete(0, tk.END)
            storage_entry.insert(0, folder)

    ttk.Button(storage_frame, text="...", width=3, command=browse_storage).pack(side="left")

    # Node ID
    id_frame = ttk.Frame(main_frame)
    id_frame.pack(fill="x", pady=5)
    ttk.Label(id_frame, text="Node ID:", width=18, anchor="e").pack(side="left")
    id_entry = ttk.Entry(id_frame, width=40)
    id_entry.insert(0, config.get("node_id", "") or f"node-{get_computer_name()}")
    id_entry.pack(side="left", padx=5)

    # Capacity
    cap_frame = ttk.Frame(main_frame)
    cap_frame.pack(fill="x", pady=5)
    ttk.Label(cap_frame, text="Capacity (GB):", width=18, anchor="e").pack(side="left")
    cap_entry = ttk.Entry(cap_frame, width=40)
    cap_entry.insert(0, str(config.get("capacity_gb", 10)))
    cap_entry.pack(side="left", padx=5)

    # Status label
    status_var = tk.StringVar(value="Configure your node and click Start")
    status_label = ttk.Label(main_frame, textvariable=status_var, foreground="gray")
    status_label.pack(pady=20)

    # Buttons
    btn_frame = ttk.Frame(main_frame)
    btn_frame.pack(pady=10)

    def start_node():
        server_url = url_entry.get().strip()
        if not server_url:
            messagebox.showerror("Error", "Please enter the Server URL")
            return

        if not server_url.startswith("http"):
            server_url = "https://" + server_url

        try:
            capacity = int(cap_entry.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Capacity must be a number")
            return

        storage_dir = storage_entry.get().strip()
        node_id = id_entry.get().strip()

        # Save config
        new_config = {
            "server_url": server_url,
            "storage_dir": storage_dir,
            "node_id": node_id,
            "capacity_gb": capacity
        }
        save_config(new_config)

        # Close GUI
        root.destroy()

        # Run node
        run_node(server_url, storage_dir, node_id, capacity)

    def quit_app():
        root.destroy()
        sys.exit(0)

    ttk.Button(btn_frame, text="Start Node", command=start_node).pack(side="left", padx=10)
    ttk.Button(btn_frame, text="Quit", command=quit_app).pack(side="left", padx=10)

    # Info text
    info_text = """
How it works:
1. Your node connects OUTBOUND to the server via WebSocket
2. No port forwarding or firewall changes needed
3. The server pushes file chunks to your node for storage
4. Chunks are encrypted - you cannot read them

Get the server URL from the DecentraStore dashboard.
    """
    info_label = ttk.Label(main_frame, text=info_text, foreground="gray", justify="left")
    info_label.pack(pady=10)

    root.mainloop()
    return True


def run_cli():
    """Run CLI configuration."""
    config = load_config()

    print()
    print("=" * 60)
    print("  DecentraStore Node Setup (WebSocket Mode)")
    print("=" * 60)
    print("  No port forwarding required!")
    print()

    # Server URL
    default_url = config.get("server_url", "")
    prompt = f"Server URL [{default_url}]: " if default_url else "Server URL: "
    server_url = input(prompt).strip() or default_url

    if not server_url:
        print("Error: Server URL is required")
        sys.exit(1)

    if not server_url.startswith("http"):
        server_url = "https://" + server_url

    # Storage
    default_storage = config.get("storage_dir", str(Path.home() / "DecentraStore" / "chunks"))
    storage_dir = input(f"Storage Directory [{default_storage}]: ").strip() or default_storage

    # Node ID
    default_id = config.get("node_id", "") or f"node-{get_computer_name()}"
    node_id = input(f"Node ID [{default_id}]: ").strip() or default_id

    # Capacity
    default_cap = config.get("capacity_gb", 10)
    cap_str = input(f"Capacity in GB [{default_cap}]: ").strip()
    capacity = int(cap_str) if cap_str else default_cap

    # Save config
    new_config = {
        "server_url": server_url,
        "storage_dir": storage_dir,
        "node_id": node_id,
        "capacity_gb": capacity
    }
    save_config(new_config)

    print()
    print("Configuration saved!")
    print()

    run_node(server_url, storage_dir, node_id, capacity)


def run_node(server_url, storage_dir, node_id, capacity):
    """Run the WebSocket storage node."""
    print()
    print("=" * 60)
    print("  Starting DecentraStore Storage Node")
    print("=" * 60)
    print(f"  Server:    {server_url}")
    print(f"  Node ID:   {node_id}")
    print(f"  Storage:   {storage_dir}")
    print(f"  Capacity:  {capacity} GB")
    print("=" * 60)
    print()
    print("  Connecting via WebSocket (NAT-friendly)...")
    print("  Press Ctrl+C to stop.")
    print()

    # Create storage directory
    Path(storage_dir).mkdir(parents=True, exist_ok=True)

    # Find websocket_node.py
    script_dir = Path(__file__).parent
    node_script = script_dir / "websocket_node.py"

    if not node_script.exists():
        print(f"Error: websocket_node.py not found in {script_dir}")
        sys.exit(1)

    # Run the node
    cmd = [
        sys.executable,
        str(node_script),
        "--server", server_url,
        "--node-id", node_id,
        "--storage-dir", storage_dir,
        "--capacity", str(capacity)
    ]

    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\nNode stopped.")


def main():
    print("DecentraStore Node Launcher (WebSocket Edition)")
    print()

    # Check dependencies
    check_dependencies()

    # Check for command line args
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        run_cli()
        return

    # Try GUI first, fall back to CLI
    if not run_gui():
        print("GUI not available, using command line...")
        run_cli()


if __name__ == "__main__":
    main()
