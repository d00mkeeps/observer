import os
import time
import re
import json
import socket
import http.client
import shutil
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
        req = urllib.request.Request(url, headers={"User-Agent": "CanoObserver/1.0"})
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
        req = urllib.request.Request(url, headers={"User-Agent": "CanoObserver/1.0"})
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
            headers={"Content-Type": "application/json", "User-Agent": "CanoObserver/1.0"},
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
            req = urllib.request.Request(sample_url, headers={"User-Agent": "CanoObserver/1.0"})
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
        req = urllib.request.Request(url, headers={"User-Agent": "CanoObserver/1.0"})
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
        req = urllib.request.Request(url, headers={"User-Agent": "CanoObserver/1.0"})
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


class UnixSocketHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path: str):
        super().__init__("localhost")
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.path)


def _get_docker_containers() -> list[dict]:
    sock_path = "/var/run/docker.sock"
    if not os.path.exists(sock_path):
        return []
    try:
        conn = UnixSocketHTTPConnection(sock_path)
        conn.request("GET", "/containers/json")
        res = conn.getresponse()
        if res.status == 200:
            return json.loads(res.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        log.warning("Failed to query Docker socket: %s", e)
    return []


def _get_host_stats() -> tuple[float, float, int, int]:
    load = 0.0
    try:
        with open("/proc/loadavg", "r") as f:
            load = float(f.read().split()[0])
    except Exception:
        pass

    uptime_days = 0.0
    try:
        with open("/proc/uptime", "r") as f:
            uptime_days = round(float(f.read().split()[0]) / 86400, 1)
    except Exception:
        pass

    ram_pct = 0
    try:
        mem = {}
        with open("/proc/meminfo", "r") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    val = parts[1].strip().split()[0]
                    mem[key] = float(val)
        if "MemTotal" in mem and "MemAvailable" in mem and mem["MemTotal"] > 0:
            ram_pct = round((mem["MemTotal"] - mem["MemAvailable"]) / mem["MemTotal"] * 100)
    except Exception:
        pass

    disk_pct = 0
    try:
        total, used, _ = shutil.disk_usage("/")
        if total > 0:
            disk_pct = round(used / total * 100)
    except Exception:
        pass

    return load, uptime_days, ram_pct, disk_pct


def get_system_health() -> str:
    """Check live metrics for CPU, RAM, Disk, uptime, and running Docker containers across Cano."""
    try:
        load, uptime_days, ram_pct, disk_pct = _get_host_stats()
        docker_containers = _get_docker_containers()

        if docker_containers:
            container_names = []
            for c in docker_containers:
                raw_names = c.get("Names", [])
                name = raw_names[0].lstrip("/") if raw_names else "unknown"
                container_names.append(name)
            container_count = len(docker_containers)
            containers_summary = f"{container_count} active ({', '.join(sorted(container_names)[:6])}{'...' if len(container_names) > 6 else ''})"
        else:
            prom_containers = _prom_sync('time() - container_last_seen{name=~".+"} < 60')
            if prom_containers:
                container_count = len(prom_containers)
                containers_summary = f"{container_count} active (via Prometheus)"
            else:
                containers_summary = "Telemetry daemon unreachable (check host via SSH)"

        return (
            f"🖥️ <b>Host Health Overview:</b>\n"
            f"- <b>Host:</b> <code>cano</code>\n"
            f"- <b>CPU Load (1m):</b> {load:.2f}\n"
            f"- <b>RAM Usage:</b> {ram_pct}%\n"
            f"- <b>Disk Usage:</b> {disk_pct}%\n"
            f"- <b>Uptime:</b> {uptime_days} days\n"
            f"- <b>Running Containers:</b> {containers_summary}"
        )
    except Exception as e:
        return f"Error retrieving system health: {str(e)}"
