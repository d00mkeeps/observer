import os
import re
import html
import time
from datetime import datetime
import httpx
from portfolio import PROJECT_METADATA, PROJECT_CONTAINERS, _recent_deploys
from patch_manager import get_pending_patches

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")
LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100")


async def _prom_query(client: httpx.AsyncClient, expr: str) -> list:
    try:
        r = await client.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": expr}, timeout=8.0)
        if r.status_code == 200:
            return r.json().get("data", {}).get("result", [])
    except Exception:
        pass
    return []


async def _loki_query(client: httpx.AsyncClient, expr: str) -> list:
    try:
        r = await client.get(f"{LOKI_URL}/loki/api/v1/query", params={"query": expr}, timeout=10.0)
        if r.status_code == 200:
            return r.json().get("data", {}).get("result", [])
    except Exception:
        pass
    return []


def _parse_duration(s: str) -> tuple[str, int]:
    """Parse '1h', '6h', '24h', '7d', '30m'."""
    s = s.strip().lower()
    m = re.match(r"^(\d+)([mhd])$", s)
    if not m:
        return "24h", 86400
    val, unit = int(m.group(1)), m.group(2)
    mult = {"m": 60, "h": 3600, "d": 86400}.get(unit, 3600)
    return f"{val}{unit}", val * mult


