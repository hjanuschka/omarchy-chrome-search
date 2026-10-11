"""Summon a Chrome window without changing its original tiling slot."""

import json
import os
from pathlib import Path
import subprocess
import time

from bridge import call

LOCKER = "special:chrome-search"
SLOT_TITLE = "Omarchy Chrome Search Slot"
STATE = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "omarchy-chrome-search-window.json"
PLUGIN = "hjanuschka.chrome-search"


def hypr(*args):
    return subprocess.check_output(["hyprctl", *args], text=True).strip()


def snapshot(name):
    return json.loads(hypr("-j", name))


def dispatch(command):
    result = hypr("dispatch", command)
    if result != "ok":
        raise RuntimeError(f"Hyprland: {result}")


def plugin(method):
    result = subprocess.check_output(
        ["omarchy-shell", "shell", "call", PLUGIN, method, ""], text=True).strip()
    if result != "ok":
        raise RuntimeError(f"Omarchy shell: {result}")


def window(address):
    return next((w for w in snapshot("clients") if w["address"] == address), None)


def sel(address):
    return f'window = "address:{address}"'


def focus(address):
    dispatch(f'hl.dsp.focus({{ {sel(address)} }})')


def move(address, workspace):
    dispatch(f'hl.dsp.window.move({{ workspace = "{workspace}", follow = false, {sel(address)} }})')


def return_to(monitor, address=None):
    if not any(m["name"] == monitor["name"] for m in snapshot("monitors")):
        return
    dispatch(f'hl.dsp.focus({{ monitor = "{monitor["name"]}" }})')
    workspace = monitor["activeWorkspace"]
    target = str(workspace["id"]) if workspace["id"] > 0 else "name:" + workspace["name"]
    dispatch(f'hl.dsp.focus({{ workspace = "{target}" }})')
    if address:
        previous = window(address)
        if previous and previous["workspace"]["name"] == workspace["name"]:
            focus(address)


def slot():
    return next((w for w in snapshot("clients") if w["title"] == SLOT_TITLE), None)


def wait_for(predicate):
    for _ in range(50):
        result = predicate()
        if result:
            return result
        time.sleep(0.1)
    raise RuntimeError("Timed out waiting for a window")


def active_chrome(title):
    def matched():
        win = snapshot("activewindow")
        if win.get("class") in ("google-chrome", "chromium") and (
            win.get("title") == title or win.get("title", "").startswith(title + " - ")
        ):
            return win
        return None
    return wait_for(matched)


def geometry(workspace):
    return {w["address"]: [w["at"], w["size"]]
            for w in snapshot("clients") if w["workspace"]["name"] == workspace and not w["floating"]}


def restore(state):
    current = next(m for m in snapshot("monitors") if m["focused"])
    destination = state.get("originMonitor", current)
    chrome = window(state["address"])
    placeholder = slot() if state["tiled"] else None
    if not chrome:
        if placeholder:
            plugin("hideSlot")
        STATE.unlink(missing_ok=True)
        return_to(destination, state.get("originAddress"))
        return
    if chrome["workspace"]["name"] != LOCKER:
        raise RuntimeError("Chrome window was moved outside the summon workspace")
    if state["tiled"] and (
        not placeholder or placeholder["workspace"]["name"] != state["workspace"]
    ):
        raise RuntimeError("Original tiling slot is missing; no window was moved")

    expected = geometry(state["workspace"]) if state["tiled"] else {}
    monitor = next((m for m in snapshot("monitors") if m["specialWorkspace"]["name"] == LOCKER), None)
    try:
        if monitor:
            dispatch(f'hl.dsp.focus({{ monitor = "{monitor["name"]}" }})')
            dispatch('hl.dsp.workspace.toggle_special("chrome-search")')

        address = state["address"]
        move(address, state["workspace"])
        if state["tiled"]:
            dispatch(f'hl.dsp.window.float({{ action = "disable", {sel(address)} }})')
            focus(address)
            dispatch(f'hl.dsp.window.swap({{ target = "address:{placeholder["address"]}" }})')
            plugin("hideSlot")
            actual = geometry(state["workspace"])
            STATE.unlink(missing_ok=True)
            if actual.get(address) != expected.get(placeholder["address"]) or any(
                actual.get(k) != v for k, v in expected.items() if k != placeholder["address"]
            ):
                raise RuntimeError("Tiling layout changed while Chrome was summoned")
        else:
            width, height = state["size"]
            x, y = state["at"]
            dispatch(f'hl.dsp.window.resize({{ x = {width}, y = {height}, {sel(address)} }})')
            dispatch(f'hl.dsp.window.move({{ x = {x}, y = {y}, {sel(address)} }})')
        STATE.unlink(missing_ok=True)
    finally:
        try:
            previous_tab_id = state.get("previousTabId")
            if previous_tab_id is not None and any(
                t["id"] == previous_tab_id and t["windowId"] == state["windowId"]
                for t in call("list")
            ):
                call("activate", tabId=previous_tab_id)
        finally:
            return_to(destination, state.get("originAddress"))


