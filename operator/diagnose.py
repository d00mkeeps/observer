async def diagnose(target, status, alert, ctx) -> str:        # /operator/diagnose.diagnose
    # v2: OpenRouter call with ctx -> probable cause + suggested first command
    icon = "🔥" if status == "firing" else "✅"
    return f"{icon} [{status.upper()}] {target}\n{ctx.get('summary','')}".strip()
