# Observer Operator API Reference

> *Auto-generated on every push via GitHub Actions. Do not edit manually.*
> **Last Generated:** 2026-09-22 10:35:13 UTC

The Observer Operator exposes a lightweight FastAPI service running on port `8006` (`127.0.0.1:8006->8000/tcp`) on Volcano.

## Endpoints Summary

| Method | Endpoint | Handler | Description |
| :--- | :--- | :--- | :--- |
| `POST` | [`/alert`](#alert-post) | `receive_alert()` | Receive and diagnose Prometheus Alertmanager alerts, translating them into 5-point incident cards and dispatching to Telegram. |
| `POST` | [`/deploy`](#deploy-post) | `receive_deploy()` | Receive deployment notifications from GitHub Actions workflows, update portfolio state, and post summary to Telegram. |
| `GET` | [`/health`](#health-get) | `health()` | Liveness probe endpoint returning 200 OK for Docker and external uptime checks. |
| `GET` | [`/report`](#report-get) | `trigger_report()` | Trigger on-demand generation and Telegram broadcast of the daily 24h health and performance report. |
| `POST` | [`/report`](#report-post) | `trigger_report()` | Trigger on-demand generation and Telegram broadcast of the daily 24h health and performance report. |
| `GET` | [`/status`](#status-get) | `status_endpoint()` | Retrieve full Volcano fleet status JSON, container health, Prometheus resource gauges, and recent deploy history. |
| `POST` | [`/telegram/webhook`](#telegramwebhook-post) | `telegram_webhook()` | Receive incoming Telegram updates via Webhook mode (authenticated with secret token header). |

---

## Endpoint Details

### `POST /alert`
**Function:** `receive_alert()` (Line 72)  
**Description:** Receive and diagnose Prometheus Alertmanager alerts, translating them into 5-point incident cards and dispatching to Telegram.  

```bash
curl -s -X POST http://127.0.0.1:8006/alert \
  -H "Content-Type: application/json" \
  -d '{"alerts": [{"status": "firing", "labels": {"name": "supreme-octo-doodle-api"}}]}'
```

### `POST /deploy`
**Function:** `receive_deploy()` (Line 88)  
**Description:** Receive deployment notifications from GitHub Actions workflows, update portfolio state, and post summary to Telegram.  

```bash
curl -s -X POST http://127.0.0.1:8006/deploy \
  -H "Content-Type: application/json" \
  -d '{"project": "volc", "status": "success", "commit": "abc1234", "actor": "github-actions"}'
```

### `GET /health`
**Function:** `health()` (Line 147)  
**Description:** Liveness probe endpoint returning 200 OK for Docker and external uptime checks.  

```bash
curl -s http://127.0.0.1:8006/health
```

### `GET /report`
**Function:** `trigger_report()` (Line 123)  
**Description:** Trigger on-demand generation and Telegram broadcast of the daily 24h health and performance report.  

```bash
curl -s http://127.0.0.1:8006/report
```

### `POST /report`
**Function:** `trigger_report()` (Line 123)  
**Description:** Trigger on-demand generation and Telegram broadcast of the daily 24h health and performance report.  

```bash
curl -s -X POST http://127.0.0.1:8006/report \
  -H "Content-Type: application/json" \
  -d '{}'
```

### `GET /status`
**Function:** `status_endpoint()` (Line 116)  
**Description:** Retrieve full Volcano fleet status JSON, container health, Prometheus resource gauges, and recent deploy history.  

```bash
curl -s http://127.0.0.1:8006/status
```

### `POST /telegram/webhook`
**Function:** `telegram_webhook()` (Line 131)  
**Description:** Receive incoming Telegram updates via Webhook mode (authenticated with secret token header).  
**Parameters:** `x_telegram_bot_api_secret_token`  

```bash
curl -s -X POST http://127.0.0.1:8006/telegram/webhook \
  -H "Content-Type: application/json" \
  -d '{}'
```
