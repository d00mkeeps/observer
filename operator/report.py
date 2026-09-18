import os
import time
import logging
import urllib.parse
from datetime import datetime
import httpx
from notify import send_telegram

log = logging.getLogger("operator.report")

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")
LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100")

# Containers to skip in the app sections (infra, not user apps)
INFRA_CONTAINERS = {
    "obs-prometheus", "obs-grafana", "obs-loki", "obs-alloy",
    "obs-cadvisor", "obs-node-exporter", "obs-operator",
    "sturdy-robot-tunnel-1",
}


async def _prom(client: httpx.AsyncClient, expr: str) -> list:
    try:
        r = await client.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": expr},
            timeout=10.0,
        )
        if r.status_code == 200:
            return r.json().get("data", {}).get("result", [])
    except Exception as e:
        log.warning("Prometheus query failed (%s): %s", expr[:60], e)
    return []


async def _loki(client: httpx.AsyncClient, expr: str) -> list:
    try:
        r = await client.get(
            f"{LOKI_URL}/loki/api/v1/query",
            params={"query": expr},
            timeout=15.0,
        )
        if r.status_code == 200:
            return r.json().get("data", {}).get("result", [])
    except Exception as e:
        log.warning("Loki query failed (%s): %s", expr[:60], e)
    return []


def _bar(pct: float, width: int = 10) -> str:
    """Render a simple block progress bar, e.g. ████░░░░░░ 42%"""
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled) + f" {pct:.0f}%"


def _mb(bytes_val: float) -> str:
    if bytes_val >= 1024:
        return f"{bytes_val / 1024:.1f} GB"
    return f"{bytes_val:.0f} MB"


