import os
import html
import asyncio
import logging
import httpx
from notify import send_telegram_reply, send_chat_action
from agent import process_telegram_message

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
    """Parse and process an incoming Telegram update object.

    Currently returns a mock echo response. Later this will route
    to the Antigravity read-only agent.
    """
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

    # Show typing indicator while agent investigates and reasons
    await send_chat_action(chat_id=chat_id, action="typing")

    # Generate response via Antigravity Agent
    agent_reply = await process_telegram_message(
        chat_id=chat_id,
        user_text=text,
        user_name=user_name,
    )

    await send_telegram_reply(
        chat_id=chat_id,
        text=agent_reply,
        reply_to_message_id=message_id,
    )
    return {"ok": True, "status": "processed"}



async def run_telegram_poller():
    """Background long-polling worker for Telegram updates.

    Enabled by setting TELEGRAM_POLLING=true in .env.
    """
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    if not token:
        log.warning("Telegram poller not started: TELEGRAM_TOKEN is missing")
        return

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
