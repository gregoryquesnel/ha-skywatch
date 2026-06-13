#!/usr/bin/env python3
"""Deploy examples/dashboard-skywatch-test.yaml as 'skywatch-test'.

Uses HA's WebSocket API to register a new dashboard and save its YAML
config. After deploy the dashboard is reachable at
http://<HA>:8123/skywatch-test/skywatch-test (the doubled segment is
intentional — first is the dashboard url_path, second is the view path).

Re-runnable: if the dashboard already exists, the YAML is overwritten.

Env: HA_HOST (default 10.100.100.200), HA_TOKEN (required).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import websockets
import yaml

HA_HOST = os.environ.get("HA_HOST", "10.100.100.200")
HA_PORT = os.environ.get("HA_PORT", "8123")
HA_TOKEN = os.environ.get("HA_TOKEN")

DASHBOARD_URL_PATH = "skywatch-test"
DASHBOARD_TITLE = "Skywatch Test"
DASHBOARD_ICON = "mdi:airplane"

REPO_ROOT = Path(__file__).parent.parent
DASHBOARD_YAML = REPO_ROOT / "examples" / "dashboard-skywatch-test.yaml"


async def _ws_request(ws, request: dict, request_id: int) -> dict:
    request["id"] = request_id
    await ws.send(json.dumps(request))
    while True:
        raw = await ws.recv()
        msg = json.loads(raw)
        if msg.get("id") == request_id:
            return msg


async def main() -> int:
    if not HA_TOKEN:
        print("ERROR: HA_TOKEN env var not set", file=sys.stderr)
        return 2
    if not DASHBOARD_YAML.exists():
        print(f"ERROR: {DASHBOARD_YAML} missing", file=sys.stderr)
        return 2

    config = yaml.safe_load(DASHBOARD_YAML.read_text())
    uri = f"ws://{HA_HOST}:{HA_PORT}/api/websocket"
    print(f"==> Connecting to {uri}")
    async with websockets.connect(uri) as ws:
        # auth_required → auth
        hello = json.loads(await ws.recv())
        if hello.get("type") != "auth_required":
            print(f"unexpected hello: {hello}", file=sys.stderr)
            return 2
        await ws.send(json.dumps({"type": "auth", "access_token": HA_TOKEN}))
        ok = json.loads(await ws.recv())
        if ok.get("type") != "auth_ok":
            print(f"auth failed: {ok}", file=sys.stderr)
            return 2

        req_id = 0

        def next_id() -> int:
            nonlocal req_id
            req_id += 1
            return req_id

        # List existing dashboards
        existing = await _ws_request(
            ws, {"type": "lovelace/dashboards/list"}, next_id()
        )
        existing_url_paths = {
            d["url_path"]: d for d in (existing.get("result") or [])
        }

        if DASHBOARD_URL_PATH not in existing_url_paths:
            print(f"==> Creating dashboard '{DASHBOARD_URL_PATH}'")
            create = await _ws_request(
                ws,
                {
                    "type": "lovelace/dashboards/create",
                    "url_path": DASHBOARD_URL_PATH,
                    "require_admin": False,
                    "show_in_sidebar": True,
                    "title": DASHBOARD_TITLE,
                    "icon": DASHBOARD_ICON,
                    "mode": "storage",
                },
                next_id(),
            )
            if not create.get("success", False):
                print(f"create failed: {create}", file=sys.stderr)
                return 2
        else:
            print(f"==> Dashboard '{DASHBOARD_URL_PATH}' already exists; updating config")

        save = await _ws_request(
            ws,
            {
                "type": "lovelace/config/save",
                "url_path": DASHBOARD_URL_PATH,
                "config": config,
            },
            next_id(),
        )
        if not save.get("success", False):
            print(f"save failed: {save}", file=sys.stderr)
            return 2

    print(
        f"==> Deployed. Open http://{HA_HOST}:{HA_PORT}/{DASHBOARD_URL_PATH}/skywatch-test"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
