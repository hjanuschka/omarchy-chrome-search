#!/usr/bin/env python3
"""Native Messaging host and local CLI for the Omarchy Chrome Search plugin."""

import json
import os
from pathlib import Path
import select
import socket
import struct
import subprocess
import sys
import time


def socket_path():
    runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return Path(runtime) / "omarchy-chrome-search.sock"


def read_exact(size):
    data = bytearray()
    while len(data) < size:
        chunk = os.read(sys.stdin.fileno(), size - len(data))
        if not chunk:
            raise EOFError
        data.extend(chunk)
    return bytes(data)


def read_native():
    size = struct.unpack("=I", read_exact(4))[0]
    if size > 8 * 1024 * 1024:
        raise ValueError("Native message too large")
    return json.loads(read_exact(size))


def write_native(message):
    data = json.dumps(message).encode()
    sys.stdout.buffer.write(struct.pack("=I", len(data)) + data)
    sys.stdout.buffer.flush()


def serve():
    path = socket_path()
    if path.exists():
        with socket.socket(socket.AF_UNIX) as probe:
            try:
                probe.connect(str(path))
            except OSError:
                path.unlink()
            else:
                raise RuntimeError("Bridge is already running")
    server = socket.socket(socket.AF_UNIX)
    old_umask = os.umask(0o077)
    try:
        server.bind(str(path))
    finally:
        os.umask(old_umask)
    server.listen()
    pending = {}
    next_id = 0
    try:
        while True:
            readable, _, _ = select.select([server, sys.stdin], [], [], 1)
            if server in readable:
                client, _ = server.accept()
                client.settimeout(2)
                try:
                    request = json.loads(client.recv(65536))
                    next_id += 1
                    request["id"] = next_id
                    pending[next_id] = (client, time.monotonic())
                    write_native(request)
                except (OSError, ValueError):
                    client.close()
            if sys.stdin in readable:
                try:
                    response = read_native()
                except EOFError:
                    break
                entry = pending.pop(response.get("id"), None)
                if entry:
                    client, _ = entry
                    try:
                        client.sendall(json.dumps(response).encode())
                    finally:
                        client.close()
            for request_id, (client, started) in list(pending.items()):
                if time.monotonic() - started > 5:
                    pending.pop(request_id)
                    client.close()
    finally:
        for client, _ in pending.values():
            client.close()
        server.close()
        path.unlink(missing_ok=True)


def add_workspaces(tabs):
    try:
        clients = json.loads(subprocess.check_output(["hyprctl", "-j", "clients"], text=True))
    except (OSError, subprocess.CalledProcessError, ValueError):
        return tabs
    active = {tab["windowId"]: tab["title"] for tab in tabs if tab["active"] and tab["title"]}
    for window_id, title in active.items():
        matches = [client for client in clients
                   if client.get("class", "").startswith(("google-chrome", "chromium", "chrome-"))
                   and (client.get("title") == title or client.get("title", "").startswith(title + " - "))]
        if len(matches) == 1:
            workspace = matches[0]["workspace"]["name"]
            for tab in tabs:
                if tab["windowId"] == window_id:
                    tab["workspace"] = workspace
    return tabs


def call(action, **kwargs):
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(7)
        client.connect(str(socket_path()))
        client.sendall(json.dumps({"action": action, **kwargs}).encode())
        chunks = []
        while chunk := client.recv(65536):
            chunks.append(chunk)
        response = json.loads(b"".join(chunks))
    if response.get("error"):
        raise RuntimeError(response["error"])
    return response.get("result")


if __name__ == "__main__":
    try:
        if len(sys.argv) == 1 or sys.argv[1].startswith("chrome-extension://"):
            serve()
        elif sys.argv[1:] == ["list"]:
            print(json.dumps(add_workspaces(call("list"))))
        elif len(sys.argv) == 3 and sys.argv[1] == "activate":
            print(json.dumps(call("activate", tabId=int(sys.argv[2]))))
        elif len(sys.argv) == 3 and sys.argv[1] == "search":
            print(json.dumps(call("search", text=sys.argv[2])))
        elif len(sys.argv) == 3 and sys.argv[1] == "summon":
            from summon import toggle
            toggle(int(sys.argv[2]))
        elif sys.argv[1:] == ["restore"]:
            from summon import restore_current
            restore_current()
        elif sys.argv[1:] == ["launcher"]:
            from summon import STATE, restore_current
            if STATE.exists():
                restore_current()
                subprocess.run(["omarchy-shell", "shell", "hide", "hjanuschka.chrome-search"], check=False)
            else:
                subprocess.run(["omarchy-shell", "shell", "toggle", "hjanuschka.chrome-search", "{}"], check=True)
        else:
            raise ValueError("Usage: bridge.py [list | activate TAB_ID | summon TAB_ID | restore | launcher | search TEXT]")
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        if len(sys.argv) > 1 and sys.argv[1] in ("summon", "restore", "launcher"):
            subprocess.run(["notify-send", "Chrome Search", str(error)], check=False)
        sys.exit(1)
