import html

async def diagnose(target: str, status: str, alert: dict, ctx: dict) -> str:
    icon = "🔥" if status == "firing" else "✅"
    summary = html.escape(ctx.get("summary", ""))
    target_esc = html.escape(target)
    status_str = status.upper()
    return f"{icon} <b>[{status_str}]</b> <code>{target_esc}</code>\n{summary}".strip()
