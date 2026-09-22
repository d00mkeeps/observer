import os
import html
import asyncio
import logging
import httpx
from notify import send_telegram_reply, send_chat_action
from agent import process_telegram_message
from patch_manager import apply_and_push_patch, reject_patch, get_pending_patches
from commands import execute_deterministic_command
from skills import get_skill_for_command, sync_skills_repo

log = logging.getLogger("operator.telegram")

_CHANNEL_ENV_VARS = [
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_CHAT_ALERTS",
    "TELEGRAM_CHAT_DEPLOYS",
    "TELEGRAM_CHAT_REPORTS",
]


def get_allowed_chat_ids() -> set[str]:
    """Get all authorized chat IDs from environment variables."""
    allowed = set()
    for var in _CHANNEL_ENV_VARS:
        val = os.environ.get(var, "").strip()
        if val:
            allowed.add(str(val))
    return allowed


def get_allowed_user_ids() -> set[str]:
    """Get authorized user IDs from ALLOWED_TELEGRAM_USERS (comma-separated)."""
    raw = os.environ.get("ALLOWED_TELEGRAM_USERS", "").strip()
    if not raw:
        return set()
    return {u.strip() for u in raw.split(",") if u.strip()}


def is_authorized(chat_id: str | int, user_id: str | int | None = None) -> bool:
    """Verify if a message comes from an authorized chat or user."""
    allowed_chats = get_allowed_chat_ids()
    allowed_users = get_allowed_user_ids()

    # If no restrictions are configured in env, allow configured chats only
    if not allowed_chats and not allowed_users:
        return True

    chat_id_str = str(chat_id)
    user_id_str = str(user_id) if user_id is not None else None

    if chat_id_str in allowed_chats:
        return True
    if user_id_str and user_id_str in allowed_users:
        return True

    return False


async def handle_telegram_update(update: dict) -> dict:
    """Parse and process an incoming Telegram update object."""
    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True, "skipped": "no_message"}

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    from_user = message.get("from", {})
    user_id = from_user.get("id")
    user_name = from_user.get("first_name") or from_user.get("username") or "Operator"
    message_id = message.get("message_id")
    text = message.get("text", "").strip()

    if not chat_id:
        return {"ok": False, "error": "missing_chat_id"}

    if not is_authorized(chat_id, user_id):
        log.warning(
            "Unauthorized Telegram interaction attempt from user_id=%s in chat_id=%s",
            user_id,
            chat_id,
        )
        return {"ok": False, "error": "unauthorized"}

    if not text:
        log.info("Received non-text message in chat %s, skipping", chat_id)
        return {"ok": True, "skipped": "non_text"}

    log.info("Received query from %s (user_id=%s, chat_id=%s): %s", user_name, user_id, chat_id, text)

    clean_text = text.strip()
    norm_text = clean_text.lower()
    first_word = norm_text.split()[0] if norm_text else ""
    first_word_clean = first_word[1:] if first_word.startswith("/") else first_word

    # 1. Direct Command Interceptor: approve / /approve
    if first_word_clean == "approve":
        parts = clean_text.split(maxsplit=1)
        patch_id = parts[1].strip() if len(parts) > 1 else ""
        success, reply_msg = apply_and_push_patch(patch_id)
        await send_telegram_reply(chat_id=chat_id, text=reply_msg, reply_to_message_id=message_id)
        return {"ok": True, "status": "approved" if success else "approve_failed"}

    # 2. Direct Command Interceptor: reject / /reject
    if first_word_clean == "reject":
        parts = clean_text.split(maxsplit=1)
        patch_id = parts[1].strip() if len(parts) > 1 else ""
        success, reply_msg = reject_patch(patch_id)
        await send_telegram_reply(chat_id=chat_id, text=reply_msg, reply_to_message_id=message_id)
        return {"ok": True, "status": "rejected"}

    # 3. Direct Command Interceptor: patches / /patches
    if first_word_clean in ("patches", "patch"):
        pending = get_pending_patches()
        if not pending:
            reply_msg = "ℹ️ No pending patches waiting for approval."
        else:
            lines = ["📋 <b>Pending Patches Waiting for Approval:</b>\n"]
            for p in pending:
                lines.append(
                    f"• <code>{p['patch_id']}</code> ({p['project']})\n"
                    f"  Commit: {html.escape(p['commit_message'])}\n"
                    f"  Approve: <code>/approve {p['patch_id']}</code>\n"
                    f"  Reject: <code>/reject {p['patch_id']}</code>\n"
                )
            reply_msg = "\n".join(lines)
        await send_telegram_reply(chat_id=chat_id, text=reply_msg, reply_to_message_id=message_id)
        return {"ok": True, "status": "listed_patches"}

    # 4. Deterministic Commands Interceptor: status, errors, health, help (with subflags, no LLM)
    deterministic_reply = await execute_deterministic_command(clean_text)
    if deterministic_reply is not None:
        log.info("Handled deterministic command '%s' (0 LLM tokens used)", clean_text)
        await send_telegram_reply(chat_id=chat_id, text=deterministic_reply, reply_to_message_id=message_id)
        return {"ok": True, "status": "deterministic_command"}

    # 5. Phase Engineering Skills Interceptor: ideate, spec, plan, build, review, ship (Addy Osmani framework)
    active_skill = None
    if first_word_clean in ("ideate", "spec", "plan", "build", "review", "ship"):
        active_skill = get_skill_for_command(first_word_clean)
        log.info("Activated engineering skill '%s' for command '%s'", active_skill.get("name") if active_skill else "fallback", first_word_clean)

    # 6. Route to Antigravity Agent for conversational reasoning & tool execution (with active skill if set)
    await send_chat_action(chat_id=chat_id, action="typing")

    agent_reply = await process_telegram_message(
        chat_id=chat_id,
        user_text=text,
        user_name=user_name,
        active_skill=active_skill,
    )

    await send_telegram_reply(
        chat_id=chat_id,
        text=agent_reply,
        reply_to_message_id=message_id,
    )
    return {"ok": True, "status": "processed"}


