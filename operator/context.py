async def gather_context(target: str, alert: dict) -> dict:   # /operator/context.gather_context
    # v2: query Loki (log window), Prometheus (metrics), read /cards/{target}.md
    return {"summary": alert.get("annotations", {}).get("summary", "")}
