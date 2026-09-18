import os
import logging
import urllib.parse
from datetime import datetime
import httpx
from notify import send_telegram

log = logging.getLogger("operator.report")

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")
LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100")


async def _query_prometheus(client: httpx.AsyncClient, expr: str) -> list:
    try:
        url = f"{PROMETHEUS_URL}/api/v1/query?query=" + urllib.parse.quote(expr)
        r = await client.get(url, timeout=10.0)
        if r.status_code == 200:
            return r.json().get("data", {}).get("result", [])
    except Exception as e:
        log.warning("Prometheus query failed for '%s': %s", expr, e)
    return []


async def _query_loki(client: httpx.AsyncClient, expr: str) -> list:
    try:
        url = f"{LOKI_URL}/loki/api/v1/query?query=" + urllib.parse.quote(expr)
        r = await client.get(url, timeout=15.0)
        if r.status_code == 200:
            return r.json().get("data", {}).get("result", [])
    except Exception as e:
        log.warning("Loki query failed for '%s': %s", expr, e)
    return []


async def generate_daily_report() -> str:
    async with httpx.AsyncClient() as client:
        # 1. Host Resources
        ram_total_res = await _query_prometheus(client, "node_memory_MemTotal_bytes")
        ram_avail_res = await _query_prometheus(client, "node_memory_MemAvailable_bytes")
        disk_total_res = await _query_prometheus(client, 'node_filesystem_size_bytes{mountpoint="/"}')
        disk_avail_res = await _query_prometheus(client, 'node_filesystem_avail_bytes{mountpoint="/"}')
        load1_res = await _query_prometheus(client, "node_load1")
        load5_res = await _query_prometheus(client, "node_load5")
        load15_res = await _query_prometheus(client, "node_load15")
        uptime_res = await _query_prometheus(client, "time() - node_boot_time_seconds")

        # 2. Container Status
        running_res = await _query_prometheus(client, 'time() - container_last_seen{name=~".+"} < 60')

        # 3. 24-hour Error Summary from Loki
        error_res = await _query_loki(
            client,
            'sum by (container) (count_over_time({job=~".+", container!~"obs-.*"} |~ "(?i)(level=error|level=fatal|error:|fatal:|exception:|traceback|panic:)" [24h]))'
        )

    # Format RAM
    ram_str = "N/A"
    if ram_total_res and ram_avail_res:
        total = float(ram_total_res[0]["value"][1]) / (1024 ** 3)
        avail = float(ram_avail_res[0]["value"][1]) / (1024 ** 3)
        used = total - avail
        pct = (used / total) * 100 if total > 0 else 0
        ram_str = f"{used:.1f} GB / {total:.1f} GB ({pct:.1f}% used)"

    # Format Disk
    disk_str = "N/A"
    if disk_total_res and disk_avail_res:
        d_total = float(disk_total_res[0]["value"][1]) / (1024 ** 3)
        d_avail = float(disk_avail_res[0]["value"][1]) / (1024 ** 3)
        d_used = d_total - d_avail
        d_pct = (d_used / d_total) * 100 if d_total > 0 else 0
        disk_str = f"{d_used:.1f} GB / {d_total:.1f} GB ({d_pct:.1f}% used)"

    # Format Load
    load_str = "N/A"
    if load1_res and load5_res and load15_res:
        l1 = float(load1_res[0]["value"][1])
        l5 = float(load5_res[0]["value"][1])
        l15 = float(load15_res[0]["value"][1])
        load_str = f"{l1:.2f}, {l5:.2f}, {l15:.2f}"

    # Format Uptime
    uptime_str = "N/A"
    if uptime_res:
        secs = float(uptime_res[0]["value"][1])
        days = int(secs // 86400)
        hrs = int((secs % 86400) // 3600)
        uptime_str = f"{days}d {hrs}h"

    # Containers
    running_count = len(running_res)

    # Errors
    errors_by_container = {}
    total_errors = 0
    for r in error_res:
        count = int(r["value"][1])
        if count > 0:
            c_name = r.get("metric", {}).get("container", "unknown")
            errors_by_container[c_name] = count
            total_errors += count

    # Build report text
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"📊 *Volcano Daily Performance Report*",
        f"📅 `{today}`",
        "",
        "🖥 *Host Resources:*",
        f"• RAM: `{ram_str}`",
        f"• Disk: `{disk_str}`",
        f"• Load Average: `{load_str}`",
        f"• Uptime: `{uptime_str}`",
        "",
        f"📦 *Containers:*",
        f"• `{running_count}` active containers running",
        "",
        f"📋 *Application Errors (Last 24h):*",
    ]

    if total_errors == 0:
        lines.append("• ✅ 0 errors recorded across all apps")
    else:
        sorted_errors = sorted(errors_by_container.items(), key=lambda x: x[1], reverse=True)
        for c_name, count in sorted_errors[:5]:
            lines.append(f"• `{c_name}`: {count} error{'s' if count != 1 else ''}")
        lines.append(f"• *Total:* {total_errors} errors across {len(sorted_errors)} services")

    return "\n".join(lines)


async def send_daily_report():
    try:
        report_text = await generate_daily_report()
        await send_telegram(report_text)
        log.info("Daily performance report sent successfully")
    except Exception as e:
        log.error("Failed to generate or send daily report: %s", e)
