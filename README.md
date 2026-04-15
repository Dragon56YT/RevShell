# 🔥 RevShell Project — Advanced Windows Reverse Shell
````
╔═══════════════════════════════════════════════════════════════════════╗
║                                                                       ║
║    ██████╗ ███████╗██╗   ██╗███████╗██╗  ██╗███████╗██╗      ██╗      ║
║    ██╔══██╗██╔════╝██║   ██║██╔════╝██║  ██║██╔════╝██║      ██║      ║
║    ██████╔╝█████╗  ██║   ██║███████╗███████║█████╗  ██║      ██║      ║
║    ██╔══██╗██╔══╝  ╚██╗ ██╔╝╚════██║██╔══██║██╔══╝  ██║      ██║      ║
║    ██║  ██║███████╗ ╚████╔╝ ███████║██║  ██║███████╗███████╗ ██████╗  ║
║    ╚═╝  ╚═╝╚══════╝  ╚═══╝  ╚══════╝╚═╝  ╚═╝╚══════╝╚══════╝ ╚═════╝  ║
║                                                                       ║
║                  Advanced Reverse Shell for Windows                   ║
║                                                                       ║
╚═══════════════════════════════════════════════════════════════════════╝
````

> ⚠️ **Disclaimer — Version 3.5 Documentation**
>
> The documentation for **v3.5** is currently **in progress**.
>
> It is not yet complete and translated.
>
> A finalized version will be published in the coming days!
>


## 📖 Overview

**RevShell** is a comprehensive educational project that demonstrates the evolution of a Windows reverse shell from a simple proof‑of‑concept to a fully‑featured post‑exploitation agent. The project is structured into three major versions, each building upon the previous one with increased capabilities, better stealth, and more advanced techniques.

This repository is intended **exclusively for cybersecurity education, authorized penetration testing, and defensive research**. All code is provided as‑is for learning purposes.

---

## 📁 Repository Structure
````
.
├── v1.0/
│ ├── README.md # User guide for v1.0
│ ├── TECHNICAL.md # Technical deep‑dive for v1.0
│ ├── listener.py # C2 listener (attacker side)
│ └── victim_win.py # Implant (victim side)
│
├── v2.0/
│ ├── README.md # User guide for v2.0
│ ├── TECHNICAL.md # Technical deep‑dive for v2.0
│ ├── listener.py # Enhanced C2 listener
│ ├── victim_win.py # Implant with 40+ commands
│ └── victim_win_ADMIN.py # Same as above + auto‑elevation
│
└── v3.5/
├── README.md # User guide for v3.5 (in progress)
├── TECHNICAL.md # Technical deep‑dive for v3.5 (in progress)
├── listener.py # Advanced listener (RC4 encryption)
├── victim_win.py # Full implant with 150+ commands
└── victim_win_ADMIN.py # Full implant + admin capabilities

````

---

## 🔄 Version Evolution

| Feature | v1.0 | v2.0 | v3.5 |
|---------|:----:|:----:|:----:|
| **Encryption** | XOR (single byte) | XOR (single byte) | **RC4 + nonce + SHA‑256** |
| **Persistence** | Registry only | Registry + Task + Startup | Registry + Task + Startup + WMI + SYSTEM |
| **Commands** | 8 | 40+ | **150+** |
| **File Transfer** | ✅ | ✅ | ✅ + directory download |
| **Keylogger** | ❌ | ✅ | ✅ |
| **Screenshot** | ❌ | ✅ | ✅ + screen recording |
| **Browser Stealer** | ❌ | ✅ | ✅ |
| **WiFi Passwords** | ❌ | ✅ | ✅ |
| **Privilege Escalation Checks** | ❌ | ✅ | ✅ |
| **Admin Commands** | ❌ | `disable_defender`, `dump_hashes` | +20 admin commands (RDP, UAC, firewall, BSOD, etc.) |
| **Anti‑VM / Sandbox** | ❌ | ❌ | ✅ |
| **Decoy GUI** | ❌ | ❌ | ✅ |
| **Beacon Jitter** | ❌ | ❌ | ✅ |
| **Port Forwarding** | ❌ | ❌ | ✅ |
| **Self‑Destruction** | ❌ | ❌ | ✅ (`autodestroy`) |
| **Auto‑Elevation (Admin)** | ❌ | ❌ (separate version) | ✅ (integrated) |

---

## 🎯 Intended Use

This project is designed for:

- **Cybersecurity students** learning about reverse shells, C2 communication, and post‑exploitation techniques.
- **Penetration testers** who need a flexible, well‑documented implant for **authorized** engagements.
- **Blue teams / Defenders** who want to understand attacker tools to build better detection rules.
- **CTF players** looking for a customizable reverse shell for Windows challenges.

---

## ⚖️ Legal Disclaimer (IMPORTANT — READ CAREFULLY)

> **This software is provided for educational and research purposes only.**

### 1. No Authorization = Illegal Use

Using this software to access, monitor, or control any computer system, network, or device **without explicit, written permission from the owner** is a violation of:

- **Computer Fraud and Abuse Act (CFAA)** — 18 U.S.C. § 1030 (United States)
- **General Data Protection Regulation (GDPR)** — EU Regulation 2016/679
- **Computer Misuse Act 1990** (United Kingdom)
- **Criminal Code of Canada** — Section 342.1 / 430
- **Cybercrime Act 2001** (Australia)
- **Information Technology Act 2000** (India)
- And similar laws in virtually every country around the world.

