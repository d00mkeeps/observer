import os
import time
import re
import json
import urllib.parse
import urllib.request
import logging

log = logging.getLogger("operator.tools.observability")

LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100")
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")


def _prom_sync(expr: str) -> list:
    """Synchronously query Prometheus."""
    try:
        url = f"{PROMETHEUS_URL}/api/v1/query?query={urllib.parse.quote(expr)}"
        req = urllib.request.Request(url, headers={"User-Agent": "VolcanoObserver/1.0"})
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("data", {}).get("result", [])
    except Exception as e:
        log.warning("Sync Prometheus query failed: %s", e)
    return []


def _loki_sync(expr: str) -> list:
    """Synchronously query Loki."""
    try:
        url = f"{LOKI_URL}/loki/api/v1/query?query={urllib.parse.quote(expr)}"
        req = urllib.request.Request(url, headers={"User-Agent": "VolcanoObserver/1.0"})
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("data", {}).get("result", [])
    except Exception as e:
        log.warning("Sync Loki query failed: %s", e)
    return []


def push_loki_log(labels: dict[str, str], message: str, timestamp_ns: int | None = None) -> bool:
    """Push a structured log line directly to Loki."""
    if timestamp_ns is None:
        timestamp_ns = int(time.time() * 1e9)
    payload = {
        "streams": [
            {
                "stream": labels,
                "values": [
                    [str(timestamp_ns), message]
                ]
            }
        ]
    }
    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{LOKI_URL}/loki/api/v1/push",
            data=data_bytes,
            headers={"Content-Type": "application/json", "User-Agent": "VolcanoObserver/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            if resp.status in (200, 204):
                log.info("Pushed log to Loki successfully (labels=%s)", labels)
                return True
            else:
                log.warning("Loki push returned %d", resp.status)
                return False
    except urllib.error.HTTPError as e:
        if e.code in (200, 204):
            return True
        log.warning("Loki push HTTP error %d: %s", e.code, e.reason)
        return False
    except Exception as e:
        log.warning("Failed to push log to Loki: %s", e)
        return False


def _parse_duration_seconds(duration_str: str) -> int:
    """Convert human duration like '1h', '6h', '24h', '7d', '30m' to seconds."""
    duration_str = duration_str.strip().lower()
    m = re.match(r"^(\d+)([mhd])$", duration_str)
    if not m:
        return 86400  # Default 24 hours
    val, unit = int(m.group(1)), m.group(2)
    if unit == "m":
        return val * 60
    elif unit == "h":
        return val * 3600
    elif unit == "d":
        return val * 86400
    return 86400


def query_all_errors(duration: str = "24h", limit_per_app: int = 5) -> str:
    """Query Loki for all errors across all production containers and CI/CD pipelines in a given timeframe.

    Args:
        duration: Lookback duration (e.g. '1h', '6h', '24h', '7d'). Default is '24h'.
        limit_per_app: Max unique sample error lines per container (default 5).
    """
    duration = duration.strip().lower()
    if not re.match(r"^\d+[mhd]$", duration):
        duration = "24h"

    # 1. Aggregate error counts per container
    agg_query = (
        f'sum by (container) (count_over_time({{job=~".+", container!~"obs-.*"}}'
        f' |~ "(?i)(level=error|level=fatal|error:|fatal:|exception:|traceback|panic:)" [{duration}]))'
    )
    
    results = _loki_sync(agg_query)
    if not results:
        return f"✅ No application errors found in Loki across any containers in the last {duration}."

    counts = {}
    for r in results:
        container = r.get("metric", {}).get("container", "unknown")
        cnt = int(r.get("value", [0, 0])[1])
        if cnt > 0:
            counts[container] = cnt

    if not counts:
        return f"✅ No application errors found in Loki across any containers in the last {duration}."

    total_errors = sum(counts.values())
    secs = _parse_duration_seconds(duration)
    start_ns = int((time.time() - secs) * 1e9)
    end_ns = int(time.time() * 1e9)

    report_lines = [
        f"📊 Error Report Across All Apps & Pipelines (Last {duration}):",
        f"Total Errors: {total_errors:,} across {len(counts)} service(s)\n",
    ]

    # 2. Fetch sample logs for each failing container
    for container, count in sorted(counts.items(), key=lambda x: -x[1]):
        report_lines.append(f"• <b>{container}</b>: {count:,} errors in last {duration}")
        sample_query = urllib.parse.quote(
            f'{{container="{container}"}} |~ "(?i)(level=error|level=fatal|error:|fatal:|exception:|traceback|panic:)"'
        )
        sample_url = f"{LOKI_URL}/loki/api/v1/query_range?query={sample_query}&start={start_ns}&end={end_ns}&limit=15"
        try:
            req = urllib.request.Request(sample_url, headers={"User-Agent": "VolcanoObserver/1.0"})
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                sr_data = json.loads(resp.read().decode("utf-8"))
                data = sr_data.get("data", {}).get("result", [])
                seen_samples = set()
                for stream in data:
                    for _, line in stream.get("values", []):
                        line_clean = line.strip()
                        snippet = line_clean[:180]
                        if snippet not in seen_samples:
                            seen_samples.add(snippet)
                            report_lines.append(f"  - <code>{snippet}</code>")
                        if len(seen_samples) >= limit_per_app:
                            break
                    if len(seen_samples) >= limit_per_app:
                        break
        except Exception as e:
            log.warning("Failed fetching samples for %s: %s", container, e)
        report_lines.append("")

    return "\n".join(report_lines).strip()


def search_container_logs(query: str, container: str = "", duration: str = "24h", limit: int = 30) -> str:
    """Search Loki logs for specific keywords or patterns.

    Args:
        query: Search keyword or phrase.
        container: Optional specific container name (e.g. 'supreme-octo-doodle-api', 'medicine-api', 'github-actions').
        duration: Lookback duration (e.g. '1h', '6h', '24h', '7d'). Default '24h'.
        limit: Max lines to return (capped at 50).
    """
    limit = min(50, max(1, limit))
    secs = _parse_duration_seconds(duration)
    start_ns = int((time.time() - secs) * 1e9)
    end_ns = int(time.time() * 1e9)

    clean_q = re.escape(query.strip())
    if container:
        selector = f'{{container="{container.strip()}"}}'
    else:
        selector = '{job=~".+", container!~"obs-.*"}'

    logql = f'{selector} |~ "(?i){clean_q}"'
    encoded_logql = urllib.parse.quote(logql)
    url = f"{LOKI_URL}/loki/api/v1/query_range?query={encoded_logql}&start={start_ns}&end={end_ns}&limit={limit}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VolcanoObserver/1.0"})
        with urllib.request.urlopen(req, timeout=12.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("data", {}).get("result", [])
            if not results:
                return f"No logs found matching '{query}' in {container or 'all containers'} (last {duration})."

            matched_lines = []
            for stream in results:
                c_name = stream.get("stream", {}).get("container", "app")
                for _, line in stream.get("values", []):
                    matched_lines.append(f"[{c_name}] {line.strip()[:250]}")

            return f"Found {len(matched_lines)} matches for '{query}' (last {duration}):\n" + "\n".join(matched_lines[:limit])
    except Exception as e:
        return f"Error searching Loki logs: {str(e)}"


def get_error_frequency(container: str, days: int = 7) -> str:
    """Check how often an error or log pattern occurred in a container over time (1h, 24h, 7d).

    Args:
        container: Container name (e.g. 'supreme-octo-doodle-api', 'volc-website', 'github-actions').
        days: Historical days to inspect (default 7).
    """
    try:
        q_1h = f'sum(count_over_time({{container="{container}"}} |~ "(?i)(error|fatal|exception|traceback|panic:)" [1h]))'
        q_24h = f'sum(count_over_time({{container="{container}"}} |~ "(?i)(error|fatal|exception|traceback|panic:)" [24h]))'
        q_7d = f'sum(count_over_time({{container="{container}"}} |~ "(?i)(error|fatal|exception|traceback|panic:)" [{days}d]))'

        res_1h = _loki_sync(q_1h)
        res_24h = _loki_sync(q_24h)
        res_7d = _loki_sync(q_7d)

        count_1h = int(res_1h[0]["value"][1]) if res_1h and res_1h[0].get("value") else 0
        count_24h = int(res_24h[0]["value"][1]) if res_24h and res_24h[0].get("value") else 0
        count_7d = int(res_7d[0]["value"][1]) if res_7d and res_7d[0].get("value") else 0

        return (
            f"Error frequency for container '{container}':\n"
            f"- Last 1 Hour: {count_1h} occurrences\n"
            f"- Last 24 Hours: {count_24h} occurrences\n"
            f"- Last {days} Days: {count_7d} occurrences"
        )
    except Exception as e:
        return f"Error checking Loki frequency for '{container}': {str(e)}"


def get_recent_logs(container: str, minutes: int = 15, limit: int = 25) -> str:
    """Fetch recent log lines from Loki for a container.

    Args:
        container: Container name.
        minutes: Lookback duration in minutes.
        limit: Max log lines to return.
    """
    start_ns = int((time.time() - (minutes * 60)) * 1e9)
    end_ns = int(time.time() * 1e9)
    query = f'{{container="{container}"}}'

    url = f"{LOKI_URL}/loki/api/v1/query_range?query={urllib.parse.quote(query)}&start={start_ns}&end={end_ns}&limit={limit}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VolcanoObserver/1.0"})
        with urllib.request.urlopen(req, timeout=12.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("data", {}).get("result", [])
            if not results:
                return f"No logs found for container '{container}' in the last {minutes} minutes."

            lines = []
            for stream in results:
                values = stream.get("values", [])
                for _, line in values:
                    lines.append(line.strip())

            return "\n".join(lines[-limit:]) if lines else "No log lines found."
    except Exception as e:
        return f"Error fetching recent logs from Loki: {str(e)}"


def get_system_health() -> str:
    """Check Prometheus metrics for CPU, RAM, Disk, and container uptime across Volcano."""
    try:
        ram_total = _prom_sync("node_memory_MemTotal_bytes")
        ram_avail = _prom_sync("node_memory_MemAvailable_bytes")
        disk_total = _prom_sync('node_filesystem_size_bytes{mountpoint="/"}')
        disk_avail = _prom_sync('node_filesystem_avail_bytes{mountpoint="/"}')
        load1 = _prom_sync("node_load1")
        uptime = _prom_sync("time() - node_boot_time_seconds")
        running_containers = _prom_sync('time() - container_last_seen{name=~".+"} < 60')

        ram_pct = 0
        if ram_total and ram_avail:
            t = float(ram_total[0]["value"][1])
            a = float(ram_avail[0]["value"][1])
            ram_pct = round((t - a) / t * 100)

        disk_pct = 0
        if disk_total and disk_avail:
            t = float(disk_total[0]["value"][1])
            a = float(disk_avail[0]["value"][1])
            disk_pct = round((t - a) / t * 100)

        load = float(load1[0]["value"][1]) if load1 else 0.0
        uptime_days = round(float(uptime[0]["value"][1]) / 86400, 1) if uptime else 0.0
        container_count = len(running_containers)

        return (
            f"🖥️ <b>Host Health Overview:</b>\n"
            f"- <b>Host:</b> <code>volcano</code>\n"
            f"- <b>CPU Load (1m):</b> {load:.2f}\n"
            f"- <b>RAM Usage:</b> {ram_pct}%\n"
            f"- <b>Disk Usage:</b> {disk_pct}%\n"
            f"- <b>Uptime:</b> {uptime_days} days\n"
            f"- <b>Running Containers:</b> {container_count}"
        )
    except Exception as e:
        return f"Error querying Prometheus system health: {str(e)}"
