# Technical Documentation: Windows Reverse Shell v1.0

This document provides an in-depth technical description of the reverse shell implementation found in `victim_win.py` and `listener.py`.

It is intended for security researchers, developers, and students who want to understand the internal mechanics of the tool.

---

## 1. Overview

The system consists of two components:

* **Listener (`listener.py`)**
  Runs on the attacker's machine, listens for incoming TCP connections, and provides an interactive command interface.

* **Client (`victim_win.py`)**
  Deployed on the target Windows machine. Establishes an outbound connection and executes received commands.

Communication is obfuscated using a simple XOR cipher, and a custom framing protocol handles both command/response data and file transfers.

---

## 2. Communication Protocol

### 2.1 Encryption

Both sides use a static XOR key:

```python id="enc1"
XOR_KEY = 0x42

def xor_encrypt_decrypt(data):
    return bytes([b ^ XOR_KEY for b in data])
```

> ⚠️ This is **not secure encryption**. It only prevents casual inspection.

---

### 2.2 Message Framing

Each message is structured as:

```
[ 4 bytes: length ] [ N bytes: XOR-encrypted payload ]
```

**Receiver flow:**

1. Read 4 bytes → extract payload length
2. Read exactly `N` bytes
3. Decrypt using XOR

Core functions:

* `send_encrypted(sock, data)`
* `recv_encrypted(sock)`

---

### 2.3 File Transfer Protocol

Files are transmitted inline using delimiters:

* `"FILE_START"` → start signal
* Base64-encoded chunks (≈3 KB each)
* `"FILE_END"` → end signal

---

#### Upload Flow

1. Listener sends:

   ```
   upload <remote_path>
   ```
2. Client responds:

   ```
   READY_FOR_UPLOAD
   ```
3. Listener sends:

   * `FILE_START`
   * encoded chunks
   * `FILE_END`
4. Client reconstructs file and confirms

---

#### Download Flow

1. Listener sends:

   ```
   download <remote_path>
   ```
2. Client responds:

   * `FILE_START`
   * encoded chunks
   * `FILE_END`
3. Listener decodes and saves file

---

The `steal` command reuses this mechanism after generating a ZIP archive.

---

## 3. Persistence Mechanism

### 3.1 Installation (`install_persistence()`)

* Copies script to:

  ```
  %APPDATA%\WindowsUpdate.py
  ```

* Creates registry entry:

  ```
  HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run
  ```

* Value:

  ```
  Name: WindowsUpdateService
  Data: "<pythonw.exe>" "<script_path>"
  ```

`pythonw.exe` is used to avoid displaying a console window.

---

### 3.2 Automatic Installation

```python id="pers1"
if not os.path.exists(PERSIST_SCRIPT) or os.path.realpath(__file__) != PERSIST_SCRIPT:
    install_persistence()
```

This ensures persistence is installed on first execution.

---

## 4. Command Handling Flow (Client)

Inside `connect_and_loop()`:

1. Connect to attacker

2. Send banner (`user@hostname`, working directory)

3. Enter command loop:

   * Receive encrypted command
   * Dispatch logic
   * Send response

4. On failure:

   * Close socket
   * Sleep `RECONNECT_DELAY`
   * Reconnect

---

### Command Dispatch Table

| Command   | Action                            |
| --------- | --------------------------------- |
| exit      | Break loop → reconnect            |
| kill      | `sys.exit(0)`                     |
| cd <path> | `os.chdir()`                      |
| persist   | Install persistence               |
| download  | Send file                         |
| upload    | Receive file                      |
| steal     | ZIP + send                        |
| alert     | Show popup                        |
| status    | Return system info                |
| help      | Show help                         |
| other     | `subprocess.run(..., shell=True)` |

---

## 5. Listener Enhancements

* Colored output (ANSI)
* Local command execution:

  ```
  !command
  ```
* Automatic file saving
* Persistent listening after disconnects

---

## 6. Data Exfiltration (`steal`)

### Internal Flow (`steal_files()`)

1. Read `USERPROFILE`
2. Define target folders:

   * Desktop
   * Downloads
   * Pictures
   * Videos
3. Filter existing directories
4. Create ZIP in `%TEMP%`
5. Recursively add files
6. Return ZIP path

Then transmitted via the download protocol.

---

### Limitations

* No size limits
* Large archives may cause:

  * timeouts
  * memory issues

---

## 7. Popup Alerts

### Method 1: PowerShell

```powershell id="ps1"
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.MessageBox]::Show("message", "Alert", "OK", "Information")
```

### Method 2: Fallback

```cmd id="cmd1"
msg * message
```

---

## 8. Security Considerations

* XOR is weak → easily reversible
* No authentication → any client can connect
* Persistence is detectable
* Process visible in Task Manager
* Commands may be logged (Event Logs / PowerShell history)

---

## 9. Potential Improvements

* Replace XOR with TLS (`ssl` module)
* Add jittered beaconing
* Resume file transfers
* Anti-VM / anti-sandbox checks
* Reflective injection / shellcode execution
* Cleanup mechanism (registry + files)

---

## 10. Code Structure Summary

### listener.py

* `xor_encrypt_decrypt()`
* `send_encrypted()`, `recv_encrypted()`
* `receive_file()`
* `main()`

---

### victim_win.py

* `xor_encrypt_decrypt()`
* `send_encrypted()`, `recv_encrypted()`
* `install_persistence()`
* `change_dir()`, `run_command()`
* `upload_file()`
* `steal_files()`
* `show_alert()`
* `get_system_status()`
* `connect_and_loop()`

---

## 📌 Notes

* Uses only Python Standard Library
* No external dependencies
* Easy to port and compile

---

**Document version:** 1.0
Aligned with reverse shell v1.0 release
