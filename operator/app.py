import html
import logging
import asyncio
from datetime import datetime, timedelta
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from notify import send_telegram
from context import gather_context
from diagnose import diagnose
from report import send_daily_report, generate_daily_report
from monitor import run_error_monitor
from portfolio import get_system_status, record_deploy_event
from tools_observability import push_loki_log
from cost_tracker import cost_tracker
from telegram_handler import handle_telegram_update, run_telegram_poller

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("operator")


async def run_daily_scheduler():
    log.info("Starting daily report scheduler (scheduled for 09:00 daily)...")
    while True:
        try:
            now = datetime.now()
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
    workers = [
        asyncio.create_task(run_error_monitor()),
        asyncio.create_task(run_daily_scheduler()),
    ]
    if os.environ.get("TELEGRAM_POLLING", "false").lower() == "true":
        log.info("TELEGRAM_POLLING is enabled; starting Telegram poller worker")
        workers.append(asyncio.create_task(run_telegram_poller()))

    yield
    # Shutdown: gracefully cancel workers
    for w in workers:
        w.cancel()
    await asyncio.gather(*workers, return_exceptions=True)


app = FastAPI(title="Observer Operator", lifespan=lifespan)

# Enable CORS for portfolio & admin dashboards
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/alert")
async def receive_alert(request: Request):
    """Receive and diagnose Prometheus Alertmanager alerts, translating them into 5-point incident cards and dispatching to Telegram."""
    payload = await request.json()
    for alert in payload.get("alerts", []):
        labels = alert.get("labels", {})
        target = labels.get("name") or labels.get("alertname", "unknown")
        status = alert.get("status", "unknown")
        log.info("Alert received: %s %s", status, target)

        ctx = await gather_context(target, alert)
        message = await diagnose(target, status, alert, ctx)
        await send_telegram(message, channel="alerts")
    return {"ok": True}


@app.post("/deploy")
async def receive_deploy(request: Request):
    """Receive deployment notifications from GitHub Actions workflows, update portfolio state, and post summary to Telegram."""
    data = await request.json()
    project = html.escape(data.get("project", "unknown-service"))
    status = data.get("status", "success").lower()
    commit = html.escape(data.get("commit", ""))
    actor = html.escape(data.get("actor", ""))
    details = html.escape(data.get("message", ""))

    # Record in portfolio tracker & cost ledger
    record_deploy_event(project=project, status=status, commit=commit, actor=actor, message=details)
    cost_tracker.record_ci_usage(app=project, duration_seconds=45)

    icon = "🚀" if status == "success" else "❌"
    lines = [f"{icon} <b>Deploy {status.upper()}</b> — <code>{project}</code>"]
    if commit:
        lines.append(f"  • commit: <code>{commit}</code>")
    if actor:
        lines.append(f"  • by: <code>{actor}</code>")
    if details:
        lines.append(f"  • {details}")

    message = "\n".join(lines)
    log.info("Deploy event received for %s (%s)", project, status)
    await send_telegram(message, channel="deploys")
    return {"ok": True}


@app.post("/ci/failure")
async def receive_ci_failure(request: Request):
    """Receive GitHub Actions workflow/CI failures, log directly to Loki, and dispatch incident alert."""
    data = await request.json()
    repo = html.escape(data.get("repository", "unknown-repo"))
    workflow = html.escape(data.get("workflow", "CI Pipeline"))
    run_id = html.escape(str(data.get("run_id", "")))
    run_num = html.escape(str(data.get("run_number", "")))
    actor = html.escape(data.get("actor", "unknown"))
    branch = html.escape(data.get("branch", "main"))
    commit = html.escape(data.get("commit", "")[:7])
    error_step = html.escape(data.get("error_step", "Execution Failure"))
    details = html.escape(data.get("message", "Pipeline step exited with non-zero status."))
    run_url = html.escape(data.get("run_url", f"https://github.com/{repo}/actions/runs/{run_id}" if run_id else ""))

    # 1. Push structured error stream to Loki
    log_msg = f"ERROR: GitHub Actions CI Failure in {repo} | Workflow: {workflow} (#{run_num}) | Step: {error_step} | Commit: {commit} by {actor} | Details: {details} | Run URL: {run_url}"
    loki_labels = {
        "job": "github-actions",
        "container": "github-actions",
        "repository": repo,
        "workflow": workflow,
        "level": "error",
    }
    push_loki_log(labels=loki_labels, message=log_msg)

    # 2. Record failure in portfolio tracker & cost ledger
    project_slug = repo.split("/")[-1].lower() if "/" in repo else repo.lower()
    record_deploy_event(
        project=project_slug,
        status="failure",
        commit=commit,
        actor=actor,
        message=f"CI Failed: {error_step} ({workflow})",
    )
    cost_tracker.record_ci_usage(app=project_slug, duration_seconds=30)

    # 3. Dispatch Incident Alert Card to Telegram (#alerts)
    alert_lines = [
        f"🚨 <b>CI/CD Pipeline Failure</b> — <code>{repo}</code>",
        f"• <b>Workflow:</b> <i>{workflow}</i> (#{run_num})",
        f"• <b>Failed Step:</b> <code>{error_step}</code>",
        f"• <b>Branch/Commit:</b> <code>{branch}</code> @ <code>{commit}</code> by <i>{actor}</i>",
    ]
    if details and details != "Pipeline step exited with non-zero status.":
        alert_lines.append(f"• <b>Error:</b> <pre>{details[:250]}</pre>")
    if run_url:
        alert_lines.append(f"🔗 <a href=\"{run_url}\">View GitHub Actions Run</a>")

    alert_msg = "\n".join(alert_lines)
    log.warning("CI failure received from %s (workflow: %s, step: %s)", repo, workflow, error_step)
    await send_telegram(alert_msg, channel="alerts")
    return {"ok": True, "logged_to_loki": True}


@app.get("/costs")
async def get_costs_endpoint(app: str | None = None, timeframe: str = "month"):
    """Retrieve Volcano ecosystem cost breakdown by app and service."""
    return cost_tracker.get_summary(timeframe=timeframe)


@app.get("/status")
async def status_endpoint():
    """Retrieve full Volcano fleet status JSON, container health, Prometheus resource gauges, and recent deploy history."""
    return await get_system_status()


@app.post("/report")
@app.get("/report")
async def trigger_report():
    """Trigger on-demand generation and Telegram broadcast of the daily 24h health and performance report."""
    report_text = await generate_daily_report()
    await send_telegram(report_text, channel="reports")
    return {"ok": True, "report": report_text}


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    """Receive incoming Telegram updates via Webhook mode (authenticated with secret token header)."""
    secret = os.environ.get("TELEGRAM_SECRET_TOKEN", "").strip()
    if secret and x_telegram_bot_api_secret_token != secret:
        log.warning("Invalid Telegram webhook secret token")
        raise HTTPException(status_code=403, detail="Forbidden")

    payload = await request.json()
    result = await handle_telegram_update(payload)
    return result


@app.get("/health")
async def health():
    """Liveness probe endpoint returning 200 OK for Docker and external uptime checks."""
    return {"ok": True}

