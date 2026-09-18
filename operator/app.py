import logging
import asyncio
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from notify import send_telegram
from context import gather_context
from diagnose import diagnose
from report import send_daily_report, generate_daily_report
from monitor import run_error_monitor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("operator")


async def run_daily_scheduler():
    log.info("Starting daily report scheduler (scheduled for 09:00 daily)...")
    while True:
        try:
            now = datetime.now()
            # Calculate next 09:00 AM
            target = now.replace(hour=9, minute=0, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            seconds_until = (target - now).total_seconds()
            log.info("Next daily report scheduled in %.1f hours (%s)", seconds_until / 3600, target.strftime("%Y-%m-%d %H:%M:%S"))
            await asyncio.sleep(seconds_until)
            await send_daily_report()
        except asyncio.CancelledError:
            log.info("Daily scheduler cancelled")
            break
        except Exception as e:
            log.error("Error in daily scheduler: %s", e)
            await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: launch background workers
    monitor_task = asyncio.create_task(run_error_monitor())
    scheduler_task = asyncio.create_task(run_daily_scheduler())
    yield
    # Shutdown: gracefully cancel workers
    monitor_task.cancel()
    scheduler_task.cancel()
    await asyncio.gather(monitor_task, scheduler_task, return_exceptions=True)


app = FastAPI(title="Observer Operator", lifespan=lifespan)


@app.post("/alert")
async def receive_alert(request: Request):
    payload = await request.json()
    for alert in payload.get("alerts", []):
        labels = alert.get("labels", {})
        target = labels.get("name") or labels.get("alertname", "unknown")
        status = alert.get("status", "unknown")
        log.info("Alert received: %s %s", status, target)

        ctx = await gather_context(target, alert)
        message = await diagnose(target, status, alert, ctx)
        await send_telegram(message)
    return {"ok": True}


@app.post("/deploy")
async def receive_deploy(request: Request):
    data = await request.json()
    project = data.get("project", "unknown-service")
    status = data.get("status", "success").lower()
    commit = data.get("commit", "")
    actor = data.get("actor", "")
    details = data.get("message", "")

    icon = "🚀" if status == "success" else "❌"
    header = f"{icon} [DEPLOY {status.upper()}] *{project}*"

    lines = [header]
    if commit:
        lines.append(f"• Commit: `{commit}`")
    if actor:
        lines.append(f"• Triggered by: `{actor}`")
    if details:
        lines.append(f"• Details: {details}")

    message = "\n".join(lines)
    log.info("Deploy event received for %s (%s)", project, status)
    await send_telegram(message)
    return {"ok": True}


@app.post("/report")
@app.get("/report")
async def trigger_report():
    report_text = await generate_daily_report()
    await send_telegram(report_text)
    return {"ok": True, "report": report_text}


@app.get("/health")
async def health():
    return {"ok": True}
