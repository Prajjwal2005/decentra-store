# DecentraStore Storage Node

Contribute storage to the DecentraStore network!

## What This Does

Your computer will store **encrypted chunks** of other users' files. You cannot see or read any of the data - it's all encrypted. You're just providing storage space to help the network.

## Quick Start

### Windows

1. **Double-click `run_node.bat`**
2. A setup window will appear
3. Enter the Discovery Server URL (get this from the network admin)
4. Click "Start Node"

That's it! Your settings are saved for next time.

### Linux / Mac

```bash
chmod +x run_node.sh
./run_node.sh
```

Follow the prompts to enter the Discovery URL.

## Configuration

Your settings are saved in:
- **Windows:** `%USERPROFILE%\.decentrastore\node_config.json`
- **Linux/Mac:** `~/.decentrastore/node_config.json`

To change settings, either:
- Delete the config file and run again
- Or edit the JSON file directly

## Requirements

- **Python 3.8+** - Download from https://python.org
- **Open port 6001** - Must be accessible from the internet
- **Stable internet connection**

## Firewall Setup

### Windows
1. Open Windows Defender Firewall
2. Click "Allow an app through firewall"
3. Add Python and allow both Private and Public

### Linux
```bash
sudo ufw allow 6001/tcp
```

### Router Port Forwarding
If behind NAT, forward port 6001 to your computer's local IP.

## Where is Data Stored?

Encrypted chunks are stored in:
- **Windows:** `C:\Users\YourName\DecentraStore\chunks`
- **Linux/Mac:** `~/DecentraStore/chunks`

## Command Line Usage

For advanced users or automation:

```bash
python storage_node.py \
    --discovery http://SERVER:4000 \
    --port 6001 \
    --storage-dir /path/to/chunks \
    --node-id my-custom-name
```

## FAQ

**Q: Can I see what's stored?**
A: No - all data is AES-256 encrypted. You only see random binary blobs.

**Q: Will it slow down my computer?**
A: Minimal impact. The node only responds when others request chunks.

**Q: How do I stop?**
A: Press Ctrl+C or close the terminal window.

**Q: What if I lose internet?**
A: The node will automatically try to reconnect. Other copies of the data exist on other nodes.

## Troubleshooting

**"Python not found"**
→ Install Python from https://python.org (check "Add to PATH")

**"Connection refused"**
→ Check that the Discovery URL is correct and the server is running

**"Port already in use"**
→ Change the port in the launcher or use `--port 6002`

**GUI doesn't appear**
→ Run with `--cli` flag: `python launcher.py --cli`
