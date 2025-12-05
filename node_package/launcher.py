#!/usr/bin/env python3
"""
DecentraStore Node Launcher
Interactive GUI for easy node setup on any network.
"""

import os
import sys
import json
import subprocess
from pathlib import Path

# Config file location
CONFIG_DIR = Path.home() / ".decentrastore"
CONFIG_FILE = CONFIG_DIR / "node_config.json"

DEFAULT_CONFIG = {
    "discovery_url": "",
    "node_port": 6001,
    "storage_dir": str(Path.home() / "DecentraStore" / "chunks"),
    "node_id": ""
}


def load_config():
    """Load saved configuration."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
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
    import socket
    return socket.gethostname()


def check_dependencies():
    """Check and install dependencies."""
    try:
        import flask
        import requests
        return True
    except ImportError:
        print("Installing dependencies...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", 
                              "flask", "flask-cors", "requests", "-q"])
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
    root.geometry("500x400")
    root.resizable(False, False)
    
    # Try to set icon and style
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
    title.pack(pady=(0, 20))
    
    # Discovery URL
    url_frame = ttk.Frame(main_frame)
    url_frame.pack(fill="x", pady=5)
    ttk.Label(url_frame, text="Discovery Server URL:", width=20, anchor="e").pack(side="left")
    url_entry = ttk.Entry(url_frame, width=35)
    url_entry.insert(0, config.get("discovery_url", ""))
    url_entry.pack(side="left", padx=5)
    
    # Port
    port_frame = ttk.Frame(main_frame)
    port_frame.pack(fill="x", pady=5)
    ttk.Label(port_frame, text="Node Port:", width=20, anchor="e").pack(side="left")
    port_entry = ttk.Entry(port_frame, width=35)
    port_entry.insert(0, str(config.get("node_port", 6001)))
    port_entry.pack(side="left", padx=5)
    
    # Storage Directory
    storage_frame = ttk.Frame(main_frame)
    storage_frame.pack(fill="x", pady=5)
    ttk.Label(storage_frame, text="Storage Directory:", width=20, anchor="e").pack(side="left")
    storage_entry = ttk.Entry(storage_frame, width=28)
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
    ttk.Label(id_frame, text="Node ID (optional):", width=20, anchor="e").pack(side="left")
    id_entry = ttk.Entry(id_frame, width=35)
    id_entry.insert(0, config.get("node_id", "") or f"node-{get_computer_name()}")
    id_entry.pack(side="left", padx=5)
    
    # Status label
    status_var = tk.StringVar(value="Configure your node and click Start")
    status_label = ttk.Label(main_frame, textvariable=status_var, foreground="gray")
    status_label.pack(pady=20)
    
    # Buttons
    btn_frame = ttk.Frame(main_frame)
    btn_frame.pack(pady=10)
    
    def start_node():
        discovery_url = url_entry.get().strip()
        if not discovery_url:
            messagebox.showerror("Error", "Please enter the Discovery Server URL")
            return
        
        if not discovery_url.startswith("http"):
            discovery_url = "http://" + discovery_url
        
        try:
            port = int(port_entry.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Port must be a number")
            return
        
        storage_dir = storage_entry.get().strip()
        node_id = id_entry.get().strip()
        
        # Save config
        new_config = {
            "discovery_url": discovery_url,
            "node_port": port,
            "storage_dir": storage_dir,
            "node_id": node_id
        }
        save_config(new_config)
        
        # Close GUI
        root.destroy()
        
        # Run node
        run_node(discovery_url, port, storage_dir, node_id)
    
    def quit_app():
        root.destroy()
        sys.exit(0)
    
    ttk.Button(btn_frame, text="Start Node", command=start_node).pack(side="left", padx=10)
    ttk.Button(btn_frame, text="Quit", command=quit_app).pack(side="left", padx=10)
    
    # Info text
    info_text = """
Note: You need the Discovery Server URL from your network admin.
Port 6001 must be open in your firewall.
Chunks will be stored encrypted - you cannot read them.
    """
    info_label = ttk.Label(main_frame, text=info_text, foreground="gray", justify="center")
    info_label.pack(pady=10)
    
    root.mainloop()
    return True


def run_cli():
    """Run CLI configuration."""
    config = load_config()
    
    print()
    print("=" * 50)
    print("  DecentraStore Node Setup")
    print("=" * 50)
    print()
    
    # Discovery URL
    default_url = config.get("discovery_url", "")
    prompt = f"Discovery Server URL [{default_url}]: " if default_url else "Discovery Server URL: "
    discovery_url = input(prompt).strip() or default_url
    
    if not discovery_url:
        print("Error: Discovery URL is required")
        sys.exit(1)
    
    if not discovery_url.startswith("http"):
        discovery_url = "http://" + discovery_url
    
    # Port
    default_port = config.get("node_port", 6001)
    port_str = input(f"Node Port [{default_port}]: ").strip()
    port = int(port_str) if port_str else default_port
    
    # Storage
    default_storage = config.get("storage_dir", str(Path.home() / "DecentraStore" / "chunks"))
    storage_dir = input(f"Storage Directory [{default_storage}]: ").strip() or default_storage
    
    # Node ID
    default_id = config.get("node_id", "") or f"node-{get_computer_name()}"
    node_id = input(f"Node ID [{default_id}]: ").strip() or default_id
    
    # Save config
    new_config = {
        "discovery_url": discovery_url,
        "node_port": port,
        "storage_dir": storage_dir,
        "node_id": node_id
    }
    save_config(new_config)
    
    print()
    print("Configuration saved!")
    print()
    
    run_node(discovery_url, port, storage_dir, node_id)


def run_node(discovery_url, port, storage_dir, node_id):
    """Run the storage node."""
    print()
    print("=" * 50)
    print("  Starting DecentraStore Storage Node")
    print("=" * 50)
    print(f"  Discovery: {discovery_url}")
    print(f"  Port:      {port}")
    print(f"  Storage:   {storage_dir}")
    print(f"  Node ID:   {node_id}")
    print("=" * 50)
    print()
    
    # Create storage directory
    Path(storage_dir).mkdir(parents=True, exist_ok=True)
    
    # Find storage_node.py
    script_dir = Path(__file__).parent
    node_script = script_dir / "storage_node.py"
    
    if not node_script.exists():
        print(f"Error: storage_node.py not found in {script_dir}")
        sys.exit(1)
    
    # Run the node
    cmd = [
        sys.executable,
        str(node_script),
        "--host", "0.0.0.0",
        "--port", str(port),
        "--discovery", discovery_url,
        "--storage-dir", storage_dir,
        "--node-id", node_id
    ]
    
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\nNode stopped.")


def main():
    print("DecentraStore Node Launcher")
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
