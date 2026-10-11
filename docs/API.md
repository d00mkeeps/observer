# Observer Operator API Reference

> *Auto-generated on every push via GitHub Actions. Do not edit manually.*
> **Last Generated:** 2026-10-11 12:34:37 UTC

The Observer Operator exposes a lightweight FastAPI service running on port `8006` (`127.0.0.1:8006->8000/tcp`) on Cano.

## Endpoints Summary

| Method | Endpoint | Handler | Description |
| :--- | :--- | :--- | :--- |
| `POST` | [`/alert`](#alert-post) | `receive_alert()` | Receive and diagnose Prometheus Alertmanager alerts, translating them into 5-point incident cards and dispatching to Telegram. |
| `POST` | [`/chat`](#chat-post) | `chat_endpoint()` | Conversational endpoint for CLI and TUI queries. |
| `POST` | [`/ci/failure`](#cifailure-post) | `receive_ci_failure()` | Receive GitHub Actions workflow/CI failures, log directly to Loki, and dispatch incident alert. |
| `GET` | [`/costs`](#costs-get) | `get_costs_endpoint()` | Retrieve Cano ecosystem cost breakdown by app and service. |
| `POST` | [`/deploy`](#deploy-post) | `receive_deploy()` | Receive deployment notifications from GitHub Actions workflows, update portfolio state, and post summary to Telegram. |
| `GET` | [`/health`](#health-get) | `health()` | Liveness probe endpoint returning 200 OK for Docker and external uptime checks. |
| `GET` | [`/preview/active`](#previewactive-get) | `preview_active()` | Check active preview session state for a project. |
| `GET` | [`/preview/launch`](#previewlaunch-get) | `preview_launch()` | Render iOS Safari trampoline page that immediately invokes the Dev Client custom scheme. |
| `POST` | [`/preview/notify`](#previewnotify-post) | `preview_notify()` | Receive Metro tunnel announcement, register ephemeral session, and dispatch interactive Telegram notification. |
| `POST` | [`/preview/start`](#previewstart-post) | `preview_start_endpoint()` | Trigger on-demand cloud preview session on Cano. |
| `POST` | [`/preview/stop`](#previewstop-post) | `preview_stop()` | Programmatically stop active preview session and clean up Metro tunnel process. |
| `GET` | [`/projects`](#projects-get) | `get_projects_endpoint()` | Retrieve all tracked Cano ecosystem projects, statuses, and milestones. |
| `GET` | [`/projects/markdown`](#projectsmarkdown-get) | `get_projects_markdown_endpoint()` | Retrieve full Cano ecosystem project registry as rendered Markdown. |
| `GET` | [`/projects/{slug}`](#projects{slug}-get) | `get_project_detail_endpoint()` | Retrieve details for a specific Cano project by slug. |
| `PATCH` | [`/projects/{slug}`](#projects{slug}-patch) | `update_project_endpoint()` | Update fields on a Cano project entry. |
| `POST` | [`/projects/{slug}`](#projects{slug}-post) | `update_project_endpoint()` | Update fields on a Cano project entry. |
| `GET` | [`/report`](#report-get) | `trigger_report()` | Trigger on-demand generation and Telegram broadcast of the daily 24h health and performance report. |
| `POST` | [`/report`](#report-post) | `trigger_report()` | Trigger on-demand generation and Telegram broadcast of the daily 24h health and performance report. |
| `GET` | [`/status`](#status-get) | `status_endpoint()` | Retrieve full Cano fleet status JSON, container health, Prometheus resource gauges, and recent deploy history. |
| `POST` | [`/telegram/webhook`](#telegramwebhook-post) | `telegram_webhook()` | Receive incoming Telegram updates via Webhook mode (authenticated with secret token header). |

---

## Endpoint Details

### `POST /alert`
**Function:** `receive_alert()` (Line 90)  
**Description:** Receive and diagnose Prometheus Alertmanager alerts, translating them into 5-point incident cards and dispatching to Telegram.  

```bash
curl -s -X POST http://127.0.0.1:8006/alert \
  -H "Content-Type: application/json" \
  -d '{"alerts": [{"status": "firing", "labels": {"name": "supreme-octo-doodle-api"}}]}'
```

### `POST /chat`
**Function:** `chat_endpoint()` (Line 260)  
**Description:** Conversational endpoint for CLI and TUI queries.  

```bash
curl -s -X POST http://127.0.0.1:8006/chat \
  -H "Content-Type: application/json" \
  -d '{}'
```

### `POST /ci/failure`
**Function:** `receive_ci_failure()` (Line 135)  
**Description:** Receive GitHub Actions workflow/CI failures, log directly to Loki, and dispatch incident alert.  

```bash
curl -s -X POST http://127.0.0.1:8006/ci/failure \
  -H "Content-Type: application/json" \
  -d '{}'
```

### `GET /costs`
**Function:** `get_costs_endpoint()` (Line 190)  
**Description:** Retrieve Cano ecosystem cost breakdown by app and service.  
**Parameters:** `app, timeframe`  

```bash
curl -s http://127.0.0.1:8006/costs
```

### `POST /deploy`
**Function:** `receive_deploy()` (Line 106)  
**Description:** Receive deployment notifications from GitHub Actions workflows, update portfolio state, and post summary to Telegram.  

```bash
curl -s -X POST http://127.0.0.1:8006/deploy \
  -H "Content-Type: application/json" \
  -d '{"project": "volc", "status": "success", "commit": "abc1234", "actor": "github-actions"}'
```

### `GET /health`
**Function:** `health()` (Line 347)  
**Description:** Liveness probe endpoint returning 200 OK for Docker and external uptime checks.  

```bash
curl -s http://127.0.0.1:8006/health
```

### `GET /preview/active`
**Function:** `preview_active()` (Line 324)  
**Description:** Check active preview session state for a project.  
**Parameters:** `p`  

```bash
curl -s http://127.0.0.1:8006/preview/active
```

### `GET /preview/launch`
**Function:** `preview_launch()` (Line 333)  
**Description:** Render iOS Safari trampoline page that immediately invokes the Dev Client custom scheme.  
**Parameters:** `p, url`  

```bash
curl -s http://127.0.0.1:8006/preview/launch
```

### `POST /preview/notify`
**Function:** `preview_notify()` (Line 288)  
**Description:** Receive Metro tunnel announcement, register ephemeral session, and dispatch interactive Telegram notification.  

```bash
curl -s -X POST http://127.0.0.1:8006/preview/notify \
  -H "Content-Type: application/json" \
  -d '{}'
```

### `POST /preview/start`
**Function:** `preview_start_endpoint()` (Line 276)  
**Description:** Trigger on-demand cloud preview session on Cano.  

```bash
curl -s -X POST http://127.0.0.1:8006/preview/start \
  -H "Content-Type: application/json" \
  -d '{}'
```

### `POST /preview/stop`
**Function:** `preview_stop()` (Line 314)  
**Description:** Programmatically stop active preview session and clean up Metro tunnel process.  

```bash
curl -s -X POST http://127.0.0.1:8006/preview/stop \
  -H "Content-Type: application/json" \
  -d '{}'
```

### `GET /projects`
**Function:** `get_projects_endpoint()` (Line 202)  
**Description:** Retrieve all tracked Cano ecosystem projects, statuses, and milestones.  
**Parameters:** `status`  

```bash
curl -s http://127.0.0.1:8006/projects
```

### `GET /projects/markdown`
**Function:** `get_projects_markdown_endpoint()` (Line 208)  
**Description:** Retrieve full Cano ecosystem project registry as rendered Markdown.  

```bash
curl -s http://127.0.0.1:8006/projects/markdown
```

### `GET /projects/{slug}`
**Function:** `get_project_detail_endpoint()` (Line 215)  
**Description:** Retrieve details for a specific Cano project by slug.  
**Parameters:** `slug`  

```bash
curl -s http://127.0.0.1:8006/projects/{slug}
```

### `PATCH /projects/{slug}`
**Function:** `update_project_endpoint()` (Line 225)  
**Description:** Update fields on a Cano project entry.  
**Parameters:** `slug`  

```bash
curl -s -X PATCH http://127.0.0.1:8006/projects/{slug} \
  -H "Content-Type: application/json" \
  -d '{}'
```

### `POST /projects/{slug}`
**Function:** `update_project_endpoint()` (Line 225)  
**Description:** Update fields on a Cano project entry.  
**Parameters:** `slug`  

```bash
curl -s -X POST http://127.0.0.1:8006/projects/{slug} \
  -H "Content-Type: application/json" \
  -d '{}'
```

### `GET /report`
**Function:** `trigger_report()` (Line 236)  
**Description:** Trigger on-demand generation and Telegram broadcast of the daily 24h health and performance report.  

```bash
curl -s http://127.0.0.1:8006/report
```

### `POST /report`
**Function:** `trigger_report()` (Line 236)  
**Description:** Trigger on-demand generation and Telegram broadcast of the daily 24h health and performance report.  

```bash
curl -s -X POST http://127.0.0.1:8006/report \
  -H "Content-Type: application/json" \
  -d '{}'
```

### `GET /status`
**Function:** `status_endpoint()` (Line 196)  
**Description:** Retrieve full Cano fleet status JSON, container health, Prometheus resource gauges, and recent deploy history.  

```bash
curl -s http://127.0.0.1:8006/status
```

### `POST /telegram/webhook`
**Function:** `telegram_webhook()` (Line 244)  
**Description:** Receive incoming Telegram updates via Webhook mode (authenticated with secret token header).  
**Parameters:** `x_telegram_bot_api_secret_token`  

```bash
curl -s -X POST http://127.0.0.1:8006/telegram/webhook \
  -H "Content-Type: application/json" \
  -d '{}'
```
