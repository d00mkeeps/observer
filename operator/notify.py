import logging
import os
import re
import httpx

log = logging.getLogger("operator.notify")

_CHANNEL_ENV_VARS = {
    "alerts":  "TELEGRAM_CHAT_ALERTS",
    "deploys": "TELEGRAM_CHAT_DEPLOYS",
    "reports": "TELEGRAM_CHAT_REPORTS",
}
_DEFAULT_CHAT_ENV_VAR = "TELEGRAM_CHAT_ID"


def _chat_id_for(channel: str) -> str:
    env_var = _CHANNEL_ENV_VARS.get(channel, _DEFAULT_CHAT_ENV_VAR)
    specific = os.environ.get(env_var, "").strip()
    return specific or os.environ.get(_DEFAULT_CHAT_ENV_VAR, "").strip()


def _strip_html_tags(text: str) -> str:
    """Strip basic HTML tags if HTML parsing fails."""
    return re.sub(r"<[^>]+>", "", text)


async def send_telegram(text: str, channel: str = "default") -> None:
    """Send an HTML-formatted message to a Telegram chat."""
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = _chat_id_for(channel)

    if not token or not chat_id:
        log.warning(
            "Telegram notification skipped (channel=%s): "
            "TELEGRAM_TOKEN or chat_id not configured",
            channel,
        )
        return

    # Cap message size at 4000 characters for Telegram limits
    if len(text) > 4000:
        text = text[:3950] + "\n\n<i>… (message truncated)</i>"

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id":    chat_id,
                "text":       text,
                "parse_mode": "HTML",
            },
        )
        # If HTML parse error, fallback to plain text
        if r.status_code == 400:
            log.warning("Telegram HTML send error (%s), falling back to plain text", r.text)
            r = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text":    _strip_html_tags(text),
                },
            )
        r.raise_for_status()


async def send_telegram_reply(
    chat_id: str | int,
    text: str,
    reply_to_message_id: int | None = None,
) -> None:
    """Send an HTML-formatted reply to a specific Telegram chat_id."""
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    if not token or not chat_id:
        log.warning("Telegram reply skipped: TELEGRAM_TOKEN or chat_id not configured")
        return

    # Cap message size at 4000 characters
    if len(text) > 4000:
        text = text[:3950] + "\n\n<i>… (message truncated)</i>"

    payload = {
        "chat_id":    chat_id,
        "text":       text,
        "parse_mode": "HTML",
    }
    if reply_to_message_id is not None:
        payload["reply_parameters"] = {"message_id": reply_to_message_id}

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json=payload,
        )
        # If HTML parse error or malformed tag, retry without HTML parse_mode
        if r.status_code == 400:
            log.warning("Telegram reply HTML parse error (%s); falling back to plain text", r.text)
            payload["text"] = _strip_html_tags(text)
            payload.pop("parse_mode", None)
            r = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json=payload,
            )
        r.raise_for_status()


async def send_chat_action(chat_id: str | int, action: str = "typing") -> None:
    """Send a chat action like 'typing' to Telegram."""
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    if not token or not chat_id:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendChatAction",
                json={"chat_id": chat_id, "action": action},
            )
    except Exception:
        pass
