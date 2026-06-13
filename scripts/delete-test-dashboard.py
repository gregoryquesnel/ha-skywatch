#!/usr/bin/env python3
"""Remove the 'skywatch-test' dashboard from HA.

Idempotent: succeeds if the dashboard is already gone.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

import websockets

HA_HOST = os.environ.get("HA_HOST", "10.100.100.200")
HA_PORT = os.environ.get("HA_PORT", "8123")
HA_TOKEN = os.environ.get("HA_TOKEN")
DASHBOARD_URL_PATH = "skywatch-test"


async def main() -> int:
    if not HA_TOKEN:
        print("ERROR: HA_TOKEN env var not set", file=sys.stderr)
        return 2
    uri = f"ws://{HA_HOST}:{HA_PORT}/api/websocket"
    async with websockets.connect(uri) as ws:
        json.loads(await ws.recv())  # auth_required
        await ws.send(json.dumps({"type": "auth", "access_token": HA_TOKEN}))
        if json.loads(await ws.recv()).get("type") != "auth_ok":
            print("auth failed", file=sys.stderr)
            return 2

        await ws.send(json.dumps({"id": 1, "type": "lovelace/dashboards/list"}))
        msg = json.loads(await ws.recv())
        dashboards = msg.get("result") or []
        for d in dashboards:
            if d["url_path"] == DASHBOARD_URL_PATH:
                dashboard_id = d["id"]
                await ws.send(
                    json.dumps(
                        {
                            "id": 2,
                            "type": "lovelace/dashboards/delete",
                            "dashboard_id": dashboard_id,
                        }
                    )
                )
                result = json.loads(await ws.recv())
                if result.get("success"):
                    print(f"==> Deleted '{DASHBOARD_URL_PATH}'")
                else:
                    print(f"delete failed: {result}", file=sys.stderr)
                    return 2
                return 0
        print(f"==> Dashboard '{DASHBOARD_URL_PATH}' not found (already gone?)")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
