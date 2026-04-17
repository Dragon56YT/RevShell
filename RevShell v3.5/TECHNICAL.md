# Technical Documentation: Windows Reverse Shell v3.5

This document provides a comprehensive technical description of the reverse shell implementation found in `victim_win.py` (v3.5) and `listener.py` (v3.5). It covers architecture, encryption, protocol, module details, and all changes introduced in version 3.5.

---

## 1. Overview

Version 3.5 is a **major evolution** from v2.0, introducing:

- **Strong encryption:** RC4 with per-message nonce and SHA-256 key derivation.
- **Beacon jitter:** Randomized reconnection intervals.
- **Anti-VM / sandbox detection:** Prevents execution in analysis environments.
- **Decoy GUI:** A fake installer window that distracts the user.
- **50+ new commands:** Covering advanced post-exploitation, lateral movement, and system manipulation.
- **Autodestroy:** Complete self-removal, including persistence artifacts.

---

## 2. Architecture & Design

### 2.1 High-Level Structure

```
┌─────────────────────────────────────────────────────────────────┐
│ victim_win.py                                                   │
├─────────────────────────────────────────────────────────────────┤
│ Configuration  │ IP, port, shared secret, jitter settings       │
│ Crypto Layer   │ RC4 + nonce + SHA-256                          │
│ Helpers        │ run_cmd, run_ps, file transfer, admin check    │
│ Persistence    │ install/check/remove/toggle (3+ methods)       │
│ Decoy          │ launch_decoy() – fake installer GUI            │
│ Modules        │ 50+ functions for all commands                 │
│ Dispatcher     │ handle_command() – routes 150+ commands        │
│ Connection Loop│ connect_and_loop() – jitter, reconnect         │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Command Dispatcher

The `handle_command(sock, cmd)` function is the central router. It examines the command string and calls the appropriate handler. This design keeps the main loop clean and makes adding new commands straightforward.

### 2.3 File Command Protocol

Commands that return a file follow this pattern:

1. Victim sends a **status message** (e.g., `[+] Collecting files...`).
2. Victim sends `FILE_START`.
3. Victim sends file data as a series of base64-encoded chunks.
4. Victim sends `FILE_END`.

If an error occurs during file creation, the victim sends an error message (starting with `[-]`) and **no** `FILE_START`. The listener detects this and displays the error without attempting to save a file.

---

## 3. Encryption – RC4 with Nonce

### 3.1 Why Upgrade from XOR?

The single-byte XOR in v2.0 was trivial to break. v3.5 implements a **per-message keyed RC4 stream cipher** with a random nonce, providing:

- Confidentiality against passive network monitoring.
- Replay protection (each message has a unique nonce).
- Configurable shared secret.

### 3.2 Algorithm Details

**Encryption (`_encrypt_data`):**

1. Generate a cryptographically random **8-byte nonce** using `os.urandom(8)`.
2. Derive the RC4 key: `key = SHA-256(SHARED_SECRET + nonce)` → 32 bytes.
3. Encrypt the plaintext with RC4 using the derived key.
4. Return `nonce + ciphertext`.

**Decryption (`_decrypt_data`):**

1. Extract the first 8 bytes as the nonce.
2. Derive the same RC4 key using `SHA-256(SHARED_SECRET + nonce)`.
3. Decrypt the remaining bytes with RC4.

**RC4 Implementation (`_rc4`):**

- Standard RC4 key-scheduling algorithm (KSA) and pseudo-random generation algorithm (PRGA).
- Operates on bytes.

### 3.3 Security Considerations

- **RC4 is not suitable for TLS** but is more than adequate for obfuscating C2 traffic in a controlled lab.
- **Nonce size (8 bytes)** provides a 2^64 space, making nonce reuse extremely unlikely.
- **SHA-256** ensures that each message uses a unique, unpredictable RC4 key.

---

## 4. Beacon Jitter

The client can randomize its reconnection delay to evade detection based on fixed intervals.

```python
if BEACON_JITTER:
    delay = random.uniform(BEACON_MIN, BEACON_MAX)
