import logging
import os
import httpx

log = logging.getLogger("operator.notify")

# Map channel names to env var names.
# Add a new group chat: create the group, add the bot, get the chat_id,
# add TELEGRAM_CHAT_<NAME>=<chat_id> to .env, add the key here.
_CHANNEL_ENV_VARS = {
    "alerts":  "TELEGRAM_CHAT_ALERTS",
    "deploys": "TELEGRAM_CHAT_DEPLOYS",
    "reports": "TELEGRAM_CHAT_REPORTS",
}
_DEFAULT_CHAT_ENV_VAR = "TELEGRAM_CHAT_ID"


def _chat_id_for(channel: str) -> str:
    """Resolve a channel name to a Telegram chat_id.

    Falls back to TELEGRAM_CHAT_ID if the specific channel isn't configured,
    so everything works with a single chat until you're ready to split.
    """
    env_var = _CHANNEL_ENV_VARS.get(channel, _DEFAULT_CHAT_ENV_VAR)
    specific = os.environ.get(env_var, "").strip()
    return specific or os.environ.get(_DEFAULT_CHAT_ENV_VAR, "").strip()


async def send_telegram(text: str, channel: str = "default") -> None:
    """Send an HTML-formatted message to a Telegram chat.

    Args:
        text:    Message body. Use HTML tags: <b>, <i>, <code>, <pre>.
        channel: Logical channel name ("alerts", "deploys", "reports").
                 Resolves to the matching TELEGRAM_CHAT_* env var,
                 falling back to TELEGRAM_CHAT_ID if not set.
    """
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = _chat_id_for(channel)

    if not token or not chat_id:
        log.warning(
            "Telegram notification skipped (channel=%s): "
            "TELEGRAM_TOKEN or chat_id not configured",
            channel,
        )
        return

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id":    chat_id,
                "text":       text,
                "parse_mode": "HTML",
            },
        )
        r.raise_for_status()
