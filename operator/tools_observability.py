import os
import time
import logging
import httpx

log = logging.getLogger("operator.tools.observability")

LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100")
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")


def _prom_sync(expr: str) -> list:
    """Synchronously query Prometheus."""
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": expr})
            if r.status_code == 200:
                return r.json().get("data", {}).get("result", [])
    except Exception as e:
        log.warning("Sync Prometheus query failed: %s", e)
    return []


def _loki_sync(expr: str) -> list:
    """Synchronously query Loki."""
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(f"{LOKI_URL}/loki/api/v1/query", params={"query": expr})
            if r.status_code == 200:
                return r.json().get("data", {}).get("result", [])
    except Exception as e:
        log.warning("Sync Loki query failed: %s", e)
    return []


def get_error_frequency(container: str, days: int = 7) -> str:
    """Check how often an error or log pattern occurred in a container over time (1h, 24h, 7d).

    Args:
        container: Container name (e.g. 'supreme-octo-doodle-api', 'volc-website').
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

    url = f"{LOKI_URL}/loki/api/v1/query_range?query={query}&start={start_ns}&end={end_ns}&limit={limit}"
    
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(url)
            if r.status_code != 200:
                return f"Loki query returned status {r.status_code}: {r.text}"
            
            data = r.json()
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
        return f"Error querying Loki logs: {str(e)}"


def get_system_health() -> str:
    """Get current host CPU, RAM, Disk, Uptime, and list of running containers."""
    try:
        ram_t = _prom_sync("node_memory_MemTotal_bytes")
        ram_a = _prom_sync("node_memory_MemAvailable_bytes")
        disk_t = _prom_sync('node_filesystem_size_bytes{mountpoint="/"}')
        disk_a = _prom_sync('node_filesystem_avail_bytes{mountpoint="/"}')
        load1 = _prom_sync("node_load1")
        uptime = _prom_sync("time() - node_boot_time_seconds")
        running = _prom_sync('time() - container_last_seen{name=~".+"} < 60')

        ram_pct = 0
        if ram_t and ram_a:
            t = float(ram_t[0]["value"][1])
            a = float(ram_a[0]["value"][1])
            ram_pct = round((t - a) / t * 100)

        disk_pct = 0
        if disk_t and disk_a:
            t = float(disk_t[0]["value"][1])
            a = float(disk_a[0]["value"][1])
            disk_pct = round((t - a) / t * 100)

        load_val = float(load1[0]["value"][1]) if load1 else 0.0
        uptime_days = round(float(uptime[0]["value"][1]) / 86400, 1) if uptime else 0.0
        running_names = [r["metric"].get("name", "unknown") for r in running]

        return (
            f"Volcano Host Health:\n"
            f"- RAM Used: {ram_pct}%\n"
            f"- Disk Used: {disk_pct}%\n"
            f"- Load (1m): {load_val:.2f}\n"
            f"- Uptime: {uptime_days} days\n"
            f"- Running Containers ({len(running_names)}): {', '.join(running_names)}"
        )
    except Exception as e:
        return f"Error querying Prometheus health: {str(e)}"
