import os
import time
import asyncio
import logging
import urllib.parse
from datetime import datetime
import httpx
from notify import send_telegram

log = logging.getLogger("operator.monitor")

LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100")
POLL_INTERVAL_SECONDS = int(os.environ.get("ERROR_POLL_INTERVAL", "60"))
DEBOUNCE_SECONDS = int(os.environ.get("ERROR_DEBOUNCE_SECONDS", "300"))  # 5 minutes per container

# Track last alert time and suppressed counts per container
_last_alert_time = {}
_suppressed_counts = {}
_seen_line_hashes = set()


def _get_line_hash(container: str, timestamp_ns: str, line: str) -> int:
    return hash((container, timestamp_ns, line.strip()))


async def check_for_errors(client: httpx.AsyncClient, start_ns: int, end_ns: int) -> int:
    query = urllib.parse.quote(
        '{job=~".+", container!~"obs-.*"} |~ "(?i)(level=error|level=fatal|error:|fatal:|exception:|traceback|panic:)"'
    )
    url = f"{LOKI_URL}/loki/api/v1/query_range?query={query}&start={start_ns}&end={end_ns}&limit=50"

    try:
        r = await client.get(url, timeout=15.0)
        if r.status_code != 200:
            log.warning("Loki query returned status %s: %s", r.status_code, r.text)
            return end_ns

        data = r.json()
        results = data.get("data", {}).get("result", [])
        if not results:
            return end_ns

        now = time.time()

        for stream in results:
            container = stream.get("stream", {}).get("container", "unknown")
            values = stream.get("values", [])

            new_lines = []
            for ts_str, line in values:
                h = _get_line_hash(container, ts_str, line)
                if h in _seen_line_hashes:
                    continue
                _seen_line_hashes.add(h)
                new_lines.append((ts_str, line.strip()))

            if not new_lines:
                continue

            # Keep cache size bounded
            if len(_seen_line_hashes) > 10000:
                _seen_line_hashes.clear()

            last_alert = _last_alert_time.get(container, 0)
            if now - last_alert < DEBOUNCE_SECONDS:
                _suppressed_counts[container] = _suppressed_counts.get(container, 0) + len(new_lines)
                log.info("Suppressed %d error log(s) for container %s (debounced)", len(new_lines), container)
                continue

            suppressed = _suppressed_counts.pop(container, 0)
            _last_alert_time[container] = now

            # Select most representative error line (first line)
            sample_line = new_lines[0][1]
            if len(sample_line) > 400:
                sample_line = sample_line[:400] + "..."

            msg_parts = [
                f"🚨 [APP ERROR] `{container}`",
                f"🕒 `{datetime.now().strftime('%H:%M:%S')}`",
                f"```\n{sample_line}\n```",
            ]
            if suppressed > 0:
                msg_parts.append(f"ℹ️ _(+{suppressed} similar errors occurred in the last {DEBOUNCE_SECONDS // 60}m)_")

            message = "\n".join(msg_parts)
            await send_telegram(message)
            log.info("Sent error alert for %s", container)

    except Exception as e:
        log.warning("Error checking Loki for logs: %s", e)

    return end_ns


async def run_error_monitor():
    log.info("Starting background real-time error monitor (polling every %ds)...", POLL_INTERVAL_SECONDS)
    # Start looking from now onwards
    last_timestamp_ns = int(time.time() * 1e9)

    async with httpx.AsyncClient() as client:
        while True:
            try:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                now_ns = int(time.time() * 1e9)
                # Overlap by 5 seconds to catch any in-flight ingestion
                start_ns = max(0, last_timestamp_ns - int(5 * 1e9))
                last_timestamp_ns = await check_for_errors(client, start_ns, now_ns)
            except asyncio.CancelledError:
                log.info("Error monitor cancelled")
                break
            except Exception as e:
                log.error("Unexpected exception in error monitor loop: %s", e)
                await asyncio.sleep(10)
