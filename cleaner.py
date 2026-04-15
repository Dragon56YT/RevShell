#!/usr/bin/env python3
# cleaner.py v3.5 - Universal Detection & Remediation Tool (Incident Response)
# Detects and removes artifacts (IoCs) created by RevShell v1.0, v2.0, and v3.5
# Works universally across all versions of the implant

import os
import sys
import winreg
import subprocess
import ctypes
import shutil
import tempfile
import glob

def is_admin() -> bool:
    """Check if the script is running with Administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False

# ===================== INDICATORS OF COMPROMISE (IoCs) =====================
# These are the artifacts left behind by any version of RevShell (v1.0, v2.0, v3.5)

APPDATA = os.environ.get('APPDATA', '')
LOCAL_APPDATA = os.environ.get('LOCALAPPDATA', '')
USER_PROFILE = os.environ.get('USERPROFILE', '')
PERSIST_SCRIPT = os.path.join(APPDATA, "svchost_update.pyw")  # v2.0+ also used in v1.0 as WindowsUpdate.py
PERSIST_KEY_HKCU = r"Software\Microsoft\Windows\CurrentVersion\Run"
PERSIST_KEY_HKLM = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
PERSIST_NAME = "WindowsUpdateService"
PERSIST_TASK_NAME = "WindowsUpdateCheck"
PERSIST_TASK_SYSTEM = "WindowsUpdateCheck_System"
STARTUP_VBS = os.path.join(APPDATA, "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "WindowsUpdate.vbs")

TEMP = tempfile.gettempdir()

# Known temporary files created by the malware (all versions)
TEMP_FILE_PATTERNS = [
    "cm.ps1", "clipmon.txt",           # Clipboard monitor (v3.5)
    "kl.ps1", "kl.txt",                # Keylogger (v2.0, v3.5)
    "sl.ps1",                           # Screenshot loop (v3.5)
    "_gc.ps1",                          # Autodestroy killer script (v3.5)
    "sc.png",                           # Screenshot (v2.0, v3.5)
    "mic_rec.wav",                      # Mic recording (v3.5)
    "webcam.jpg",                       # Webcam snap (v3.5)
    "lsass.dmp",                        # LSASS dump (v3.5)
    "sam.save", "system.save", "security.save",  # Registry hive dumps (v2.0, v3.5)
    "sysinfo.tar", "exfil.tar",         # Exfiltration archives (v2.0, v3.5)
    "browsers.zip", "record_screen.zip",# Browser/screen data (v2.0, v3.5)
    "scrloop.zip",                      # Screenshot loop dump (v3.5)
    "tts_*.vbs",                        # Text-to-speech scripts (v3.5)
    "wp_*",                             # Wallpaper temp downloads (v3.5)
]

# Known temporary directories created by the malware
TEMP_DIR_PATTERNS = [
    "si_*",     # sysinfo temp dirs (v2.0, v3.5)
    "br_*",     # browser temp dirs (v2.0, v3.5)
    "ex_*",     # exfil temp dirs (v2.0, v3.5)
    "rec_*",    # screen recording temp dirs (v3.5)
    "scrloop",  # screenshot loop dir (v3.5)
    "dl_*",     # downloaded files (v3.5)
    "port_scan_*",
]

# Known ZIP archives created during exfiltration
TEMP_ZIP_PATTERNS = [
    "steal_*.zip",   # User files archive (all versions)
    "dir_*.zip",     # Directory download archive (v3.5)
]

# Admin-level registry modifications that the malware may have made (v3.5 ADMIN)
ADMIN_REGISTRY_IOCS = [
    {
        "hive": winreg.HKEY_LOCAL_MACHINE,
        "path": r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList",
        "description": "User accounts hidden from login screen",
    },
    {
        "hive": winreg.HKEY_LOCAL_MACHINE,
        "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System",
        "values": {"EnableLUA": 1},  # Should be 1 (enabled)
        "description": "UAC potentially disabled",
    },
    {
        "hive": winreg.HKEY_CURRENT_USER,
        "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System",
        "values": {"DisableTaskMgr": None},  # Should not exist
        "description": "Task Manager disabled via registry",
    },
    {
        "hive": winreg.HKEY_CURRENT_USER,
        "path": r"SOFTWARE\Policies\Microsoft\Windows\System",
        "values": {"DisableCMD": None},  # Should not exist
        "description": "CMD disabled via registry",
    },
]

# WMI persistence names (v3.5 ADMIN)
WMI_FILTER_NAME = "WinUpdateFilter"
WMI_CONSUMER_NAME = "WinUpdateConsumer"


class MalwareCleaner:
    """Main class that performs detection and remediation of RevShell artifacts."""
    
    def __init__(self):
        self.findings = []  # List to store all detected IoCs
        
    # ===================== DETECTION CHECKS =====================
    
    def check_registry_hkcu(self):
        """Check HKCU Run key for persistence (all versions)."""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, PERSIST_KEY_HKCU, 0, winreg.KEY_READ)
            val, _ = winreg.QueryValueEx(key, PERSIST_NAME)
            winreg.CloseKey(key)
            self.findings.append({
                "type": "Registry HKCU (Run Key)",
                "description": f"Persistence in registry: HKCU\\{PERSIST_KEY_HKCU} → {PERSIST_NAME}",
                "value": val,
                "severity": "HIGH",
                "remediation": self.clean_registry_hkcu
            })
        except FileNotFoundError:
            pass

    def check_registry_hklm(self):
        """Check HKLM Run key for persistence (v3.5 ADMIN). Requires admin privileges."""
        if not is_admin():
            return
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, PERSIST_KEY_HKLM, 0, winreg.KEY_READ)
            val, _ = winreg.QueryValueEx(key, PERSIST_NAME)
            winreg.CloseKey(key)
            self.findings.append({
                "type": "Registry HKLM (Run Key)",
                "description": f"Persistence in registry: HKLM\\{PERSIST_KEY_HKLM} → {PERSIST_NAME}",
                "value": val,
                "severity": "HIGH",
                "remediation": self.clean_registry_hklm
            })
        except (FileNotFoundError, PermissionError):
            pass

    def check_task(self):
        """Check for malicious scheduled tasks (v2.0, v3.5)."""
        for task_name in [PERSIST_TASK_NAME, PERSIST_TASK_SYSTEM]:
            try:
                output = subprocess.check_output(
                    f'schtasks /query /tn "{task_name}" /fo LIST',
                    shell=True, stderr=subprocess.DEVNULL, text=True
                )
                if task_name in output:
                    self.findings.append({
                        "type": "Scheduled Task",
                        "description": f"Malicious scheduled task found: {task_name}",
                        "value": task_name,
                        "severity": "HIGH",
                        "remediation": lambda tn=task_name: self.clean_task(tn)
                    })
            except subprocess.CalledProcessError:
                pass

    def check_startup(self):
        """Check Startup folder for VBS persistence (v2.0, v3.5)."""
        if os.path.exists(STARTUP_VBS):
            self.findings.append({
                "type": "Startup Folder",
                "description": "VBS persistence script in Startup folder.",
                "value": STARTUP_VBS,
                "severity": "HIGH",
                "remediation": lambda: self.delete_file(STARTUP_VBS)
            })

    def check_payload(self):
        """Check for the main payload script (all versions)."""
        if os.path.exists(PERSIST_SCRIPT):
            self.findings.append({
                "type": "Main Payload",
                "description": "Payload script hidden in AppData.",
                "value": PERSIST_SCRIPT,
                "severity": "CRITICAL",
                "remediation": lambda: self.delete_file(PERSIST_SCRIPT)
            })
        # Also check v1.0 naming convention
        v1_script = os.path.join(APPDATA, "WindowsUpdate.py")
        if os.path.exists(v1_script):
            self.findings.append({
                "type": "Main Payload (v1.0)",
                "description": "Payload script hidden in AppData (v1.0 naming).",
                "value": v1_script,
                "severity": "CRITICAL",
                "remediation": lambda: self.delete_file(v1_script)
            })

    def check_temp_files(self):
        """Check for temporary files and directories created by the malware (all versions)."""
        # Individual files
        for pattern in TEMP_FILE_PATTERNS:
            for path in glob.glob(os.path.join(TEMP, pattern)):
                if os.path.exists(path):
                    self.findings.append({
                        "type": "Malicious Temporary File",
                        "description": f"Trace of malicious activity: {os.path.basename(path)}",
                        "value": path,
                        "severity": "MEDIUM",
                        "remediation": lambda p=path: self.delete_file(p)
                    })

        # Directories
        for pattern in TEMP_DIR_PATTERNS:
            for path in glob.glob(os.path.join(TEMP, pattern)):
                if os.path.isdir(path):
                    self.findings.append({
                        "type": "Malicious Temporary Directory",
                        "description": f"Directory of collected data: {os.path.basename(path)}",
                        "value": path,
                        "severity": "MEDIUM",
                        "remediation": lambda p=path: self.delete_dir(p)
                    })

        # ZIP patterns
        for pattern in TEMP_ZIP_PATTERNS:
            for path in glob.glob(os.path.join(TEMP, pattern)):
                if os.path.exists(path):
                    self.findings.append({
                        "type": "Exfiltration ZIP Archive",
                        "description": f"Exfiltrated data archive: {os.path.basename(path)}",
                        "value": path,
                        "severity": "HIGH",
                        "remediation": lambda p=path: self.delete_file(p)
                    })

    def check_process(self):
        """Check for running malware processes (all versions)."""
        try:
            # Python processes running the payload
            output = subprocess.check_output(
                'wmic process where "Name=\'python.exe\' or Name=\'pythonw.exe\'" get ProcessId,CommandLine',
                shell=True, stderr=subprocess.DEVNULL, text=True
            )
            for line in output.splitlines():
                if any(name in line for name in ["svchost_update.pyw", "victim_win.pyw", "victim_win_ADMIN.pyw", "WindowsUpdate.py"]):
                    parts = line.strip().split()
                    pid = parts[-1]
                    self.findings.append({
                        "type": "Active Process in Memory",
                        "description": f"Malware running in background (PID: {pid})",
                        "value": line.strip(),
                        "severity": "CRITICAL",
                        "remediation": lambda pid=pid: self.kill_process(pid)
                    })
            
            # PowerShell sub-processes (keylogger, clipboard, scrloop) - v2.0, v3.5
            ps_output = subprocess.check_output(
                'wmic process where "Name=\'powershell.exe\'" get ProcessId,CommandLine',
                shell=True, stderr=subprocess.DEVNULL, text=True
            )
            malicious_scripts = ["cm.ps1", "kl.ps1", "sl.ps1", "_gc.ps1"]
            for line in ps_output.splitlines():
                for script in malicious_scripts:
                    if script in line:
                        parts = line.strip().split()
                        pid = parts[-1]
                        script_names = {
                            "cm.ps1": "Clipboard monitor",
                            "kl.ps1": "Keylogger",
                            "sl.ps1": "Screenshot loop",
                            "_gc.ps1": "Self-destruction script",
                        }
                        desc = script_names.get(script, "Malicious script")
                        self.findings.append({
                            "type": "Malicious Sub-Process",
                            "description": f"{desc} active (PID: {pid})",
                            "value": line.strip(),
                            "severity": "HIGH",
                            "remediation": lambda pid=pid: self.kill_process(pid)
                        })
        except subprocess.CalledProcessError:
            pass

    def check_wmi_persistence(self):
        """Check for WMI event subscription persistence (v3.5 ADMIN). Requires admin."""
        if not is_admin():
            return
        try:
            output = subprocess.check_output(
                f'powershell -NoProfile -Command "Get-WMIObject -NS root\\subscription -Class __EventFilter | Where{{$_.Name -eq \'{WMI_FILTER_NAME}\'}} | Select Name | FL"',
                shell=True, stderr=subprocess.DEVNULL, text=True
            )
            if WMI_FILTER_NAME in output:
                self.findings.append({
                    "type": "WMI Persistence",
                    "description": f"WMI event subscription persistence detected: {WMI_FILTER_NAME}",
                    "value": WMI_FILTER_NAME,
                    "severity": "CRITICAL",
                    "remediation": self.clean_wmi
                })
        except subprocess.CalledProcessError:
            pass

    def check_defender_exclusions(self):
        """Check for suspicious Defender exclusions (v2.0, v3.5 ADMIN)."""
        if not is_admin():
            return
        try:
            output = subprocess.check_output(
                'powershell -NoProfile -Command "Get-MpPreference | Select -Expand ExclusionPath -EA SilentlyContinue"',
                shell=True, stderr=subprocess.DEVNULL, text=True
            )
            suspicious = [TEMP, APPDATA]
            for line in output.splitlines():
                line = line.strip()
                if line and any(s.lower() in line.lower() for s in suspicious):
                    self.findings.append({
                        "type": "Suspicious Defender Exclusion",
                        "description": f"Path excluded from Defender: {line}",
                        "value": line,
                        "severity": "HIGH",
                        "remediation": lambda p=line: self.remove_defender_exclusion(p)
                    })
        except subprocess.CalledProcessError:
            pass

    def check_admin_registry_mods(self):
        """Check for admin-level registry modifications (v3.5 ADMIN)."""
        if not is_admin():
            return
        # Check UAC status
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System",
                0, winreg.KEY_READ
            )
            val, _ = winreg.QueryValueEx(key, "EnableLUA")
            winreg.CloseKey(key)
            if val == 0:
                self.findings.append({
                    "type": "UAC Disabled",
                    "description": "User Account Control (UAC) has been disabled via registry.",
                    "value": "EnableLUA = 0",
                    "severity": "CRITICAL",
                    "remediation": self.fix_uac
                })
        except (FileNotFoundError, PermissionError):
            pass

        # Check Task Manager disabled
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System",
                0, winreg.KEY_READ
            )
            val, _ = winreg.QueryValueEx(key, "DisableTaskMgr")
            winreg.CloseKey(key)
            if val == 1:
                self.findings.append({
                    "type": "Task Manager Disabled",
                    "description": "Task Manager has been disabled via registry.",
                    "value": "DisableTaskMgr = 1",
                    "severity": "HIGH",
                    "remediation": self.fix_taskmgr
                })
        except (FileNotFoundError, PermissionError):
            pass

        # Check CMD disabled
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"SOFTWARE\Policies\Microsoft\Windows\System",
                0, winreg.KEY_READ
            )
            val, _ = winreg.QueryValueEx(key, "DisableCMD")
            winreg.CloseKey(key)
            if val == 1:
                self.findings.append({
                    "type": "CMD Disabled",
                    "description": "Command Prompt (CMD) has been disabled via registry.",
                    "value": "DisableCMD = 1",
                    "severity": "HIGH",
                    "remediation": self.fix_cmd
                })
        except (FileNotFoundError, PermissionError):
            pass

    def check_hidden_users(self):
        """Check for hidden users in the login screen (v3.5 ADMIN)."""
        if not is_admin():
            return
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList",
                0, winreg.KEY_READ
            )
            i = 0
            while True:
                try:
                    name, val, _ = winreg.EnumValue(key, i)
                    if val == 0:
                        self.findings.append({
                            "type": "Hidden User",
                            "description": f"User '{name}' hidden from login screen.",
                            "value": name,
                            "severity": "CRITICAL",
                            "remediation": lambda n=name: self.unhide_user(n)
                        })
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        except (FileNotFoundError, PermissionError):
            pass

    def check_rdp_enabled(self):
        """Check if RDP was silently enabled (v3.5 ADMIN)."""
        if not is_admin():
            return
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\Terminal Server",
                0, winreg.KEY_READ
            )
            val, _ = winreg.QueryValueEx(key, "fDenyTSConnections")
            winreg.CloseKey(key)
            if val == 0:
                # RDP is enabled - could be legitimate, so just note it
                self.findings.append({
                    "type": "RDP Enabled",
                    "description": "Remote Desktop (RDP) is enabled. Verify if this is intentional.",
                    "value": "fDenyTSConnections = 0",
                    "severity": "MEDIUM",
                    "remediation": None  # Manual review needed
                })
        except (FileNotFoundError, PermissionError):
            pass

    # ===================== REMEDIATION FUNCTIONS =====================
    
    def clean_registry_hkcu(self):
        """Remove HKCU Run persistence entry."""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, PERSIST_KEY_HKCU, 0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(key, PERSIST_NAME)
            winreg.CloseKey(key)
            print("  [+] HKCU key successfully removed.")
        except Exception as e:
            print(f"  [-] Error: {e}")

    def clean_registry_hklm(self):
        """Remove HKLM Run persistence entry."""
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, PERSIST_KEY_HKLM, 0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(key, PERSIST_NAME)
            winreg.CloseKey(key)
            print("  [+] HKLM key successfully removed.")
        except Exception as e:
            print(f"  [-] Error: {e}")

    def clean_task(self, task_name: str):
        """Delete a scheduled task by name."""
        try:
            subprocess.run(f'schtasks /delete /tn "{task_name}" /f', shell=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"  [+] Task '{task_name}' successfully deleted.")
        except Exception as e:
            print(f"  [-] Error: {e}")

    def clean_wmi(self):
        """Remove WMI persistence subscription."""
        try:
            ps = f'''$ErrorActionPreference = 'SilentlyContinue'
Get-WMIObject -NS root\\subscription -Class __EventFilter | Where{{$_.Name -eq '{WMI_FILTER_NAME}'}} | Remove-WmiObject
Get-WMIObject -NS root\\subscription -Class CommandLineEventConsumer | Where{{$_.Name -eq '{WMI_CONSUMER_NAME}'}} | Remove-WmiObject
Get-WMIObject -NS root\\subscription -Class __FilterToConsumerBinding | Where{{$_.Filter -like '*{WMI_FILTER_NAME}*'}} | Remove-WmiObject
'''
            subprocess.run(
                ['powershell', '-NoProfile', '-Command', ps],
                capture_output=True, timeout=15
            )
            print("  [+] WMI persistence removed.")
        except Exception as e:
            print(f"  [-] Error removing WMI: {e}")

    def delete_file(self, path: str):
        """Delete a file if it exists."""
        try:
            if os.path.exists(path):
                os.remove(path)
                print(f"  [+] File deleted: {path}")
        except Exception as e:
            print(f"  [-] Error deleting {path}: {e}")

    def delete_dir(self, path: str):
        """Delete a directory and all its contents."""
        try:
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
                print(f"  [+] Directory deleted: {path}")
        except Exception as e:
            print(f"  [-] Error deleting {path}: {e}")

    def kill_process(self, pid: str):
        """Forcefully terminate a process by PID."""
        try:
            subprocess.run(f'taskkill /PID {pid} /F', shell=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"  [+] Process {pid} terminated.")
        except Exception as e:
            print(f"  [-] Error terminating process {pid}: {e}")

    def remove_defender_exclusion(self, path: str):
        """Remove a path from Windows Defender exclusions."""
        try:
            subprocess.run(
                ['powershell', '-NoProfile', '-Command',
                 f'Remove-MpPreference -ExclusionPath "{path}" -EA SilentlyContinue'],
                capture_output=True, timeout=15
            )
            print(f"  [+] Defender exclusion removed: {path}")
        except Exception as e:
            print(f"  [-] Error: {e}")

    def fix_uac(self):
        """Re-enable UAC by setting EnableLUA = 1."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System",
                0, winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(key, "EnableLUA", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)
            print("  [+] UAC re-enabled (EnableLUA=1). Reboot required.")
        except Exception as e:
            print(f"  [-] Error: {e}")

    def fix_taskmgr(self):
        """Re-enable Task Manager by deleting the DisableTaskMgr registry value."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System",
                0, winreg.KEY_SET_VALUE
            )
            winreg.DeleteValue(key, "DisableTaskMgr")
            winreg.CloseKey(key)
            print("  [+] Task Manager re-enabled.")
        except Exception as e:
            print(f"  [-] Error: {e}")

    def fix_cmd(self):
        """Re-enable CMD by deleting the DisableCMD registry value."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"SOFTWARE\Policies\Microsoft\Windows\System",
                0, winreg.KEY_SET_VALUE
            )
            winreg.DeleteValue(key, "DisableCMD")
            winreg.CloseKey(key)
            print("  [+] CMD re-enabled.")
        except Exception as e:
            print(f"  [-] Error: {e}")

    def unhide_user(self, username: str):
        """Unhide a user account from the login screen."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList",
                0, winreg.KEY_SET_VALUE
            )
            winreg.DeleteValue(key, username)
            winreg.CloseKey(key)
            print(f"  [+] User '{username}' unhidden.")
        except Exception as e:
            print(f"  [-] Error: {e}")

    # ===================== MAIN FLOW =====================
    
    def run_scan(self):
        """Perform a full system scan for RevShell IoCs."""
        print("[*] Starting scan for Indicators of Compromise (IoCs) v3.0...\n")
        
        # 1. Processes first (to prevent regeneration of persistence)
        print("  [~] Searching for malicious processes...")
        self.check_process()

        # 2. Persistence mechanisms
        print("  [~] Checking persistence mechanisms...")
        self.check_registry_hkcu()
        self.check_registry_hklm()
        self.check_task()
        self.check_startup()
        self.check_payload()
        self.check_wmi_persistence()

        # 3. Temporary files
        print("  [~] Searching for malicious temporary files...")
        self.check_temp_files()

        # 4. System configuration changes (ADMIN only)
        if is_admin():
            print("  [~] Checking system modifications (admin)...")
            self.check_admin_registry_mods()
            self.check_hidden_users()
            self.check_defender_exclusions()
            self.check_rdp_enabled()
        else:
            print("  [!] Without admin privileges: some checks skipped.")

        print("")

        if not self.findings:
            print("[+] ✅ The system appears to be CLEAN. No traces of the Reverse Shell were found.")
            return

        # Classify by severity
        critical = [f for f in self.findings if f.get("severity") == "CRITICAL"]
        high = [f for f in self.findings if f.get("severity") == "HIGH"]
        medium = [f for f in self.findings if f.get("severity") == "MEDIUM"]

        print(f"[!] ⚠️  WARNING: {len(self.findings)} malicious artifacts found.\n")
        if critical:
            print(f"    🔴 CRITICAL: {len(critical)}")
        if high:
            print(f"    🟠 HIGH:     {len(high)}")
        if medium:
            print(f"    🟡 MEDIUM:   {len(medium)}")

        print("\n" + "=" * 60)
        print("          INFECTION REPORT")
        print("=" * 60)
        
        for i, finding in enumerate(self.findings, 1):
            sev_icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡"}.get(finding.get("severity", ""), "⚪")
            print(f"\n{i}. [{sev_icon} {finding.get('severity', 'N/A')}] {finding['type']}")
            print(f"   Detail: {finding['description']}")
            print(f"   Trace:  {finding['value']}")

        print("\n" + "=" * 60)
        print("⚠️  THREAT STATUS: SYSTEM IS COMPROMISED")
        print("=" * 60)
        print("An external attacker may have control of this machine and could:")
        print(" - Execute commands remotely (Reverse Shell).")
        print(" - Track your keyboard (Keylogger) and clipboard.")
        print(" - Steal personal files, cookies, and saved passwords.")
        print(" - Capture screen, webcam, and microphone.")
        print(" - Have created hidden users or enabled RDP.")
        print(" - Have disabled Defender, UAC, Firewall, or Task Manager.\n")

        ans = input("Do you want to attempt to clean and disinfect the system now? (y/N): ").strip().lower()
        if ans == 'y':
            print("\n[*] Starting remediation process...\n")
            
            # Order: processes → persistence → files → configuration
            phases = [
                ("Active Process in Memory", "Malicious Sub-Process"),
                ("Registry HKCU (Run Key)", "Registry HKLM (Run Key)", "Scheduled Task",
                 "Startup Folder", "Main Payload", "Main Payload (v1.0)", "WMI Persistence"),
                ("Malicious Temporary File", "Malicious Temporary Directory",
                 "Exfiltration ZIP Archive"),
                ("UAC Disabled", "Task Manager Disabled", "CMD Disabled",
                 "Hidden User", "Suspicious Defender Exclusion"),
            ]
            phase_names = [
                "Neutralizing active processes",
                "Removing persistence mechanisms",
                "Cleaning temporary files",
                "Restoring system configuration",
            ]

            for phase_idx, phase_types in enumerate(phases):
                phase_findings = [f for f in self.findings if f["type"] in phase_types and f.get("remediation")]
                if phase_findings:
                    print(f"  ── {phase_names[phase_idx]} ──")
                    for finding in phase_findings:
                        print(f"  [*] {finding['type']}...")
                        finding['remediation']()
                    print("")

            # Handle findings with no remediation (manual review)
            manual = [f for f in self.findings if f.get("remediation") is None]
            if manual:
                print("  ── Require manual review ──")
                for f in manual:
                    print(f"  [?] {f['type']}: {f['description']}")

            print("\n[+] ✅ Cleanup completed successfully.")
            print("[*] Post-cleanup recommendations:")
            print("    1. Run a full antivirus scan.")
            print("    2. Change ALL important passwords.")
            print("    3. Check for unknown users (net user).")
            print("    4. Verify firewall is active (netsh advfirewall show allprofiles).")
            print("    5. Check that Defender is active (Get-MpComputerStatus).")
            print("    6. Reboot the system to ensure all changes take effect.")
        else:
            print("\n[-] Cleanup cancelled by user. The system REMAINS INFECTED.")

def run_as_admin():
    """Relaunch the script requesting Administrator privileges (UAC)."""
    print("[*] Requesting Administrator privileges via UAC...")
    try:
        script_path = os.path.abspath(sys.argv[0])
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script_path}" {params}', None, 1)
        sys.exit(0)
    except Exception as e:
        print(f"[-] Skipping privilege escalation or an error occurred: {e}")
        print("    Continuing with normal privileges...\n")

if __name__ == "__main__":
    # Set window title
    os.system("title EDR Scanner v3.0" if os.name == "nt" else "")
    
    print("=" * 60)
    print("    System Scanner & Remediator (EDR Demo) v3.0     ")
    print("=" * 60)
    print()
    
    if not is_admin():
        run_as_admin()
    
    try:
        scanner = MalwareCleaner()
        scanner.run_scan()
    except Exception as e:
        print(f"\n[-] Critical error running scanner: {e}")
        
    print("\n" + "=" * 60)
    input("  Press ENTER to exit and close this window...")