async def generate_daily_report() -> str:
    async with httpx.AsyncClient() as client:
        # ── Host ──────────────────────────────────────────────
        ram_total_r  = await _prom(client, "node_memory_MemTotal_bytes")
        ram_avail_r  = await _prom(client, "node_memory_MemAvailable_bytes")
        disk_total_r = await _prom(client, 'node_filesystem_size_bytes{mountpoint="/"}')
        disk_avail_r = await _prom(client, 'node_filesystem_avail_bytes{mountpoint="/"}')
        load1_r      = await _prom(client, "node_load1")
        uptime_r     = await _prom(client, "time() - node_boot_time_seconds")

        # ── Containers ────────────────────────────────────────
        running_r = await _prom(client, 'time() - container_last_seen{name=~".+"} < 60')

        # Per-container memory (MB)
        mem_r = await _prom(client, 'sum by (name) (container_memory_usage_bytes{name=~".+"})')

        # Per-container CPU % (rate over last 5m)
        cpu_r = await _prom(client, 'sum by (name) (rate(container_cpu_usage_seconds_total{name=~".+"}[5m])) * 100')

        # ── Errors from Loki ──────────────────────────────────
        error_r = await _loki(
            client,
            'sum by (container) (count_over_time({job=~".+", container!~"obs-.*"}'
            ' |~ "(?i)(level=error|level=fatal|error:|fatal:|exception:|traceback|panic:)" [24h]))',
        )

    # ── Parse host ────────────────────────────────────────────
    ram_pct = ram_used_gb = ram_total_gb = 0.0
    if ram_total_r and ram_avail_r:
        t = float(ram_total_r[0]["value"][1])
        a = float(ram_avail_r[0]["value"][1])
        ram_used_gb  = (t - a) / 1024**3
        ram_total_gb = t / 1024**3
        ram_pct      = (t - a) / t * 100

    disk_pct = disk_used_gb = disk_total_gb = 0.0
    if disk_total_r and disk_avail_r:
        t = float(disk_total_r[0]["value"][1])
        a = float(disk_avail_r[0]["value"][1])
        disk_used_gb  = (t - a) / 1024**3
        disk_total_gb = t / 1024**3
        disk_pct      = (t - a) / t * 100

    load1 = float(load1_r[0]["value"][1]) if load1_r else 0.0

    uptime_str = "unknown"
    if uptime_r:
        s = float(uptime_r[0]["value"][1])
        uptime_str = f"{int(s // 86400)}d {int((s % 86400) // 3600)}h"

    # ── Parse containers ─────────────────────────────────────
    running_names = {r["metric"]["name"] for r in running_r}
    app_names     = sorted(running_names - INFRA_CONTAINERS)

    mem_by_name = {r["metric"]["name"]: float(r["value"][1]) / 1024**2 for r in mem_r}
    cpu_by_name = {r["metric"]["name"]: float(r["value"][1]) for r in cpu_r}

    # ── Parse errors ─────────────────────────────────────────
    errors_by_container: dict[str, int] = {}
    total_errors = 0
    for r in error_r:
        c = r.get("metric", {}).get("container", "unknown")
        n = int(r["value"][1])
        if n > 0:
            errors_by_container[c] = n
            total_errors += n

    # ── Format ───────────────────────────────────────────────
    today = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Host block
    ram_warn  = " ⚠️" if ram_pct  > 80 else ""
    disk_warn = " ⚠️" if disk_pct > 80 else ""
    load_warn = " ⚠️" if load1    > 4  else ""

    host_block = (
        f"🖥 *volcano*  —  up {uptime_str}\n"
        f"  RAM   {_bar(ram_pct)}  {ram_used_gb:.1f}/{ram_total_gb:.0f} GB{ram_warn}\n"
        f"  Disk  {_bar(disk_pct)}  {disk_used_gb:.0f}/{disk_total_gb:.0f} GB{disk_warn}\n"
        f"  Load  {load1:.2f}{load_warn}    Containers: {len(running_names)} running"
    )

    # App table — show memory, cpu, errors per app container
    # Skip infra; limit to app containers
    app_rows = []
    for name in app_names:
        mem_mb = mem_by_name.get(name, 0)
        cpu_pc = cpu_by_name.get(name, 0)
        errs   = errors_by_container.get(name, 0)
        err_str = f"⚠️{errs}" if errs else "✅"
        app_rows.append((name, mem_mb, cpu_pc, errs, err_str))

    # Sort by error count desc, then name
    app_rows.sort(key=lambda x: (-x[3], x[0]))

    app_lines = []
    for name, mem_mb, cpu_pc, errs, err_str in app_rows:
        mem_s = _mb(mem_mb)
        cpu_s = f"{cpu_pc:.1f}%" if cpu_pc >= 0.1 else "<0.1%"
        app_lines.append(f"  `{name:<28}` {mem_s:>7}  {cpu_s:>5}  {err_str}")

    app_block = (
        "📦 *Apps*\n"
        f"  `{'name':<28}` {'mem':>7}  {'cpu':>5}  errors\n"
        "  " + "─" * 52 + "\n"
        + "\n".join(app_lines)
    )

    # Error summary (top 5)
    error_block_lines = []
    if total_errors == 0:
        error_block_lines.append("✅ No errors in the last 24h")
    else:
        sorted_errs = sorted(errors_by_container.items(), key=lambda x: -x[1])
        for c, n in sorted_errs[:5]:
            bar = "█" * min(10, max(1, round(n / max(errors_by_container.values()) * 10)))
            error_block_lines.append(f"  `{c}` — {n:,}")
        error_block_lines.append(f"\n  *Total: {total_errors:,} errors across {len(errors_by_container)} services*")

    error_block = "📋 *Errors (24h)*\n" + "\n".join(error_block_lines)

    # Assemble
    lines = [
        f"📊 *Daily Report*  `{today}`",
        "",
        host_block,
        "",
        app_block,
        "",
        error_block,
    ]

    return "\n".join(lines)


async def send_daily_report():
    try:
        text = await generate_daily_report()
        await send_telegram(text)
        log.info("Daily performance report sent")
    except Exception as e:
        log.error("Failed to send daily report: %s", e)
