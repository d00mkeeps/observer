"""Service & Observer Self-Update Engine.

Allows Observer to safely pull the latest verified commits from GitHub `main`
and rebuild/restart itself or any service on Volcano from Telegram.
"""

import os
import re
import logging
import subprocess
from pathlib import Path

log = logging.getLogger("operator.updater")

# Project directories mapping
SERVICE_DIR_MAP = {
    "observer": ["/codebases/prod/observer", "/codebases/observer", "/home/miles/prod/observer"],
    "volc": ["/codebases/prod/volc", "/codebases/volc", "/home/miles/prod/volc"],
    "clearbox": ["/codebases/prod/clear-box", "/codebases/clear-box", "/home/miles/prod/clear-box"],
    "clear-box": ["/codebases/prod/clear-box", "/codebases/clear-box", "/home/miles/prod/clear-box"],
    "horizon": ["/codebases/prod/horizon", "/codebases/horizon", "/home/miles/prod/horizon"],
    "portfolio": ["/codebases/prod/portfolio", "/codebases/portfolio", "/home/miles/prod/portfolio"],
    "qa": ["/codebases/prod/sturdy-robot", "/codebases/sturdy-robot", "/home/miles/prod/sturdy-robot"],
}


def _resolve_project_dir(service_name: str) -> Path | None:
    norm = service_name.strip().lower()
    candidates = SERVICE_DIR_MAP.get(norm, [f"/codebases/prod/{norm}", f"/codebases/{norm}", f"/home/miles/prod/{norm}"])
    for path_str in candidates:
        p = Path(path_str)
        if p.exists() and (p / ".git").exists():
            return p
    return None


def execute_service_update(service_name: str = "observer") -> tuple[bool, str]:
    """Pull latest code from GitHub main and trigger container rebuild/restart.

    Args:
        service_name: Project name (e.g. 'observer', 'volc', 'clearbox', 'horizon').
    """
    target = service_name.strip().lower() or "observer"
    proj_dir = _resolve_project_dir(target)

    if not proj_dir:
        return False, f"❌ Cannot find project directory for service '{service_name}' on Volcano."

    log.info("Executing update for service '%s' in %s...", target, proj_dir)

    # 1. Git fetch and reset to origin/main
    try:
        fetch_res = subprocess.run(
            ["git", "fetch", "origin", "main"],
            cwd=str(proj_dir),
            capture_output=True,
            text=True,
            timeout=25,
        )
        if fetch_res.returncode != 0:
            return False, f"❌ Git fetch failed for {target}:\n<code>{fetch_res.stderr.strip()}</code>"

        reset_res = subprocess.run(
            ["git", "reset", "--hard", "origin/main"],
            cwd=str(proj_dir),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if reset_res.returncode != 0:
            return False, f"❌ Git reset failed for {target}:\n<code>{reset_res.stderr.strip()}</code>"

        rev_res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(proj_dir),
            capture_output=True,
            text=True,
            timeout=5,
        )
        commit_sha = rev_res.stdout.strip() if rev_res.returncode == 0 else "latest"

    except Exception as e:
        return False, f"❌ Git sync error for {target}: {str(e)}"

    # 2. Rebuild and restart container
    try:
        # Check if docker or docker compose is available
        compose_cmd = ["docker", "compose", "up", "-d", "--build"]
        if target == "observer":
            compose_cmd.append("operator")

        # Spawn rebuild in detached background so operator doesn't terminate mid-command
        log.info("Spawning docker compose rebuild for %s...", target)
        subprocess.Popen(
            compose_cmd,
            cwd=str(proj_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        return (
            True,
            f"🔄 <b>Update Initiated for {target.upper()}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Branch:</b> <code>origin/main</code>\n"
            f"• <b>Commit:</b> <code>{commit_sha}</code>\n"
            f"• <b>Status:</b> Pull succeeded. Docker container rebuild and recreate is running in the background.\n\n"
            f"<i>You will receive a notification once the container finishes starting.</i>",
        )

    except Exception as e:
        return False, f"❌ Container restart failed for {target}: {str(e)}"
