import logging
from fastapi import FastAPI, Request
from notify import send_telegram
from context import gather_context
from diagnose import diagnose

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("operator")
app = FastAPI()

@app.post("/alert")                       # /operator/app.receive_alert
async def receive_alert(request: Request):
    payload = await request.json()
    for alert in payload.get("alerts", []):
        labels = alert.get("labels", {})
        target = labels.get("name") or labels.get("alertname", "unknown")
        status = alert.get("status", "unknown")
        log.info("alert received: %s %s", status, target)

        ctx = await gather_context(target, alert)      # v1: minimal
        message = await diagnose(target, status, alert, ctx)  # v1: format only
        await send_telegram(message)
    return {"ok": True}

@app.get("/health")                        # /operator/app.health
async def health():
    return {"ok": True}