else:
    delay = RECONNECT_DELAY
time.sleep(delay)
```

Configuration:

- `BEACON_JITTER = True`
- `BEACON_MIN = 3` (seconds)
- `BEACON_MAX = 10` (seconds)

---

## 5. Anti-VM and Sandbox Evasion

The function `check_vm()` (invoked at startup) performs several checks:

| Check | Implementation | Indicator if true |
|---|---|---|
| Screen resolution | GetSystemMetrics(0), GetSystemMetrics(1) | Width < 800 or Height < 600 |
| RAM size | GetPhysicallyInstalledSystemMemory | < 2 GB |
| BIOS manufacturer | wmic baseboard get manufacturer | Contains microsoft, vmware, virtualbox, qemu, oracle, innotek |
| Uptime | GetTickCount64() | < 10 minutes |

If any check indicates a VM/sandbox, the implant sleeps for 60–300 seconds and then exits without performing any malicious activity.

---

## 6. Decoy GUI

The function `launch_decoy()` is called when the implant runs for the first time (not from the persistent location). It spawns a background thread that displays a Tkinter window titled "ModLoader Pro - Installer v3.2".

The window shows a progress bar that slowly fills with fake status messages.

At the end, a message box appears with an error: "Error 0x80070005: Access is denied."

The GUI then closes.

**Purpose:** Convince the user that the program simply failed to install, reducing suspicion while the implant operates.

---

## 7. New Modules in v3.5

### 7.1 File System Tools

| Function | Description |
|---|---|
| `tree_dir(path, depth)` | Recursively display directory tree (limits to 200 entries) |
| `grep_files(pattern, path)` | Search for text inside files; uses findstr for directories |
| `head_file` / `tail_file` | Read first/last N lines of a text file |
| `write_file` / `append_file` | Write or append content to a file |
| `change_timestamp` | Modify file creation/modification timestamps |
| `search_files` | Search files by name using dir /s /b |
| `file_info` | Show size, timestamps, permissions, and MD5/SHA256 hashes |

### 7.2 Surveillance & Espionage

| Function | Description |
|---|---|
| `record_screen(sec)` | Capture screen at 10 fps, save frames as JPG, zip them |
| `record_mic(sec)` | Record audio via winmm.dll mciSendString, save as WAV |
| `webcam_snap()` | Take a photo using WIA COM object (fallback to ffmpeg) |
| `scrloop_control()` | Periodic screenshot capture with start/stop/dump/clear |

### 7.3 Credential Harvesting

| Function | Description |
|---|---|
| `dump_credvault()` | Enumerate Windows Credential Manager (cmdkey) and DPAPI files |
| `find_secrets()` | Search for SSH keys, cloud credentials, VPN configs, KeePass DBs, etc. |
| `ssh_keys()` | List and display SSH keys from .ssh directory |
| `token_steal()` | Run whoami /all, cmdkey /list, query session, query user |

### 7.4 Network Tools

| Function | Description |
|---|---|
| `port_scan(target, ports)` | TCP connect scan with 0.5s timeout |
| `net_scan(subnet)` | Ping sweep using PowerShell jobs (parallel) |
| `dns_lookup(name)` | Forward and reverse DNS, MX record lookup |
| `traceroute(target)` | tracert wrapper |
| `arp_table()` | arp -a |
| `port_fwd_*` | Simple TCP port forwarding for pivoting |

### 7.5 Admin / System Manipulation

| Function | Description |
|---|---|
| `dump_lsass()` | Create a minidump of lsass.exe (requires SeDebugPrivilege) |
| `disable_firewall()` | netsh advfirewall set allprofiles state off |
| `disable_uac()` | Set EnableLUA registry value to 0 |
| `clear_logs()` | wevtutil cl Security/System/Application logs |
| `exclude_path()` / `exclude_ext()` | Add Defender exclusions |
| `enable_rdp()` | Enable Remote Desktop via registry and firewall rule |
| `add_user(user, pass)` | Create local user and add to Administrators group |
| `blue_screen()` | Force a BSOD via NtRaiseHardError or taskkill csrss |
| `disable_taskmgr` / `disable_cmd` | Set registry policies to disable Task Manager / Command Prompt |
| `shadow_list` / `shadow_delete` | Manage volume shadow copies (vssadmin) |
| `sys_persist` | Install persistence in HKLM Run key |
| `persist_wmi` | Create WMI event subscription for persistence |
| `safe_mode_persist` | Add persistence via Safe Mode registry keys |

### 7.6 Trolling & Disruption

| Function | Description |
|---|---|
| `tts_speak(text)` | Text-to-speech via SAPI.SpVoice (VBScript) |
| `type_text(text)` | Simulate keyboard input with SendKeys |
| `msgbox(title, text)` | Customizable popup message box |
| `wallpaper_url(url)` | Download image and set as wallpaper |
| `swap_mouse(enable)` | Swap left/right mouse buttons |
| `crazy_cursor(sec)` | Move cursor randomly for N seconds |
| `open_cd` / `close_cd` | Eject/retract CD tray via mciSendString |

### 7.7 Autodestroy

The `autodestroy()` function orchestrates complete self-removal:

1. Removes all persistence entries (HKCU, HKLM, scheduled tasks, startup VBS).
2. If admin, also removes system-level persistence.
3. Runs `cleanup()` to delete temporary files.
4. Creates a PowerShell script (`_gc.ps1`) that:
   - Waits for the parent process to exit.
   - Deletes both the current script and the persistent copy.
   - Deletes itself.
5. Sends a final message and terminates the victim process.

---

## 8. Listener Enhancements

- **Colored help:** Categorized and color-coded command list.
- **Session logging:** All commands and responses are logged to `session_logs/`.
- **Local command execution:** Prefix with `!` to run on attacker's machine.
- **File command detection:** Automatically recognizes commands that return a file and prompts for save location.

---

## 9. Protocol Specification (Detailed)

### 9.1 Packet Format

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                        Length (BE)                            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
|                         Nonce (8 bytes)                       |
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
|                    RC4-encrypted payload ...                  |
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

### 9.2 Key Derivation

```
RC4_Key = SHA-256(SHARED_SECRET || Nonce)
```

### 9.3 File Transfer State Machine (Victim)

```
[File command received]
        │
        ▼