**Penalties may include:**
- Heavy fines (up to hundreds of thousands of dollars/euros)
- Imprisonment (up to 10‑20 years depending on jurisdiction)
- Permanent criminal record
- Civil lawsuits from affected parties

### 2. Authorized Use Only

You may **only** use this software in the following scenarios:

- On **your own personal systems** that you own and control.
- In **isolated laboratory environments** (virtual machines with no network access to production systems).
- As part of an **authorized penetration test** where you have a signed legal contract and explicit scope of work.
- For **academic research** within a controlled, supervised environment.

### 3. No Warranty

THIS SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT, OR OTHERWISE, ARISING FROM, OUT OF, OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

### 4. User Responsibility

By downloading, copying, installing, or using this software, **you agree that you are solely responsible for your actions**. The authors and contributors assume **zero liability** for any misuse, damage, or legal consequences resulting from the use of this software.

If you are unsure whether your intended use is legal, **consult a qualified attorney** before proceeding.

### 5. Educational Purpose Statement

The techniques demonstrated in this project (reverse shells, persistence, credential harvesting, privilege escalation) are **common knowledge in the cybersecurity field** and are documented here to:

- Educate defenders on attacker methodologies.
- Provide a reference implementation for students.
- Enable controlled testing of detection and response capabilities.

**Understanding how attacks work is essential for building effective defenses.** This project contributes to that goal by providing transparent, well‑commented code that can be studied and analyzed.

---

## 🔗 Quick Links per Version

### v1.0 — Basic Reverse Shell
- **Features:** XOR encryption, file upload/download, `steal` command, registry persistence.
- **Files:** [`v1.0/`](./v1.0/)
- **Documentation:** [README (v1.0)](./v1.0/README.md) | [TECHNICAL (v1.0)](./v1.0/TECHNICAL.md)

### v2.0 — Expanded Post‑Exploitation
- **Features:** +30 new commands, multi‑method persistence, keylogger, browser stealer, WiFi passwords, privesc checks.
- **Files:** [`v2.0/`](./v2.0/)
- **Documentation:** [README (v2.0)](./v2.0/README.md) | [TECHNICAL (v2.0)](./v2.0/TECHNICAL.md)
- **Admin Variant:** `victim_win_ADMIN.py` — same features + automatic UAC bypass (requests elevation on startup).

### v3.5 — Advanced C2 Agent
- **Features:** RC4 encryption with nonce, beacon jitter, anti‑VM, decoy GUI, 150+ commands, port forwarding, screen/mic recording, admin backdoors, self‑destruction.
- **Files:** [`v3.5/`](./v3.5/)
- **Documentation:** [README (v3.5)](./v3.5/README.md) | [TECHNICAL (v3.5)](./v3.5/TECHNICAL.md)
- **Admin Variant:** `victim_win_ADMIN.py` — full implant with integrated auto‑elevation and 20+ admin‑only commands.

---

## 🛠️ Basic Usage (All Versions)

### 1. Configure the Attacker IP

Edit the victim script (`victim_win.py`) and set:
```python
ATTACKER_IP = "your.ip.here"
2. Start the Listener (Attacker Machine)
````
````
python listener.py
3. Deploy the Victim Script (Target Machine)
````
````
python victim_win.py
Once connected, you will have a shell> prompt where you can type commands. Type help to see available commands for that version.
````
###📚 Learning Resources
- OWASP Reverse Shell Cheat Sheet

- MITRE ATT&CK — Command and Control

- Windows Internals — Persistence Mechanisms

- Python Socket Programming

## 📄 License

This work is licensed under the
**Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License**
(CC BY-NC-SA 4.0).

To view a copy of this license, visit
[https://creativecommons.org/licenses/by-nc-sa/4.0/](https://creativecommons.org/licenses/by-nc-sa/4.0/)
or see the [LICENSE](LICENSE) file included in this repository.

### Summary of Permissions

- ✅ **Share** — copy and redistribute the material in any medium or format.
- ✅ **Adapt** — remix, transform, and build upon the material.

### Under the Following Terms

- **Attribution** — You must give appropriate credit, provide a link to the license, and indicate if changes were made. You may do so in any reasonable manner, but not in any way that suggests the licensor endorses you or your use.
- **NonCommercial** — You may not use the material for **commercial purposes**. This includes selling the software, offering it as part of a paid service, or using it in any activity primarily intended for commercial advantage or monetary compensation.
- **ShareAlike** — If you remix, transform, or build upon the material, you must distribute your contributions under the **same license** as the original.

### Important Note

This license applies **only** to the code and documentation in this repository. It does **not** grant you permission to use this software in violation of any applicable laws. Unauthorized access to computer systems remains illegal regardless of the license.

**No additional restrictions** — You may not apply legal terms or technological measures that legally restrict others from doing anything the license permits.

###⭐ Acknowledgements
This project was created as an educational resource to help the cybersecurity community understand offensive techniques and improve defensive capabilities.

Remember: With great power comes great responsibility. Use this knowledge ethically and legally.

###📧 Contact
This project is maintained as an open educational resource. For questions, suggestions, or to report issues, please open an issue on the GitHub repository.

Do not contact the maintainers for help with illegal activities. Such requests will be ignored and reported.

RevShell Project — Made for education, not for crime.
