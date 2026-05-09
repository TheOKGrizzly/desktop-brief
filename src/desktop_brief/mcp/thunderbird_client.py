"""Async stdio client for the Thunderbird MCP bridge.

The bridge speaks line-delimited JSON-RPC 2.0 over stdio. We spawn the
Node subprocess once per client lifetime, multiplex requests by id,
and auto-restart on EOF.
"""
from __future__ import annotations

import asyncio
import itertools
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ThunderbirdMCPError(RuntimeError):
    pass


class ThunderbirdMCPClient:
    """One subprocess, many concurrent JSON-RPC calls.

    Usage:
        client = ThunderbirdMCPClient(bridge_path)
        await client.start()
        accounts = await client.list_accounts()
        ...
        await client.stop()
    """

    def __init__(self, bridge_path: Path, *, request_timeout: float = 30.0) -> None:
        self._bridge_path = bridge_path
        self._timeout = request_timeout
        self._proc: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._restart_lock = asyncio.Lock()
        self._pending: dict[int, asyncio.Future] = {}
        self._id_counter = itertools.count(1)
        self._initialized = False

    # ---- lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        if not self._bridge_path.exists():
            raise ThunderbirdMCPError(f"bridge not found at {self._bridge_path}")
        await self._spawn()

    async def stop(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
            self._reader_task = None
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                if self._proc.returncode is None:
                    self._proc.kill()
        self._proc = None
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(ThunderbirdMCPError("client stopped"))
        self._pending.clear()

    async def _spawn(self) -> None:
        logger.info("spawning thunderbird-mcp bridge: %s", self._bridge_path)
        self._proc = await asyncio.create_subprocess_exec(
            "node",
            str(self._bridge_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_loop(), name="tb-mcp-reader")
        await self._initialize()

    async def _restart(self) -> None:
        async with self._restart_lock:
            if self._proc and self._proc.returncode is None:
                return  # someone else already restarted
            logger.warning("thunderbird-mcp bridge died; restarting")
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(ThunderbirdMCPError("bridge restarted"))
            self._pending.clear()
            self._initialized = False
            await self._spawn()

    # ---- protocol -----------------------------------------------------------

    async def _read_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        try:
            while True:
                line = await self._proc.stdout.readline()
                if not line:
                    logger.warning("thunderbird-mcp stdout EOF")
                    return
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("non-JSON stdout line: %r", line[:200])
                    continue

                msg_id = msg.get("id")
                if msg_id is None or msg_id not in self._pending:
                    # Notification (no id) or unsolicited response.
                    logger.debug("unsolicited mcp message: %s", str(msg)[:200])
                    continue
                fut = self._pending.pop(msg_id)
                if fut.done():
                    continue
                if "error" in msg:
                    fut.set_exception(ThunderbirdMCPError(str(msg["error"])))
                else:
                    fut.set_result(msg.get("result"))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("reader loop crashed")

    async def _send(self, method: str, params: dict | None = None) -> Any:
        # If the subprocess has died, restart before sending.
        if not self._proc or self._proc.returncode is not None:
            await self._restart()

        assert self._proc is not None and self._proc.stdin is not None
        msg_id = next(self._id_counter)
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = fut

        msg = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params is not None:
            msg["params"] = params

        try:
            self._proc.stdin.write((json.dumps(msg) + "\n").encode())
            await self._proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as e:
            self._pending.pop(msg_id, None)
            raise ThunderbirdMCPError(f"stdin write failed: {e}") from e

        try:
            return await asyncio.wait_for(fut, timeout=self._timeout)
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            raise ThunderbirdMCPError(f"timeout waiting for {method}") from None

    async def _initialize(self) -> None:
        await self._send(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "desktop-brief", "version": "0.1"},
            },
        )
        # MCP requires this notification post-initialize.
        assert self._proc is not None and self._proc.stdin is not None
        notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        try:
            self._proc.stdin.write((json.dumps(notif) + "\n").encode())
            await self._proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        self._initialized = True

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        result = await self._send("tools/call", {"name": name, "arguments": arguments or {}})
        # MCP tool results commonly look like {"content": [{"type":"text","text":"..."}], "isError": false}
        if isinstance(result, dict) and "content" in result:
            content = result["content"]
            if isinstance(content, list) and content:
                first = content[0]
                if first.get("type") == "text":
                    text = first.get("text", "")
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return text
        return result

    # ---- typed wrappers (the four we need) ----------------------------------

    async def list_accounts(self) -> Any:
        return await self.call_tool("listAccounts")

    async def get_recent_messages(self, account_id: str | None = None, limit: int = 50) -> Any:
        args: dict[str, Any] = {"limit": limit}
        if account_id is not None:
            args["accountId"] = account_id
        return await self.call_tool("getRecentMessages", args)

    async def search_messages(self, query: dict[str, Any]) -> Any:
        return await self.call_tool("searchMessages", query)

    async def list_events(self, calendar_id: str | None = None, time_min: str | None = None,
                          time_max: str | None = None) -> Any:
        args: dict[str, Any] = {}
        if calendar_id:
            args["calendarId"] = calendar_id
        if time_min:
            args["timeMin"] = time_min
        if time_max:
            args["timeMax"] = time_max
        return await self.call_tool("listEvents", args)

    async def list_calendars(self) -> Any:
        return await self.call_tool("listCalendars")
