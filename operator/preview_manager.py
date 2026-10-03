"""Mobile Dev Preview & Trampoline Session Manager for Cano & Observer.

Coordinates ephemeral Expo Dev Client tunnels, generates Safari trampoline pages,
and dispatches interactive Telegram notifications with one-tap launch and teardown buttons.
"""

from __future__ import annotations
import os
import signal
import asyncio
import logging
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Optional

from notify import send_telegram, edit_telegram_message, answer_callback_query

log = logging.getLogger("operator.preview")

# In-memory session registry: project -> session metadata
_active_previews: dict[str, dict] = {}
_watchdog_tasks: dict[str, asyncio.Task] = {}


def render_trampoline_html(project: str, tunnel_url: str | None = None) -> str:
    """Generate responsive HTML trampoline page for iOS Safari."""
    title = f"{project.capitalize()} Dev Preview" if project else "Dev Preview"
    
    if not tunnel_url:
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} Ended</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0f172a;
      color: #f8fafc;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      margin: 0;
      padding: 20px;
      box-sizing: border-box;
    }}
    .card {{
      background: #1e293b;
      border: 1px solid #334155;
      padding: 36px 28px;
      border-radius: 24px;
      max-width: 440px;
      width: 100%;
      text-align: center;
      box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
    }}
    h1 {{ font-size: 24px; margin-bottom: 12px; }}
    p {{ color: #94a3b8; font-size: 15px; line-height: 1.5; }}
  </style>
</head>
<body>
  <div class="card">
    <div style="font-size: 48px; margin-bottom: 16px;">⏹️</div>
    <h1>Preview Session Ended</h1>
    <p>This development preview tunnel has been closed or expired.</p>
    <p>Ask your Antigravity agent or type <code>/preview</code> in Telegram to spin up a new session.</p>
  </div>
</body>
</html>"""

    # Escape for HTML attributes and JS
    escaped_url = urllib.parse.quote(tunnel_url, safe=":/%?=&-._~+")
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Launching {title}...</title>
  <meta http-equiv="refresh" content="0; url={escaped_url}">
  <script>
    window.location.href = "{escaped_url}";
  </script>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #090d16;
      color: #f8fafc;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      margin: 0;
      padding: 24px;
      box-sizing: border-box;
    }}
    .card {{
      background: #131c2e;
      border: 1px solid #1e293b;
      padding: 40px 28px;
      border-radius: 28px;
      max-width: 460px;
      width: 100%;
      text-align: center;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
    }}
    .logo {{ font-size: 44px; margin-bottom: 12px; }}
    h1 {{ font-size: 22px; font-weight: 700; margin: 0 0 10px 0; letter-spacing: -0.02em; }}
    p.subtitle {{ color: #94a3b8; font-size: 15px; margin: 0 0 28px 0; line-height: 1.5; }}
    .btn-primary {{
      display: block;
      background: #3b82f6;
      color: #ffffff;
      text-decoration: none;
      font-weight: 600;
      font-size: 16px;
      padding: 16px 24px;
      border-radius: 16px;
      margin-bottom: 24px;
      box-shadow: 0 4px 14px 0 rgba(59, 130, 246, 0.39);
    }}
    .fallback-box {{
      background: #0f172a;
      border: 1px solid #1e293b;
      border-radius: 16px;
      padding: 20px 16px;
      text-align: left;
    }}
    .fallback-title {{
      font-size: 13px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #64748b;
      margin-bottom: 12px;
    }}
    .option-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px 0;
      border-bottom: 1px solid #1e293b;
      font-size: 14px;
    }}
    .option-row:last-child {{ border-bottom: none; }}
    .option-link {{ color: #60a5fa; text-decoration: none; font-weight: 500; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">🌋</div>
    <h1>Launching {title}</h1>
    <p class="subtitle">Opening your physical iOS Dev Build with live hot-reloading connected to <code>volc-backend-dev</code>.</p>
    
    <a class="btn-primary" href="{escaped_url}">Tap to Open in Volc</a>

    <div class="fallback-box">
      <div class="fallback-title">Don't have Dev Build installed?</div>
      <div class="option-row">
        <span>Standard App Store app</span>
        <a class="option-link" href="https://apps.apple.com/gb/app/volc/id6751469055" target="_blank">View Store</a>
      </div>
      <div class="option-row">
        <span>Mobile Safari Web Preview</span>
        <a class="option-link" href="https://volc.mileshillary.com" target="_blank">Open Web</a>
      </div>
    </div>
  </div>
</body>
</html>"""


async def start_preview_session(
    project: str = "volc",
    tunnel_url: str = "",
    timeout_minutes: int = 30,
    pid: int | None = None,
) -> dict:
    """Register an active preview session and send an interactive Telegram push notification."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=timeout_minutes)
    
    session_id = f"prev-{project}-{int(now.timestamp())}"
    
    # Trampoline URL served via volc-website on public Cloudflare
    trampoline_url = f"https://volc.mileshillary.com/preview?url={urllib.parse.quote(tunnel_url)}"
    
    # Store session
    session_data = {
        "session_id": session_id,
        "project": project,
        "tunnel_url": tunnel_url,
        "trampoline_url": trampoline_url,
        "pid": pid,
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "message_id": None,
        "chat_id": None,
    }
    _active_previews[project] = session_data

    # Build Telegram card with interactive inline buttons
    text = (
        f"📱 <b>{project.upper()} Dev Preview Live</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Tunnel:</b> <code>Connected</code>\n"
        f"• <b>Backend:</b> <code>volc-backend-dev (:8102)</code>\n"
        f"• <b>Watchdog:</b> Active for <code>{timeout_minutes}m</code>\n\n"
        f"👉 <i>Tap the button below on your iPhone to launch directly into the Dev Build with sub-second hot reloading:</i>"
    )

    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "📱 Open in Volc", "url": trampoline_url},
                {"text": "🛑 Stop Preview", "callback_data": f"preview_stop:{project}"},
            ]
        ]
    }

    try:
        res = await send_telegram(text=text, channel="alerts", reply_markup=reply_markup)
        if isinstance(res, dict) and "result" in res:
            msg = res["result"]
            session_data["message_id"] = msg.get("message_id")
            session_data["chat_id"] = msg.get("chat", {}).get("id")
    except Exception as e:
        log.error("Failed sending Telegram preview notification: %s", e)

    # Schedule watchdog auto-teardown
    if project in _watchdog_tasks and not _watchdog_tasks[project].done():
        _watchdog_tasks[project].cancel()

    async def _watchdog():
        try:
            await asyncio.sleep(timeout_minutes * 60)
            log.info("Watchdog timer expired for preview '%s'. Shutting down...", project)
            await stop_preview_session(project, reason="Auto-closed after 30 minutes of inactivity.")
        except asyncio.CancelledError:
            pass

    _watchdog_tasks[project] = asyncio.create_task(_watchdog())

    return {
        "ok": True,
        "session_id": session_id,
        "trampoline_url": trampoline_url,
        "expires_at": expires_at.isoformat(),
    }


async def stop_preview_session(project: str = "volc", reason: str = "Stopped by user.") -> bool:
    """Terminate the active preview session, kill the Metro process, and edit the Telegram message."""
    session = _active_previews.pop(project, None)
    
    # Cancel watchdog
    wd = _watchdog_tasks.pop(project, None)
    if wd and not wd.done():
        wd.cancel()

    if not session:
        log.info("No active preview session found for '%s'", project)
        return False

    # 1. Terminate Metro PID if known
    pid = session.get("pid")
    if pid and pid > 1:
        try:
            log.info("Killing preview process PID %d for '%s'...", pid, project)
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except Exception as e:
            log.warning("Could not terminate PID %d: %s", pid, e)

    # 2. Update Telegram message to Closed state
    chat_id = session.get("chat_id")
    message_id = session.get("message_id")
    if chat_id and message_id:
        closed_text = (
            f"⏹️ <b>{project.upper()} Dev Preview Closed</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>{reason}</i>\n"
            f"The ephemeral Metro tunnel and server process have been terminated."
        )
        try:
            await edit_telegram_message(chat_id=chat_id, message_id=message_id, text=closed_text)
        except Exception as e:
            log.warning("Failed editing Telegram preview message: %s", e)

    return True


def get_active_preview(project: str = "volc") -> dict | None:
    """Retrieve active session data if not expired."""
    session = _active_previews.get(project)
    if not session:
        return None
    
    # Verify expiration
    expires_at = datetime.fromisoformat(session["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        _active_previews.pop(project, None)
        return None
        
    return session