async def handle_status_command(args: list[str]) -> str:
    """Handle deterministic `status` command and subflags."""
    arg_str = " ".join(args).strip().lower()

    async with httpx.AsyncClient() as client:
        # Running containers
        running_res = await _prom_query(client, 'time() - container_last_seen{name=~".+"} < 60')
        running_names = {r["metric"]["name"] for r in running_res}

        # Host resources
        ram_total_r = await _prom_query(client, "node_memory_MemTotal_bytes")
        ram_avail_r = await _prom_query(client, "node_memory_MemAvailable_bytes")
        disk_total_r = await _prom_query(client, 'node_filesystem_size_bytes{mountpoint="/"}')
        disk_avail_r = await _prom_query(client, 'node_filesystem_avail_bytes{mountpoint="/"}')
        load1_r = await _prom_query(client, "node_load1")
        uptime_r = await _prom_query(client, "time() - node_boot_time_seconds")

        # Loki errors last 24h
        error_res = await _loki_query(
            client,
            'sum by (container) (count_over_time({job=~".+", container!~"obs-.*"}'
            ' |~ "(?i)(level=error|level=fatal|error:|fatal:|exception:|traceback|panic:)" [24h]))',
        )

    # Compute host metrics
    ram_pct = 0
    ram_gb = 0.0
    if ram_total_r and ram_avail_r:
        t = float(ram_total_r[0]["value"][1]) / 1024**3
        a = float(ram_avail_r[0]["value"][1]) / 1024**3
        ram_gb = t - a
        ram_pct = round((t - a) / t * 100)

    disk_pct = 0
    disk_gb = 0.0
    if disk_total_r and disk_avail_r:
        t = float(disk_total_r[0]["value"][1]) / 1024**3
        a = float(disk_avail_r[0]["value"][1]) / 1024**3
        disk_gb = t - a
        disk_pct = round((t - a) / t * 100)

    load = float(load1_r[0]["value"][1]) if load1_r else 0.0
    uptime_s = float(uptime_r[0]["value"][1]) if uptime_r else 0.0
    uptime_days = round(uptime_s / 86400, 1)

    # Map container error counts
    error_counts = {}
    for r in error_res:
        cnt = int(r.get("value", [0, 0])[1])
        cname = r.get("metric", {}).get("container", "unknown")
        if cnt > 0:
            error_counts[cname] = cnt
    total_errors_24h = sum(error_counts.values())

    # --- Subflag: `status host` or `status -h` ---
    if arg_str in ("host", "-h", "--host"):
        lines = [
            "🌋 <b>VOLCANO HOST HEALTH</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            f"💾 <b>RAM:</b> <code>{ram_gb:.1f} GB</code> ({ram_pct}% used)",
            f"💿 <b>Disk:</b> <code>{disk_gb:.1f} GB</code> ({disk_pct}% used)",
            f"⚡ <b>Load (1m):</b> <code>{load:.2f}</code>",
            f"⏱ <b>Uptime:</b> <code>{uptime_days} days</code>",
            f"📦 <b>Active Containers:</b> <code>{len(running_names)}</code>\n",
            "<b>Running Containers:</b>",
        ]
        for name in sorted(running_names):
            lines.append(f"• <code>{html.escape(name)}</code>")
        return "\n".join(lines)

    # --- Subflag: `status errors` or `status -e` ---
    if arg_str.startswith("error") or arg_str.startswith("-e"):
        parts = arg_str.split()
        dur = parts[1] if len(parts) > 1 else "24h"
        return await handle_errors_command([dur])

    # --- Subflag: Specific Project (e.g. `status volc`, `status horizon`, `status clearbox`) ---
    target_project = None
    target_slug = None
    if arg_str and arg_str not in ("-v", "--verbose", "-a", "--all"):
        for slug, meta in PROJECT_METADATA.items():
            if slug == arg_str or arg_str in slug or arg_str in meta["title"].lower():
                target_slug = slug
                target_project = meta
                break
        if not target_project:
            # Check if matching a container name directly
            for cname in running_names:
                if arg_str in cname.lower():
                    # Return specific container status
                    err_cnt = error_counts.get(cname, 0)
                    return (
                        f"📦 <b>Container Status:</b> <code>{html.escape(cname)}</code>\n"
                        f"State: 🟢 Running\n"
                        f"Errors (24h): <code>{err_cnt}</code>"
                    )

    if target_slug and target_project:
        containers = PROJECT_CONTAINERS.get(target_slug, [])
        active_containers = [c for c in containers if c in running_names]
        meta = target_project

        if target_slug in ("tax", "brain", "qa"):
            status_badge = "⚪ Archived (Static)"
        elif containers and len(active_containers) == len(containers):
            status_badge = "🟢 Live (All containers healthy)"
        elif containers and len(active_containers) > 0:
            status_badge = f"🟡 Degraded ({len(active_containers)}/{len(containers)} running)"
        else:
            status_badge = "⚪ Inactive"

        # Project error count
        proj_err_count = sum(error_counts.get(c, 0) for c in containers)

        # Recent deploy for this project
        recent_d = next((d for d in _recent_deploys if d["project"].lower() == target_slug), None)
        deploy_str = "No recent record"
        if recent_d:
            deploy_str = f"{recent_d['status'].upper()} ({recent_d.get('commit', '')[:7]})"

        lines = [
            f"📦 <b>Project: {html.escape(meta['title'])}</b> (<code>{target_slug}</code>)",
            f"🔗 {meta['url']}",
            f"<b>Category:</b> {meta['category']}",
            f"<b>Status:</b> {status_badge}",
            f"<b>Last Deploy:</b> {deploy_str}\n",
            "<b>Containers:</b>",
        ]
        for c in containers:
            is_up = c in running_names
            c_errs = error_counts.get(c, 0)
            status_icon = "🟢" if is_up else "🔴"
            err_badge = f" — ⚠️ <code>{c_errs}</code> errs" if c_errs > 0 else ""
            lines.append(f"• {status_icon} <code>{html.escape(c)}</code>{err_badge}")

        lines.append(f"\n<b>Loki Errors (24h):</b> <code>{proj_err_count} total</code>")
        return "\n".join(lines)

    # --- Subflag: Verbose (`status -v` or `status --all`) ---
    is_verbose = arg_str in ("-v", "--verbose", "-a", "--all")

    pending_patches = get_pending_patches()
    pending_str = f"⚠️ <b>{len(pending_patches)} pending</b> (<code>/patches</code>)" if pending_patches else "0"

    lines = [
        "🌋 <b>VOLCANO STATUS OVERVIEW</b>",
        f"⏱ <i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC</i>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"💾 <b>RAM:</b> <code>{ram_pct}%</code> ({ram_gb:.1f} GB) | 💿 <b>Disk:</b> <code>{disk_pct}%</code> ({disk_gb:.1f} GB)",
        f"⚡ <b>Load:</b> <code>{load:.2f}</code> | ⏱ <b>Up:</b> <code>{uptime_days}d</code> | 📦 <b>Containers:</b> <code>{len(running_names)}</code>",
        "━━━━━━━━━━━━━━━━━━━━",
        "<b>Project Fleet:</b>",
    ]

    for slug, meta in PROJECT_METADATA.items():
        containers = PROJECT_CONTAINERS.get(slug, [])
        active_containers = [c for c in containers if c in running_names]
        proj_errs = sum(error_counts.get(c, 0) for c in containers)
        err_tag = f" ⚠️<code>{proj_errs}e</code>" if proj_errs > 0 else ""

        if slug in ("tax", "brain", "qa"):
            icon = "⚪"
            state_desc = "Archived"
        elif containers and len(active_containers) == len(containers):
            icon = "🟢"
            state_desc = f"{len(active_containers)}/{len(containers)} Live"
        elif containers and len(active_containers) > 0:
            icon = "🟡"
            state_desc = f"{len(active_containers)}/{len(containers)} Degraded"
        else:
            icon = "⚪"
            state_desc = "Stopped"

        lines.append(f"{icon} <b>{html.escape(meta['title'])}</b> (<code>{slug}</code>) — {state_desc}{err_tag}")

        if is_verbose and containers:
            for c in containers:
                c_icon = "🟢" if c in running_names else "🔴"
                c_err = error_counts.get(c, 0)
                c_err_str = f" (<code>{c_err}</code> errs)" if c_err > 0 else ""
                lines.append(f"   └ {c_icon} <code>{html.escape(c)}</code>{c_err_str}")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"📊 <b>Errors (24h):</b> <code>{total_errors_24h:,} total</code> | <b>Patches:</b> {pending_str}")
    if not is_verbose:
        lines.append("\n<i>💡 Subflags: <code>status volc</code>, <code>status -v</code>, <code>status host</code>, <code>errors</code></i>")

    return "\n".join(lines)


