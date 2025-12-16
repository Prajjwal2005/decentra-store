# DecentraStore Node Installer Guide

Complete guide for creating and distributing automated Windows installers for storage nodes.

## 📋 Table of Contents

1. [Overview](#overview)
2. [Installation Methods](#installation-methods)
3. [Batch File Installer](#batch-file-installer)
4. [GUI Installer](#gui-installer)
5. [Building the Executable](#building-the-executable)
6. [Distribution Options](#distribution-options)
7. [Troubleshooting](#troubleshooting)

---

## Overview

DecentraStore offers multiple ways for Windows users to become storage nodes:

| Method | Ease of Use | Requirements | Best For |
|--------|-------------|--------------|----------|
| **Manual Installation** | ⭐⭐ | Git + Python | Developers |
| **Batch Installer** | ⭐⭐⭐⭐ | Python | Tech-savvy users |
| **GUI Installer (.exe)** | ⭐⭐⭐⭐⭐ | None | Everyone |

The automated installers eliminate the need for users to:
- Clone repositories manually
- Run command-line Python scripts
- Understand Git or Python

---

## Installation Methods

### Method 1: Batch File Installer (Simplest Distribution)

**File:** `install_node_windows.bat`

**Requirements:**
- Python 3.8+
- Git (for cloning repository)

**How to use:**
1. Download `install_node_windows.bat`
2. Double-click to run
3. Follow prompts

**Features:**
- ✅ Automatic repository cloning
- ✅ Dependency installation
- ✅ Configuration wizard
- ✅ Desktop shortcut creation
- ✅ Optional auto-start with Windows
- ✅ Update existing installations

**Distribution:**
Upload the `.bat` file to your website or GitHub releases. Users download and run.

---

### Method 2: GUI Installer (Best User Experience)

**File:** `node_installer_gui.py` → compiled to `DecentraStore-Installer.exe`

**Requirements:** None (standalone executable)

**Features:**
- ✅ Professional GUI interface
- ✅ Real-time progress tracking
- ✅ No Git required (downloads ZIP from GitHub)
- ✅ One-click installation
- ✅ Configuration through UI
- ✅ Auto-start option
- ✅ Desktop shortcut creation

---

## Building the Executable

### Prerequisites

Install PyInstaller:
```bash
pip install pyinstaller
```

### Option 1: Using the Build Script (Recommended)

```bash
# Build the installer
python build_installer.py

# Output: dist/DecentraStore-Installer.exe
```

### Option 2: Manual PyInstaller Command

```bash
pyinstaller --onefile --windowed --name "DecentraStore-Installer" node_installer_gui.py
```

### Build Options Explained

- `--onefile`: Creates a single executable (no dependencies)
- `--windowed`: No console window (GUI only)
- `--name`: Output executable name
- `--icon`: Add custom icon (optional)

### Build Output

```
dist/
  DecentraStore-Installer.exe  ← Distribute this file (~15-20 MB)

build/                         ← Temporary (can delete)
DecentraStore-Installer.spec   ← PyInstaller config (can delete)
```

### Clean Build Artifacts

```bash
python build_installer.py --clean
```

---

## Distribution Options

### Option 1: Website Download

Upload `DecentraStore-Installer.exe` to your website:

```html
<a href="DecentraStore-Installer.exe" download>
  Download DecentraStore Node Installer
</a>
```

**Recommended hosting:**
- Your own website
- GitHub Releases
- Cloud storage (Dropbox, Google Drive, OneDrive)

### Option 2: GitHub Releases

1. Go to your repository
2. Click "Releases" → "Create a new release"
3. Upload `DecentraStore-Installer.exe`
4. Publish release

Users can then download from:
```
https://github.com/YOUR_USERNAME/decentra-store/releases/latest/download/DecentraStore-Installer.exe
```

### Option 3: Direct Link on Web Interface

Add to your `frontend/index.html`:

```html
<div class="become-node-section">
  <h2>💰 Become a Storage Provider</h2>
  <p>Earn by sharing your unused storage space!</p>

  <div class="download-options">
    <a href="https://github.com/Prajjwal2005/decentra-store/releases/latest/download/DecentraStore-Installer.exe"
       class="download-btn windows">
      <i class="fab fa-windows"></i>
      Download for Windows
    </a>

    <a href="install_node_windows.bat"
       class="download-btn batch">
      <i class="fas fa-terminal"></i>
      Download Batch Installer
    </a>
  </div>
</div>
```

---

## How the Installers Work

### Batch Installer Flow

```
1. Check Python & Git installed
   ↓
2. Clone repository to %USERPROFILE%\DecentraStore
   ↓
3. Install requirements.txt
   ↓
4. Ask user for configuration:
   - Server URL
   - Storage capacity
   - Auto-start preference
   ↓
5. Create run_node.bat script
   ↓
6. Create desktop shortcut
   ↓
7. Optionally create startup shortcut
   ↓
8. Offer to start node immediately
```

### GUI Installer Flow

```
1. Display configuration UI
   ↓
2. User sets:
   - Server URL (default: Railway)
   - Storage capacity (default: 50 GB)
   - Auto-start checkbox
   ↓
3. Click "Install & Start Node"
   ↓
4. Download repository ZIP from GitHub
   ↓
5. Extract files
   ↓
6. Install Python dependencies
   ↓
7. Create configuration file
   ↓
8. Create shortcuts
   ↓
9. Show progress in real-time
   ↓
10. Offer to start node
```

---

## Configuration Details

### Default Settings

| Setting | Default Value | Description |
|---------|---------------|-------------|
| Server URL | `https://web-production-dcddc.up.railway.app` | Your Railway deployment |
| Storage Capacity | 50 GB | Storage space to allocate |
| Installation Dir | `%USERPROFILE%\DecentraStore` | Where files are installed |
| Auto-start | False | Start with Windows |

### Customization

Users can change these during installation, or modify later:

**Batch installer:** Re-run the installer
**GUI installer:** Edit `node_config.json` in installation directory

---

## Files Created by Installer

After installation, the following structure is created:

```
%USERPROFILE%\DecentraStore/
├── backend/              # Backend API code
├── frontend/             # Web interface
├── node_package/         # Storage node code
│   └── websocket_node.py # Node client
├── requirements.txt      # Dependencies
├── run_node.bat         # Launch script
├── node_config.json     # Configuration
└── node_storage/        # Chunk storage (created on first run)

%USERPROFILE%\Desktop/
└── DecentraStore Node.lnk  # Desktop shortcut

%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup/
└── DecentraStore Node.lnk  # Auto-start (if enabled)
```

---

## Troubleshooting

### Common Issues

#### 1. Python Not Found

**Error:** "Python is not installed or not in PATH"

**Solution:**
1. Install Python from https://python.org/downloads/
2. **Important:** Check "Add Python to PATH" during installation
3. Restart installer

#### 2. Git Not Found (Batch Installer Only)

**Error:** "Git is not installed or not in PATH"

**Solution:**
1. Install Git from https://git-scm.com/download/win
2. Restart installer

**Alternative:** Use GUI installer instead (doesn't require Git)

#### 3. Download Failed

**Error:** "Failed to download DecentraStore"

**Solution:**
- Check internet connection
- Verify GitHub is accessible
- Try again later
- Use batch installer as alternative

#### 4. Permission Denied

**Error:** "Access denied" or "Permission error"

**Solution:**
- Run installer as Administrator (right-click → "Run as administrator")
- Choose a different installation directory with write permissions

#### 5. Dependencies Installation Failed

**Error:** "Failed to install dependencies"

**Solution:**
```bash
# Upgrade pip first
python -m pip install --upgrade pip

# Then re-run installer
```

#### 6. Shortcut Not Created

**Error:** Desktop shortcut missing

**Solution:**
Manually create shortcut:
1. Right-click desktop → New → Shortcut
2. Target: `%USERPROFILE%\DecentraStore\run_node.bat`
3. Name: "DecentraStore Node"

#### 7. Node Won't Connect

**Error:** "Connection failed" or "Cannot reach server"

**Solution:**
- Verify server URL is correct
- Check firewall settings
- Ensure Railway deployment is running
- Test server URL in browser

### Debug Mode

Run node manually to see detailed logs:

```bash
cd %USERPROFILE%\DecentraStore
python node_package\websocket_node.py --server https://web-production-dcddc.up.railway.app --capacity 50
```

---

## Advanced: Customizing the Installer

### Change Default Server URL

Edit `node_installer_gui.py`:

```python
# Line ~50
self.server_url = "https://your-custom-domain.com"
```

Then rebuild:
```bash
python build_installer.py
```

### Add Custom Icon

1. Create or download an `.ico` file
2. Place it in the project directory (e.g., `icon.ico`)
3. Edit `build_installer.py`:

```python
cmd = [
    "pyinstaller",
    "--onefile",
    "--windowed",
    "--name", "DecentraStore-Installer",
    "--icon=icon.ico",  # ← Add this
    "node_installer_gui.py"
]
```

4. Rebuild

### Change Installation Directory

Edit `node_installer_gui.py`:

```python
# Line ~48
self.install_dir = Path.home() / "MyCustomFolder"
```

---

## Security Considerations

### Code Signing (Recommended for Production)

Windows may show "Unknown Publisher" warning for unsigned executables.

To sign the `.exe`:

1. Obtain a code signing certificate
2. Use `signtool.exe` (comes with Windows SDK):

```bash
signtool sign /f certificate.pfx /p password /t http://timestamp.digicert.com DecentraStore-Installer.exe
```

**Note:** Code signing certificates cost $100-$400/year but increase user trust.

### Antivirus False Positives

PyInstaller executables sometimes trigger antivirus warnings.

**Solutions:**
1. Upload to VirusTotal and share results
2. Get code signing certificate
3. Provide source code and batch installer as alternatives
4. Contact antivirus vendors to whitelist

---

## Testing Checklist

Before distributing, test the installer:

- [ ] Fresh Windows installation (or VM)
- [ ] Python installed correctly
- [ ] Installer downloads files
- [ ] Dependencies install successfully
- [ ] Configuration is saved
- [ ] Desktop shortcut works
- [ ] Auto-start shortcut created (if enabled)
- [ ] Node connects to server
- [ ] Node registers successfully
- [ ] Chunks can be stored
- [ ] Uninstall/reinstall works

---

## Uninstalling

Users can uninstall by:

1. Delete `%USERPROFILE%\DecentraStore` folder
2. Delete desktop shortcut
3. Delete startup shortcut (if auto-start enabled)

**Optional:** Create an uninstaller script:

```batch
@echo off
echo Uninstalling DecentraStore...
rmdir /s /q "%USERPROFILE%\DecentraStore"
del "%USERPROFILE%\Desktop\DecentraStore Node.lnk"
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\DecentraStore Node.lnk"
echo Uninstall complete!
pause
```

---

## Future Enhancements

Potential improvements:

- [ ] macOS installer (.dmg or .app)
- [ ] Linux installer (.deb, .rpm, AppImage)
- [ ] Auto-update functionality
- [ ] System tray integration
- [ ] GUI for node management (view stats, pause/resume)
- [ ] Bandwidth limiting options
- [ ] Storage quota monitoring
- [ ] Earnings dashboard

---

## Support

If users encounter issues:

1. Check logs: `%USERPROFILE%\DecentraStore\node_storage\node.log`
2. Visit GitHub: https://github.com/Prajjwal2005/decentra-store/issues
3. Contact support: your-email@example.com

---

## License

Same as DecentraStore main project (MIT License)

---

**Last Updated:** 2025-12-16
**Version:** 1.0.0
**Maintainer:** Prajjwal2005