[Generate file] ──error──→ [Send "[-] Error message"] ──→ [Done]
        │
        ▼
[Send status message] (e.g., "[+] Collecting...")
        │
        ▼
[Send "FILE_START"]
        │
        ▼
[Read 3KB chunk] ──→ [Base64 encode] ──→ [Send encrypted chunk]
        │                                     │
        └─────────────────────────────────────┘ (loop until EOF)
        │
        ▼
[Send "FILE_END"]
        │
        ▼
[Cleanup temp file]
```

---

## 10. Security Considerations

- Encryption provides strong confidentiality, but the shared secret is embedded in the binary.
- No forward secrecy – if the secret is compromised, all traffic can be decrypted.
- Anti-VM checks are basic and can be bypassed by advanced sandboxes.
- PowerShell scripts are written to disk (`kl.ps1`, `cm.ps1`, `sl.ps1`), which may trigger AV.
- Admin commands leave traces in Windows Event Logs (unless cleared).

---

## 11. Testing and Compatibility

- **Tested on:** Windows 10 (21H2, 22H2), Windows 11 (23H2), Windows Server 2019/2022.
- **Python versions:** 3.8, 3.9, 3.10, 3.11, 3.12.
- **PowerShell:** Requires version 3.0+.

---

## 12. Known Limitations

- `dump_lsass` may fail if not running as SYSTEM or with SeDebugPrivilege.
- `webcam_snap` depends on WIA or ffmpeg being available.
- `record_mic` requires a working microphone device.
- `steal` and `download_dir` have size limits to prevent memory exhaustion.

---

## 13. Future Roadmap

- Add reflective DLL injection for stealthier execution.
- Create a web-based C2 panel for multi-session management.
- Try to solve some of the limitations
- Multiplatoform versions.

---

*Document version: 3.5 – corresponds to the v3.5 release of the reverse shell.*
