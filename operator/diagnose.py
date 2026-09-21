import html
import logging

log = logging.getLogger("operator.diagnose")


async def diagnose(target: str, status: str, alert: dict, ctx: dict) -> str:
    status_str = status.upper()
    summary = ctx.get("summary") or alert.get("annotations", {}).get("description") or ""

    if status.lower() == "resolved":
        return f"✅ <b>[RESOLVED]</b> <code>{html.escape(target)}</code>\n{html.escape(summary)}".strip()

    # If firing, run investigation
    try:
        from agent import translate_error_to_incident_card
        sample_error = f"Alert: {target} is {status_str}.\nSummary: {summary}\nLabels: {alert.get('labels', {})}"
        return await translate_error_to_incident_card(target, sample_error)
    except Exception as e:
        log.warning("Agent alert diagnosis failed, falling back: %s", e)
        icon = "🔥" if status == "firing" else "ℹ️"
        return f"{icon} <b>[{status_str}]</b> <code>{html.escape(target)}</code>\n{html.escape(summary)}".strip()
