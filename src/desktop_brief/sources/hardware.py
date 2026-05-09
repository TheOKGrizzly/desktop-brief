"""Hardware metrics via psutil (+ optional nvidia-smi for GPU)."""
from __future__ import annotations

import asyncio
import logging
import shutil
import time

import psutil

from desktop_brief.config import INTERVALS, Config
from desktop_brief.sources.base import Source
from desktop_brief.state import write_source

logger = logging.getLogger(__name__)


_NVIDIA_SMI = shutil.which("nvidia-smi")


class HardwareSource(Source):
    name = "hardware"

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        # Prime per-CPU + net counters so the first sample has deltas.
        psutil.cpu_percent(interval=None, percpu=True)
        self._last_net = psutil.net_io_counters()
        self._last_net_t = time.monotonic()

    @property
    def interval_s(self) -> int:
        return INTERVALS["hardware"]

    async def _gpu(self) -> list[dict] | None:
        if not _NVIDIA_SMI:
            return None
        try:
            proc = await asyncio.create_subprocess_exec(
                _NVIDIA_SMI,
                "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await proc.communicate()
            if proc.returncode != 0:
                return None
            gpus = []
            for line in out.decode().strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 5:
                    gpus.append({
                        "name": parts[0],
                        "util_pct": float(parts[1]),
                        "mem_used_mb": float(parts[2]),
                        "mem_total_mb": float(parts[3]),
                        "temp_c": float(parts[4]),
                    })
            return gpus or None
        except Exception:
            logger.debug("nvidia-smi probe failed", exc_info=True)
            return None

    def _cpu_temp(self) -> float | None:
        try:
            temps = psutil.sensors_temperatures(fahrenheit=False)
        except (AttributeError, OSError):
            return None
        if not temps:
            return None
        # Prefer Intel/AMD package temps, then any core/Tdie.
        for label_pref in ("coretemp", "k10temp", "cpu_thermal", "acpitz"):
            entries = temps.get(label_pref)
            if entries:
                vals = [e.current for e in entries if e.current]
                if vals:
                    return round(max(vals), 1)
        # Fallback: max temp anywhere.
        all_vals = [e.current for entries in temps.values() for e in entries if e.current]
        return round(max(all_vals), 1) if all_vals else None

    async def run_once(self) -> None:
        cpu_overall = psutil.cpu_percent(interval=None)
        cpu_per = psutil.cpu_percent(interval=None, percpu=True)
        vm = psutil.virtual_memory()
        sm = psutil.swap_memory()
        load1, load5, load15 = psutil.getloadavg()
        disk = psutil.disk_usage("/")

        net = psutil.net_io_counters()
        now_t = time.monotonic()
        dt = max(now_t - self._last_net_t, 1e-6)
        rx_kbps = (net.bytes_recv - self._last_net.bytes_recv) / dt / 1024
        tx_kbps = (net.bytes_sent - self._last_net.bytes_sent) / dt / 1024
        self._last_net = net
        self._last_net_t = now_t

        gpus = await self._gpu()

        data = {
            "cpu": {
                "overall_pct": round(cpu_overall, 1),
                "per_core_pct": [round(x, 1) for x in cpu_per],
                "core_count": psutil.cpu_count(logical=True),
                "load_avg": [round(load1, 2), round(load5, 2), round(load15, 2)],
                "temp_c": self._cpu_temp(),
            },
            "memory": {
                "used_gb": round(vm.used / 1024**3, 2),
                "total_gb": round(vm.total / 1024**3, 2),
                "pct": round(vm.percent, 1),
                "swap_used_gb": round(sm.used / 1024**3, 2),
                "swap_total_gb": round(sm.total / 1024**3, 2),
            },
            "disk": {
                "used_gb": round(disk.used / 1024**3, 1),
                "total_gb": round(disk.total / 1024**3, 1),
                "pct": round(disk.percent, 1),
            },
            "network": {
                "rx_kbps": round(rx_kbps, 1),
                "tx_kbps": round(tx_kbps, 1),
            },
            "gpu": gpus,
            "uptime_s": int(time.time() - psutil.boot_time()),
        }
        write_source("hardware", data)
