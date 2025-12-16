#!/usr/bin/env python3
"""
DecentraStore Node Installer - GUI Version

This creates a user-friendly installer for Windows users.
Can be compiled to standalone .exe using PyInstaller:

    pip install pyinstaller
    pyinstaller --onefile --windowed --name "DecentraStore-Installer" node_installer_gui.py

Features:
- Downloads and installs DecentraStore
- Configures storage node
- Creates desktop shortcut
- Optional auto-start with Windows
- No git required (downloads zip instead)
"""

import os
import sys
import json
import shutil
import zipfile
import subprocess
from pathlib import Path
from urllib.request import urlretrieve
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading


class NodeInstallerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("DecentraStore Node Installer")
        self.root.geometry("600x500")
        self.root.resizable(False, False)

        # Configuration
        self.install_dir = Path.home() / "DecentraStore"
        self.server_url = "https://web-production-dcddc.up.railway.app"
        self.capacity_gb = 50
        self.auto_start = False

        # Build UI
        self.create_widgets()

    def create_widgets(self):
        """Create all UI widgets."""
        # Header
        header = tk.Frame(self.root, bg="#2c3e50", height=80)
        header.pack(fill=tk.X)

        title = tk.Label(
            header,
            text="DecentraStore Storage Node",
            font=("Arial", 18, "bold"),
            bg="#2c3e50",
            fg="white"
        )
        title.pack(pady=20)

        # Main content
        content = tk.Frame(self.root, padx=20, pady=20)
        content.pack(fill=tk.BOTH, expand=True)

        # Welcome message
        welcome = tk.Label(
            content,
            text="Join the decentralized storage network and earn by sharing your storage!",
            wraplength=550,
            justify=tk.LEFT
        )
        welcome.pack(pady=(0, 20))

        # Configuration section
        config_frame = tk.LabelFrame(content, text="Configuration", padx=10, pady=10)
        config_frame.pack(fill=tk.X, pady=(0, 10))

        # Installation directory
        tk.Label(config_frame, text="Installation Directory:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.dir_var = tk.StringVar(value=str(self.install_dir))
        tk.Entry(config_frame, textvariable=self.dir_var, width=50, state='readonly').grid(row=0, column=1, pady=5)

        # Server URL
        tk.Label(config_frame, text="Server URL:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.server_var = tk.StringVar(value=self.server_url)
        tk.Entry(config_frame, textvariable=self.server_var, width=50).grid(row=1, column=1, pady=5)

        # Storage capacity
        tk.Label(config_frame, text="Storage Capacity (GB):").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.capacity_var = tk.IntVar(value=self.capacity_gb)
        tk.Spinbox(config_frame, from_=1, to=1000, textvariable=self.capacity_var, width=48).grid(row=2, column=1, pady=5)

        # Auto-start checkbox
        self.autostart_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            config_frame,
            text="Start automatically with Windows",
            variable=self.autostart_var
        ).grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=5)

        # Progress section
        progress_frame = tk.LabelFrame(content, text="Installation Progress", padx=10, pady=10)
        progress_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Progress bar
        self.progress = ttk.Progressbar(progress_frame, mode='indeterminate')
        self.progress.pack(fill=tk.X, pady=(0, 10))

        # Log text area
        self.log_text = scrolledtext.ScrolledText(progress_frame, height=10, state='disabled')
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Buttons
        button_frame = tk.Frame(content)
        button_frame.pack(fill=tk.X)

        self.install_btn = tk.Button(
            button_frame,
            text="Install & Start Node",
            command=self.start_installation,
            bg="#27ae60",
            fg="white",
            font=("Arial", 12, "bold"),
            padx=20,
            pady=10
        )
        self.install_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))

        self.cancel_btn = tk.Button(
            button_frame,
            text="Cancel",
            command=self.root.quit,
            bg="#e74c3c",
            fg="white",
            font=("Arial", 12),
            padx=20,
            pady=10
        )
        self.cancel_btn.pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=(5, 0))

    def log(self, message):
        """Add message to log window."""
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
        self.root.update()

    def start_installation(self):
        """Start installation in background thread."""
        self.install_btn.config(state='disabled')
        self.cancel_btn.config(state='disabled')
        self.progress.start()

        thread = threading.Thread(target=self.run_installation, daemon=True)
        thread.start()

    def run_installation(self):
        """Run installation process."""
        try:
            # Update config from UI
            self.install_dir = Path(self.dir_var.get())
            self.server_url = self.server_var.get()
            self.capacity_gb = self.capacity_var.get()
            self.auto_start = self.autostart_var.get()

            # Step 1: Check Python
            self.log("Checking Python installation...")
            if not self.check_python():
                self.installation_failed("Python 3.8+ is required but not found")
                return

            # Step 2: Create installation directory
            self.log(f"Creating installation directory: {self.install_dir}")
            self.install_dir.mkdir(parents=True, exist_ok=True)

            # Step 3: Download DecentraStore
            self.log("Downloading DecentraStore...")
            if not self.download_decentrastore():
                self.installation_failed("Failed to download DecentraStore")
                return

            # Step 4: Install dependencies
            self.log("Installing dependencies...")
            if not self.install_dependencies():
                self.installation_failed("Failed to install dependencies")
                return

            # Step 5: Create configuration
            self.log("Creating configuration files...")
            self.create_config()

            # Step 6: Create shortcuts
            self.log("Creating shortcuts...")
            self.create_shortcuts()

            # Step 7: Done!
            self.progress.stop()
            self.log("\n✅ Installation complete!")
            self.log(f"\nServer: {self.server_url}")
            self.log(f"Capacity: {self.capacity_gb} GB")
            self.log(f"Storage location: {self.install_dir / 'node_storage'}")

            # Ask to start node
            if messagebox.askyesno("Success", "Installation complete!\n\nDo you want to start the node now?"):
                self.start_node()
            else:
                self.log("\nYou can start the node anytime using the desktop shortcut.")
                messagebox.showinfo("Complete", "Installation complete!\n\nUse the desktop shortcut to start your node.")

        except Exception as e:
            self.installation_failed(f"Unexpected error: {e}")

    def check_python(self):
        """Check if Python is installed."""
        try:
            result = subprocess.run(
                [sys.executable, "--version"],
                capture_output=True,
                text=True
            )
            self.log(f"Found: {result.stdout.strip()}")
            return True
        except Exception as e:
            self.log(f"Error: {e}")
            return False

    def download_decentrastore(self):
        """Download DecentraStore from GitHub."""
        zip_url = "https://github.com/Prajjwal2005/decentra-store/archive/refs/heads/main.zip"
        zip_path = self.install_dir / "decentra-store.zip"

        try:
            # Download
            self.log(f"Downloading from: {zip_url}")
            urlretrieve(zip_url, zip_path)
            self.log(f"Downloaded: {zip_path}")

            # Extract
            self.log("Extracting files...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(self.install_dir)

            # Move files from subdirectory
            extracted_dir = self.install_dir / "decentra-store-main"
            if extracted_dir.exists():
                for item in extracted_dir.iterdir():
                    dest = self.install_dir / item.name
                    if dest.exists():
                        if dest.is_dir():
                            shutil.rmtree(dest)
                        else:
                            dest.unlink()
                    shutil.move(str(item), str(dest))
                extracted_dir.rmdir()

            # Clean up
            zip_path.unlink()
            self.log("Extraction complete")
            return True

        except Exception as e:
            self.log(f"Download error: {e}")
            return False

    def install_dependencies(self):
        """Install Python dependencies."""
        requirements = self.install_dir / "requirements.txt"

        if not requirements.exists():
            self.log("Warning: requirements.txt not found")
            return True

        try:
            # Upgrade pip
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
                cwd=self.install_dir,
                capture_output=True
            )

            # Install requirements
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                cwd=self.install_dir,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                self.log("Dependencies installed successfully")
                return True
            else:
                self.log(f"Error installing dependencies:\n{result.stderr}")
                return False

        except Exception as e:
            self.log(f"Installation error: {e}")
            return False

    def create_config(self):
        """Create node configuration file."""
        config = {
            "server_url": self.server_url,
            "capacity_gb": self.capacity_gb,
            "auto_start": self.auto_start
        }

        config_path = self.install_dir / "node_config.json"
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)

        self.log(f"Configuration saved: {config_path}")

    def create_shortcuts(self):
        """Create desktop and startup shortcuts."""
        try:
            # Create run script
            run_script = self.install_dir / "run_node.bat"
            with open(run_script, 'w') as f:
                f.write(f'@echo off\n')
                f.write(f'cd /d "{self.install_dir}"\n')
                f.write(f'"{sys.executable}" node_package\\websocket_node.py ')
                f.write(f'--server {self.server_url} --capacity {self.capacity_gb}\n')
                f.write(f'pause\n')

            # Create desktop shortcut using PowerShell
            desktop = Path.home() / "Desktop"
            shortcut = desktop / "DecentraStore Node.lnk"

            ps_command = f'''
$WS = New-Object -ComObject WScript.Shell;
$SC = $WS.CreateShortcut('{shortcut}');
$SC.TargetPath = '{run_script}';
$SC.WorkingDirectory = '{self.install_dir}';
$SC.Description = 'Run DecentraStore Storage Node';
$SC.Save()
'''

            subprocess.run(["powershell", "-Command", ps_command], capture_output=True)

            if shortcut.exists():
                self.log(f"Created desktop shortcut: {shortcut}")
            else:
                self.log("Warning: Could not create desktop shortcut")

            # Create startup shortcut if requested
            if self.auto_start:
                startup = Path(os.getenv('APPDATA')) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
                startup_shortcut = startup / "DecentraStore Node.lnk"

                ps_command = f'''
$WS = New-Object -ComObject WScript.Shell;
$SC = $WS.CreateShortcut('{startup_shortcut}');
$SC.TargetPath = '{run_script}';
$SC.WorkingDirectory = '{self.install_dir}';
$SC.Description = 'Run DecentraStore Storage Node';
$SC.Save()
'''

                subprocess.run(["powershell", "-Command", ps_command], capture_output=True)

                if startup_shortcut.exists():
                    self.log(f"Created startup shortcut: {startup_shortcut}")

        except Exception as e:
            self.log(f"Shortcut creation error: {e}")

    def start_node(self):
        """Start the storage node."""
        try:
            node_script = self.install_dir / "node_package" / "websocket_node.py"

            if not node_script.exists():
                messagebox.showerror("Error", f"Node script not found: {node_script}")
                return

            # Start in new window
            subprocess.Popen(
                [
                    sys.executable,
                    str(node_script),
                    "--server", self.server_url,
                    "--capacity", str(self.capacity_gb)
                ],
                cwd=self.install_dir,
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )

            self.log("\n✅ Node started!")
            messagebox.showinfo("Success", "Storage node is now running!\n\nCheck the console window for status.")
            self.root.quit()

        except Exception as e:
            self.log(f"Error starting node: {e}")
            messagebox.showerror("Error", f"Failed to start node:\n{e}")

    def installation_failed(self, error_message):
        """Handle installation failure."""
        self.progress.stop()
        self.log(f"\n❌ Installation failed: {error_message}")
        self.install_btn.config(state='normal')
        self.cancel_btn.config(state='normal')
        messagebox.showerror("Installation Failed", error_message)


def main():
    """Run the installer GUI."""
    root = tk.Tk()
    app = NodeInstallerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