async def register_bot_commands():
    """Register standard commands with Telegram API so they appear in the UI menu."""
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    if not token:
        return
    commands = [
        {"command": "ideate", "description": "Brainstorm & architecture trade-offs"},
        {"command": "spec", "description": "Draft PRD, API contract & requirements"},
        {"command": "plan", "description": "Atomic task breakdown & verification gates"},
        {"command": "build", "description": "TDD sandbox build (Red -> Green)"},
        {"command": "review", "description": "Security, quality & edge-case audit"},
        {"command": "ship", "description": "Deploy patch & release summary"},
        {"command": "status", "description": "Fleet & host resource overview"},
        {"command": "errors", "description": "Loki error audit across all apps"},
        {"command": "docs", "description": "Living API & architecture documentation"},
        {"command": "patches", "description": "Pending sandbox patches awaiting approval"},
        {"command": "health", "description": "Volcano host CPU, RAM, Disk, Uptime"},
        {"command": "help", "description": "Command cheat sheet & guide"},
    ]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{token}/setMyCommands",
                json={"commands": commands},
            )
            if r.status_code == 200:
                log.info("Registered Telegram menu commands successfully")
            else:
                log.warning("setMyCommands returned %d: %s", r.status_code, r.text)
    except Exception as e:
        log.warning("Failed to register Telegram menu commands: %s", e)


async def run_telegram_poller():
    """Background long-polling worker for Telegram updates."""
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    if not token:
        log.warning("Telegram poller not started: TELEGRAM_TOKEN is missing")
        return

    # Sync skills repository in background
    sync_skills_repo()

    # Set up Telegram menu commands in UI
    await register_bot_commands()

    log.info("Starting Telegram long-polling worker...")
    offset = 0

    async with httpx.AsyncClient(timeout=35.0) as client:
        while True:
            try:
                url = f"https://api.telegram.org/bot{token}/getUpdates"
                params = {"offset": offset, "timeout": 25}
                r = await client.get(url, params=params)

                if r.status_code != 200:
                    log.warning("Telegram getUpdates returned status %d: %s", r.status_code, r.text)
                    await asyncio.sleep(5)
                    continue

                data = r.json()
                updates = data.get("result", [])
                for upd in updates:
                    offset = max(offset, upd.get("update_id", 0) + 1)
                    try:
                        await handle_telegram_update(upd)
                    except Exception as e:
                        log.error("Error processing update %s: %s", upd.get("update_id"), e)

            except asyncio.CancelledError:
                log.info("Telegram poller worker cancelled")
                break
            except Exception as e:
                log.error("Exception in Telegram poller loop: %s", e)
                await asyncio.sleep(5)