async def handle_errors_command(args: list[str]) -> str:
    """Handle deterministic `errors [duration]` command."""
    dur_str = args[0] if args else "24h"
    dur, secs = _parse_duration(dur_str)

    async with httpx.AsyncClient() as client:
        error_res = await _loki_query(
            client,
            f'sum by (container) (count_over_time({{job=~".+", container!~"obs-.*"}}'
            f' |~ "(?i)(level=error|level=fatal|error:|fatal:|exception:|traceback|panic:)" [{dur}]))',
        )

    if not error_res:
        return f"✅ <b>No errors found in Loki across any containers in the last {dur}.</b>"

    counts = {}
    for r in error_res:
        cnt = int(r.get("value", [0, 0])[1])
        cname = r.get("metric", {}).get("container", "unknown")
        if cnt > 0:
            counts[cname] = cnt

    if not counts:
        return f"✅ <b>No errors found in Loki across any containers in the last {dur}.</b>"

    total = sum(counts.values())
    lines = [
        f"📊 <b>Loki Error Audit (Last {dur}):</b>",
        f"Total Errors: <code>{total:,}</code> across {len(counts)} container(s)\n",
    ]

    for cname, count in sorted(counts.items(), key=lambda x: -x[1]):
        lines.append(f"• <b>{html.escape(cname)}</b>: <code>{count:,}</code> errors")

    lines.append(f"\n<i>💡 Ask me: 'Inspect errors in {list(counts.keys())[0]}' for a deep root-cause diagnosis.</i>")
    return "\n".join(lines)


def handle_help_command() -> str:
    """Return deterministic cheat sheet and command guide."""
    return (
        "🤖 <b>Observer / Airwavbot Commands</b>\n\n"
        "<b>⚡ Deterministic Commands (Instant, No LLM):</b>\n"
        "• <code>status</code> — Overview of Volcano host, projects & errors\n"
        "• <code>status &lt;project&gt;</code> — Detail for project (e.g. <code>status volc</code>, <code>status horizon</code>)\n"
        "• <code>status -v</code> / <code>status --all</code> — Expanded list with all container statuses\n"
        "• <code>status host</code> / <code>health</code> — Host RAM, Disk, Load, Uptime & containers\n"
        "• <code>errors [1h|24h|7d]</code> — Direct Loki error count across all apps\n"
        "• <code>patches</code> — List code patches waiting for your approval\n"
        "• <code>/approve &lt;id&gt;</code> — Commit verified fix, push to GitHub & deploy\n"
        "• <code>/reject &lt;id&gt;</code> — Discard pending sandbox patch\n"
        "• <code>help</code> — Show this cheat sheet\n\n"
        "<b>🧠 Conversational AI Assistant:</b>\n"
        "Ask anything in natural language! For example:\n"
        "• <i>\"What's causing the errors in supreme-octo-doodle-api?\"</i>\n"
        "• <i>\"Check the Horizon repo and add a test for the price parser\"</i>\n"
        "• <i>\"Show me the last 10 log lines for clearbox-site\"</i>\n\n"
        "<i>Note: Commands work with or without a leading slash (<code>/status</code> or <code>status</code>).</i>"
    )


async def execute_deterministic_command(text: str) -> str | None:
    """Evaluate text for deterministic commands. Returns response string or None if LLM is needed."""
    raw = text.strip()
    if not raw:
        return None

    # Remove optional leading slash
    clean = raw[1:] if raw.startswith("/") else raw
    parts = clean.split()
    if not parts:
        return None

    cmd = parts[0].lower()
    args = parts[1:]

    if cmd in ("status", "stat", "st"):
        return await handle_status_command(args)

    if cmd in ("errors", "error", "err"):
        return await handle_errors_command(args)

    if cmd in ("health", "host"):
        return await handle_status_command(["host"])

    if cmd in ("help", "commands", "start", "?"):
        return handle_help_command()

    return None
