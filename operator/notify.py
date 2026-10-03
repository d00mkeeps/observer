import logging
import os
import re
import json
import urllib.request
try:
    import httpx
except ImportError:
    httpx = None

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


def _send_telegram_sync(token: str, payload: dict) -> bool:
    """Fallback synchronous Telegram message dispatcher via urllib."""
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={"Content-Type": "application/json", "User-Agent": "CanoObserver/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            return resp.status == 200
    except Exception as e:
        log.warning("urllib Telegram send error: %s", e)
        return False


async def send_telegram(
    text: str,
    channel: str = "default",
    reply_markup: dict | None = None,
) -> dict | None:
    """Send an HTML-formatted message to a Telegram chat, optionally with reply_markup."""
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = _chat_id_for(channel)

    if not token or not chat_id:
        log.warning(
            "Telegram notification skipped (channel=%s): "
            "TELEGRAM_TOKEN or chat_id not configured",
            channel,
        )
        return None

    # Cap message size at 4000 characters for Telegram limits
    if len(text) > 4000:
        text = text[:3950] + "\n\n<i>… (message truncated)</i>"

    payload = {
        "chat_id":    chat_id,
        "text":       text,
        "parse_mode": "HTML",
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    if httpx is not None:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json=payload,
            )
            if r.status_code == 200:
                return r.json()
            if r.status_code == 400:
                log.warning("Telegram HTML send error (%s), falling back to plain text", r.text)
                payload["text"] = _strip_html_tags(text)
                payload.pop("parse_mode", None)
                r2 = await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json=payload,
                )
                if r2.status_code == 200:
                    return r2.json()
    else:
        _send_telegram_sync(token, payload)
    return None


async def edit_telegram_message(
    chat_id: str | int,
    message_id: int,
    text: str,
    reply_markup: dict | None = None,
) -> dict | None:
    """Edit an existing Telegram message with updated text and optional reply_markup."""
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    if not token or not chat_id or not message_id:
        return None

    if len(text) > 4000:
        text = text[:3950] + "\n\n<i>… (message truncated)</i>"

    payload = {
        "chat_id":    chat_id,
        "message_id": message_id,
        "text":       text,
        "parse_mode": "HTML",
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    if httpx is not None:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(
                    f"https://api.telegram.org/bot{token}/editMessageText",
                    json=payload,
                )
                if r.status_code == 200:
                    return r.json()
                if r.status_code == 400:
                    log.warning("Telegram edit HTML error (%s), falling back to plain text", r.text)
                    payload["text"] = _strip_html_tags(text)
                    payload.pop("parse_mode", None)
                    r2 = await client.post(
                        f"https://api.telegram.org/bot{token}/editMessageText",
                        json=payload,
                    )
                    if r2.status_code == 200:
                        return r2.json()
        except Exception as e:
            log.warning("Exception in edit_telegram_message: %s", e)
    return None


async def answer_callback_query(
    callback_query_id: str,
    text: str = "",
    show_alert: bool = False,
) -> bool:
    """Acknowledge a Telegram callback query."""
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    if not token or not callback_query_id:
        return False

    payload = {
        "callback_query_id": callback_query_id,
        "text":              text,
        "show_alert":        show_alert,
    }
    if httpx is not None:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.post(
                    f"https://api.telegram.org/bot{token}/answerCallbackQuery",
                    json=payload,
                )
                return r.status_code == 200
        except Exception as e:
            log.warning("Exception in answer_callback_query: %s", e)
    return False


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

    if httpx is not None:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json=payload,
            )
            if r.status_code == 400:
                log.warning("Telegram reply HTML parse error (%s); falling back to plain text", r.text)
                payload["text"] = _strip_html_tags(text)
                payload.pop("parse_mode", None)
                await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json=payload,
                )
    else:
        _send_telegram_sync(token, payload)


async def send_chat_action(chat_id: str | int, action: str = "typing") -> None:
    """Send a chat action like 'typing' to Telegram."""
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    if not token or not chat_id:
        return
    if httpx is not None:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    f"https://api.telegram.org/bot{token}/sendChatAction",
                    json={"chat_id": chat_id, "action": action},
                )
        except Exception:
            pass