def restore_current():
    if STATE.exists():
        restore(json.loads(STATE.read_text()))


def toggle(tab_id):
    tabs = call("list")
    tab = next((t for t in tabs if t["id"] == tab_id), None)
    if tab is None:
        raise RuntimeError("Tab no longer exists")
    previous = json.loads(STATE.read_text()) if STATE.exists() else None
    if previous:
        restore(previous)
        if previous["windowId"] == tab["windowId"]:
            return

    monitor = next(m for m in snapshot("monitors") if m["focused"])
    origin = snapshot("activewindow")
    origin_address = (origin.get("address") if origin.get("workspace", {}).get("name") ==
                      monitor["activeWorkspace"]["name"] else None)
    previous_tab = next((t for t in tabs if t["windowId"] == tab["windowId"] and t["active"]), None)
    call("activate", tabId=tab_id)
    chrome = active_chrome(tab["title"])
    if chrome.get("fullscreen") or chrome["workspace"]["name"].startswith("special:"):
        raise RuntimeError("Cannot summon a fullscreen or special-workspace window")
    workspace = chrome["workspace"]["name"]
    address = chrome["address"]
    tiled = not chrome["floating"]
    original = geometry(workspace) if tiled else {}
    state = {"windowId": tab["windowId"], "address": address, "workspace": workspace,
             "tiled": tiled, "at": chrome["at"], "size": chrome["size"], "geometry": original,
             "previousTabId": previous_tab["id"] if previous_tab else None,
             "originMonitor": {"name": monitor["name"], "activeWorkspace": monitor["activeWorkspace"]},
             "originAddress": origin_address}

    if tiled:
        plugin("showSlot")
        placeholder = wait_for(slot)
        if placeholder["workspace"]["name"] != workspace:
            plugin("hideSlot")
            raise RuntimeError("Placeholder mapped on the wrong workspace")
        focus(address)
        dispatch(f'hl.dsp.window.swap({{ target = "address:{placeholder["address"]}" }})')
    STATE.write_text(json.dumps(state))
    STATE.chmod(0o600)
    try:
        move(address, LOCKER)
        if tiled:
            after = geometry(workspace)
            if after.get(placeholder["address"]) != original[address] or any(
                after.get(k) != v for k, v in original.items() if k != address
            ):
                raise RuntimeError("Placeholder did not preserve the tiling layout")
            dispatch(f'hl.dsp.window.float({{ action = "enable", {sel(address)} }})')
        width = round(monitor["width"] / monitor["scale"] * 0.6)
        height = round(monitor["height"] / monitor["scale"] * 0.75)
        dispatch(f'hl.dsp.window.resize({{ x = {width}, y = {height}, {sel(address)} }})')
        dispatch(f'hl.dsp.window.center({{ {sel(address)} }})')
        return_to(monitor)
        if not any(m["specialWorkspace"]["name"] == LOCKER for m in snapshot("monitors")):
            dispatch('hl.dsp.workspace.toggle_special("chrome-search")')
        focus(address)
    except Exception:
        restore(state)
        raise
