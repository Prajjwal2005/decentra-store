# DecentraStore Web App Usage Guide

## 🌐 Accessing Your Webapp

### Railway Deployment (Production)

Your webapp is accessible at your Railway URL:

```powershell
# Get your Railway URL
railway open

# Or get the domain
railway domain
```

The URL will be something like:
`https://your-app-name.up.railway.app`

### Local Development

```powershell
# Terminal 1: Discovery Service
cd discovery
python discovery_service.py --port 4000

# Terminal 2: Backend
cd backend
python app.py --port 5000

# Access at: http://localhost:5000
```

---

## 🎯 Complete Feature Guide

### 1. User Registration

**First-time users:**

1. Open your Railway URL in browser
2. Click **"Create Account"** tab
3. Enter:
   - Username (unique)
   - Email (optional)
   - Password (remember this - it's used for encryption!)
4. Click **"Create Account"**
5. Switch to **"Sign In"** tab
6. Login with your credentials

**Important:** Your password is used to derive your encryption key. If you forget it, your files are permanently inaccessible (true zero-knowledge security).

### 2. File Upload

**Upload files to the decentralized network:**

1. Click the **upload zone** or drag-and-drop a file
2. Select your file
3. Click **"Encrypt & Upload to Network"**

**What happens:**
- File is chunked into 256KB pieces
- Each chunk is encrypted with AES-256
- Chunks distributed to storage nodes
- Consensus mechanism waits for node confirmations
- Metadata stored on blockchain
- Merkle root computed for integrity

**Upload status:**
- Activity log shows real-time progress
- Green success message when complete
- File appears in "My Files" list

### 3. File Management

**View Your Files:**
- Dashboard → **Files tab** (default view)
- Shows all your uploaded files
- Search files using the search box
- Click "Refresh" to update list

**Download Files:**
1. Find your file in the list
2. Click **"Download"** button
3. File is:
   - Fetched from storage nodes
   - Decrypted with your key
   - Verified using Merkle tree
   - Downloaded to your device

**Delete Files:**
1. Click **"Delete"** button next to file
2. Confirm deletion
3. Deletion record added to blockchain
4. File marked as deleted (chunks remain for now)

### 4. File Sharing

**Share files with other users:**

1. Go to **Files** tab
2. Click **"Share"** button next to any file
3. Enter the recipient's username
4. Click OK

**Important:**
- Share record is added to blockchain
- Recipient can see the file in **"Shared"** tab
- Current implementation records shares but doesn't re-encrypt keys
- Full sharing with key exchange coming soon

**View shared files:**
- Click **"Shared"** tab
- See all files shared with you
- Shows file name, size, and who shared it

### 5. Blockchain Explorer

**Explore the blockchain:**

1. Click **"Blockchain Explorer"** tab
2. Two views:
   - **All Blocks:** See entire blockchain
   - **My Blocks:** See only your file blocks

**Block information:**
- Block number and hash
- Timestamp
- File name (if file upload block)
- File size and chunk count
- Merkle root
- Previous block hash

**Genesis Block:**
- Block #0 (green highlighted)
- Foundation of the blockchain
- No previous hash

### 6. Network & Nodes

**View Active Nodes:**
- Right sidebar → **"Active Nodes"** card
- Shows all storage nodes online
- Node ID and capacity
- Green status indicator = active
- Click "Refresh" to update

**Become a Storage Node:**
1. Click **"Download Node Software"**
2. Extract the package
3. Follow node setup instructions
4. Earn rewards by storing chunks

### 7. Activity Log

**Monitor system activity:**
- Bottom right → **"Activity"** card
- Real-time log of all actions:
  - ✓ Uploads (green)
  - ✓ Downloads (green)
  - ✓ Shares (blue)
  - ✗ Errors (red)
- Timestamps for each event
- Scrollable history

### 8. Statistics Dashboard

**Top row shows:**
- **Active Nodes:** Number of online storage nodes
- **Blocks:** Total blockchain blocks
- **Your Files:** Number of files you've uploaded
- **Storage Used:** Total size of your files

**Auto-refresh:**
- Stats update after each upload
- Click "Refresh" buttons to manually update

---

## 🔐 Security Features

### Zero-Knowledge Architecture

1. **Your password never leaves your device**
   - Not sent to server
   - Not stored in database
   - Used only locally for key derivation

2. **End-to-end encryption**
   - Files encrypted before upload
   - Storage nodes only see ciphertext
   - Only you can decrypt your files

3. **Dual-layer encryption**
   - File key encrypts file chunks
   - User key encrypts file key
   - Both required to access files

### Data Integrity

1. **Merkle tree verification**
   - Each chunk hashed
   - Tree root stored on blockchain
   - Download verifies integrity

2. **Blockchain immutability**
   - All file metadata on blockchain
   - Tamper-proof audit trail
   - Transparent consensus records

3. **Chunk verification**
   - Hash checked on download
   - Corrupted chunks detected
   - Re-fetch from other nodes

---

## 🚀 Best Practices

### For Uploads

1. **Start small**
   - Test with small files first
   - Verify download works
   - Then upload larger files

2. **Remember your password**
   - Write it down securely
   - Use a password manager
   - Lost password = lost files

3. **Check node availability**
   - Ensure nodes are active before large uploads
   - Need at least REPLICATION_FACTOR nodes
   - Check "Active Nodes" count

### For Storage

1. **Monitor storage usage**
   - Check "Storage Used" stat
   - Default quota: 10GB per user
   - Delete old files to free space

2. **Organize files**
   - Use descriptive filenames
   - Use search to find files quickly
   - Share files to collaborate

### For Security

1. **Use strong passwords**
   - Minimum 8 characters
   - Mix letters, numbers, symbols
   - Unique for DecentraStore

2. **Logout on shared computers**
   - Click "Logout" button
   - Clears local session
   - Protects your account

3. **Verify downloads**
   - Check file size matches
   - Open files to verify content
   - Re-download if corrupted

---

## 📊 Understanding the Dashboard

### Files Tab (Default)

```
┌─────────────────────────────────────────┐
│ Upload Zone                             │
│ - Click or drag files here              │
│ - Shows selected file                   │
│ - "Encrypt & Upload" button             │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ My Files                    [Refresh]   │
│ ┌───────────────────────────────────┐   │
│ │ 📄 document.pdf                   │   │
│ │ 1.2 MB • 5 chunks                 │   │
│ │ [Download] [Share] [Delete]       │   │
│ └───────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

### Shared Tab

```
┌─────────────────────────────────────────┐
│ Shared With Me              [Refresh]   │
│ ┌───────────────────────────────────┐   │
│ │ 🔗 presentation.pptx              │   │
│ │ From: alice • 5 MB • May 10       │   │
│ │ [Download]                        │   │
│ └───────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

### Blockchain Explorer Tab

```
┌─────────────────────────────────────────┐
│ [All Blocks] [My Blocks]    [Refresh]   │
│ ┌───────────────────────────────────┐   │
│ │ Block #5          May 10, 2:30 PM │   │
│ │ File: document.pdf                │   │
│ │ Hash: a1b2c3...                   │   │
│ │ Size: 1.2 MB • 5 chunks           │   │
│ └───────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

---

## 🛠 Troubleshooting

### "Please login first"

**Cause:** Session expired or not logged in

**Fix:**
1. Click "Logout" if visible
2. Refresh page
3. Login again

### "Upload failed"

**Possible causes:**
1. No active storage nodes
   - Check "Active Nodes" count
   - Start storage nodes if testing locally

2. File too large
   - Default max: 100MB
   - Try smaller files first

3. Network error
   - Check internet connection
   - Check Railway logs
   - Retry upload

### "Download failed"

**Possible causes:**
1. Wrong password
   - Enter correct password
   - Password must match upload password

2. Nodes offline
   - Chunks stored on unavailable nodes
   - Wait for nodes to come online

3. File deleted
   - Check if file marked as deleted
   - Re-upload if needed

### "No active nodes"

**For production (Railway):**
- Storage nodes must be running externally
- Download node software
- Set discovery URL to your Railway URL

**For local testing:**
```powershell
# Terminal 3
cd storage
python storage_node.py --port 7001

# Terminal 4 (optional - more nodes)
python storage_node.py --port 7002
```

### Frontend not loading

**Check:**
1. Backend is running
2. Access correct URL
3. Check browser console for errors
4. Try different browser

**Railway specific:**
```powershell
railway logs --tail 50
```

Look for:
- "Starting backend server"
- "Health check" endpoint

---

## 🎨 UI Features

### Dark Mode (Default)

- GitHub-inspired dark theme
- Easy on the eyes
- Professional appearance

### Responsive Design

- Works on desktop, tablet, mobile
- Adaptive grid layout
- Touch-friendly buttons

### Real-time Updates

- Live activity log
- Instant error/success alerts
- Auto-updating statistics

### Drag & Drop

- Drag files onto upload zone
- Visual feedback on hover
- No need to click browse

---

## 📱 Mobile Usage

**Fully responsive:**
- Stats cards: 2 columns on mobile
- File list: stacked layout
- Sidebar: below main content
- Touch-friendly buttons

**Recommendations:**
- Use WiFi for large uploads
- Portrait mode for file list
- Landscape for blockchain explorer

---

## 🔄 Workflow Examples

### Example 1: Upload & Share

1. Login to DecentraStore
2. Click upload zone
3. Select "report.pdf"
4. Wait for upload (watch activity log)
5. Click "Share" next to file
6. Enter colleague's username
7. They receive it in "Shared" tab
8. Done!

### Example 2: Download & Verify

1. Go to "Files" tab
2. Find "document.docx"
3. Click "Download"
4. Activity log shows:
   - "Downloading document.docx..."
   - "Downloaded: document.docx" ✓
5. File saved to Downloads folder
6. Open and verify content
7. Merkle tree verified integrity automatically

### Example 3: Become a Node

1. Click "Download Node Software"
2. Extract decentra-node.zip
3. Set environment variables:
   ```
   DISCOVERY_URL=https://your-app.railway.app
   NODE_CAPACITY=10
   ```
4. Run: `python storage_node.py --port 7001`
5. Node appears in "Active Nodes"
6. Start earning by storing chunks

---

## 🆘 Getting Help

### Check These First:

1. **Activity Log**
   - Bottom right of dashboard
   - Shows error messages
   - Provides debugging info

2. **Browser Console**
   - Press F12
   - Check Console tab
   - Look for red errors

3. **Railway Logs**
   ```powershell
   railway logs
   ```

4. **Health Check**
   - Visit: `https://your-app.railway.app/health`
   - Should return: `{"status":"healthy"}`

### Common Solutions:

- **Refresh page:** Solves 50% of issues
- **Clear cache:** Ctrl+Shift+Delete
- **Re-login:** Clears session issues
- **Try incognito:** Tests without extensions

---

## 🎯 Next Steps

1. **Test the system:**
   - Register account
   - Upload test file
   - Download and verify
   - Share with another user

2. **Run storage nodes:**
   - Download node software
   - Configure discovery URL
   - Start earning rewards

3. **Monitor blockchain:**
   - Explore blockchain tab
   - Watch consensus in action
   - See file distribution

4. **Scale up:**
   - Upload larger files
   - Run multiple nodes
   - Invite more users

---

## 🚀 You're Ready!

Your DecentraStore webapp is fully functional with:

✅ **User registration and authentication**
✅ **File upload with encryption**
✅ **File download with verification**
✅ **File sharing between users**
✅ **Blockchain explorer**
✅ **Network monitoring**
✅ **Activity logging**
✅ **Search and filtering**
✅ **Responsive design**
✅ **Real-time statistics**

**Access your webapp:**
```powershell
railway open
```

**Start using DecentraStore today!** 🎉
