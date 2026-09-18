import os
import html
import logging
import urllib.parse
from datetime import datetime
import httpx
from notify import send_telegram

log = logging.getLogger("operator.report")

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")
LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100")


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
        log.warning("Prometheus query failed: %s", e)
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
        log.warning("Loki query failed: %s", e)
    return []


async def generate_daily_report() -> str:
    async with httpx.AsyncClient() as client:
        ram_total_r  = await _prom(client, "node_memory_MemTotal_bytes")
        ram_avail_r  = await _prom(client, "node_memory_MemAvailable_bytes")
        disk_total_r = await _prom(client, 'node_filesystem_size_bytes{mountpoint="/"}')
        disk_avail_r = await _prom(client, 'node_filesystem_avail_bytes{mountpoint="/"}')
        load1_r      = await _prom(client, "node_load1")
        uptime_r     = await _prom(client, "time() - node_boot_time_seconds")
        running_r    = await _prom(client, 'time() - container_last_seen{name=~".+"} < 60')
        error_r      = await _loki(
            client,
            'sum by (container) (count_over_time({job=~".+", container!~"obs-.*"}'
            ' |~ "(?i)(level=error|level=fatal|error:|fatal:|exception:|traceback|panic:)" [24h]))',
        )

    ram_gb = disk_gb = load = 0.0
    ram_pct = disk_pct = 0

    if ram_total_r and ram_avail_r:
        t = float(ram_total_r[0]["value"][1]) / 1024**3
        a = float(ram_avail_r[0]["value"][1]) / 1024**3
        ram_gb  = t - a
        ram_pct = round((t - a) / t * 100)

    if disk_total_r and disk_avail_r:
        t = float(disk_total_r[0]["value"][1]) / 1024**3
        a = float(disk_avail_r[0]["value"][1]) / 1024**3
        disk_gb  = t - a
        disk_pct = round((t - a) / t * 100)

    if load1_r:
        load = float(load1_r[0]["value"][1])

    uptime_str = "?"
    if uptime_r:
        s = float(uptime_r[0]["value"][1])
        uptime_str = f"{int(s // 86400)}d {int((s % 86400) // 3600)}h"

    n_containers = len(running_r)

    errors: dict[str, int] = {}
    for r in error_r:
        n = int(r["value"][1])
        if n > 0:
            errors[r.get("metric", {}).get("container", "?")] = n

    total_errors = sum(errors.values())
    today = datetime.now().strftime("%d %b %Y, %H:%M")

    lines = [
        f"🌋 <b>Volcano</b>  {today}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"💾 <b>RAM</b>   <code>{ram_gb:.1f} GB ({ram_pct}%)</code>",
        f"💿 <b>Disk</b>  <code>{disk_gb:.0f} GB ({disk_pct}%)</code>",
        f"⚡ <b>Load</b>  <code>{load:.2f}</code>   Up <code>{uptime_str}</code>",
        f"📦 <code>{n_containers}</code> containers running",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    if total_errors == 0:
        lines.append("✅ No errors in the last 24h")
    else:
        lines.append(f"⚠️ <b>Errors (24h)</b> — <code>{total_errors:,}</code> total")
        for c, n in sorted(errors.items(), key=lambda x: -x[1])[:5]:
            lines.append(f"  • <code>{html.escape(c)}</code>: {n:,}")
        if len(errors) > 5:
            lines.append(f"  <i>… and {len(errors) - 5} more services</i>")

    return "\n".join(lines)


async def send_daily_report():
    try:
        await send_telegram(await generate_daily_report(), channel="reports")
        log.info("Daily performance report sent")
    except Exception as e:
        log.error("Failed to send daily report: %s", e)
