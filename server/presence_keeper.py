#!/usr/bin/env python3
"""Keep the LumiOn Discord presence alive with an independent heartbeat loop."""

import asyncio
import contextlib
import json
import os
import random
from datetime import datetime

import aiohttp
from dotenv import load_dotenv


load_dotenv()

GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"
TOKEN = os.getenv("PRESENCE_TOKEN", "").strip()
ACTIVITY_TEXT = os.getenv("PRESENCE_ACTIVITY_TEXT", "24시간 깨어있는중").strip()
ACTIVITY_TYPE = os.getenv("PRESENCE_ACTIVITY_TYPE", "playing").strip().lower()
STATUS = os.getenv("PRESENCE_STATUS", "online").strip().lower()
REFRESH_SECONDS = max(int(os.getenv("PRESENCE_REFRESH_SECONDS", "300")), 60)


def log(message: str) -> None:
    print(f"{datetime.now().isoformat(timespec='seconds')} {message}", flush=True)


def presence() -> dict:
    type_map = {
        "playing": 0,
        "streaming": 1,
        "listening": 2,
        "watching": 3,
        "custom": 4,
        "competing": 5,
    }
    activity = {"name": ACTIVITY_TEXT, "type": type_map.get(ACTIVITY_TYPE, 0)}
    if ACTIVITY_TYPE == "streaming":
        activity["url"] = "https://twitch.tv/discord"
    return {"since": None, "activities": [activity], "status": STATUS, "afk": False}


async def heartbeat_loop(ws: aiohttp.ClientWebSocketResponse, interval: float, state: dict) -> None:
    # Discord recommends jittering the first heartbeat to avoid synchronized reconnect storms.
    await asyncio.sleep(random.uniform(0, interval))
    while not ws.closed:
        state["acked"] = False
        await ws.send_json({"op": 1, "d": state.get("seq")})
        await asyncio.sleep(interval)
        if not state.get("acked", True):
            log("Heartbeat ACK missing; reconnecting")
            await ws.close(code=4000, message=b"heartbeat timeout")
            return


async def presence_refresh_loop(ws: aiohttp.ClientWebSocketResponse) -> None:
    while not ws.closed:
        await asyncio.sleep(REFRESH_SECONDS)
        if not ws.closed:
            await ws.send_json({"op": 3, "d": presence()})


async def connect_once(session: aiohttp.ClientSession) -> None:
    async with session.ws_connect(GATEWAY_URL, heartbeat=None, receive_timeout=None) as ws:
        hello = await asyncio.wait_for(ws.receive_json(), timeout=30)
        if hello.get("op") != 10:
            raise RuntimeError(f"Expected Gateway Hello, received op={hello.get('op')}")

        interval = hello["d"]["heartbeat_interval"] / 1000
        state = {"seq": None, "acked": True}
        await ws.send_json(
            {
                "op": 2,
                "d": {
                    "token": TOKEN,
                    "properties": {"os": "linux", "browser": "lumion", "device": "lumion"},
                    "presence": presence(),
                },
            }
        )
        heartbeat_task = asyncio.create_task(heartbeat_loop(ws, interval, state))
        refresh_task = asyncio.create_task(presence_refresh_loop(ws))
        log(f"Gateway connected; heartbeat={interval:.2f}s")

        try:
            async for message in ws:
                if message.type == aiohttp.WSMsgType.TEXT:
                    payload = json.loads(message.data)
                    op = payload.get("op")
                    if payload.get("s") is not None:
                        state["seq"] = payload["s"]
                    if op == 0 and payload.get("t") == "READY":
                        user = payload["d"]["user"]
                        log(f"Presence online as {user.get('username')} ({user.get('id')})")
                    elif op == 1:
                        await ws.send_json({"op": 1, "d": state.get("seq")})
                    elif op == 7:
                        log("Gateway requested reconnect")
                        break
                    elif op == 9:
                        log("Gateway invalidated the session")
                        await asyncio.sleep(random.uniform(1, 5))
                        break
                    elif op == 11:
                        state["acked"] = True
                elif message.type in {
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                }:
                    break
        finally:
            for task in (heartbeat_task, refresh_task):
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.gather(heartbeat_task, refresh_task)


async def main() -> None:
    if not TOKEN:
        raise RuntimeError("PRESENCE_TOKEN is missing from the environment")
    timeout = aiohttp.ClientTimeout(total=None, connect=30, sock_connect=30, sock_read=None)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        delay = 3
        while True:
            try:
                await connect_once(session)
                delay = 3
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # keep the process alive through network/API failures
                log(f"Gateway error: {type(exc).__name__}: {exc}")
                delay = min(delay * 2, 60)
            log(f"Reconnecting in {delay}s")
            await asyncio.sleep(delay)


if __name__ == "__main__":
    asyncio.run(main())
