# 🌋 Observer

[![Deploy](https://github.com/d00mkeeps/observer/actions/workflows/deploy.yml/badge.svg)](https://github.com/d00mkeeps/observer/actions/workflows/deploy.yml)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg?logo=docker&logoColor=white)](https://docker.com)
[![Prometheus](https://img.shields.io/badge/Prometheus-Monitoring-E6522C.svg?logo=prometheus&logoColor=white)](https://prometheus.io)
[![Loki](https://img.shields.io/badge/Loki-LogQL-F47C00.svg?logo=grafana&logoColor=white)](https://grafana.com/oss/loki/)
[![Telegram](https://img.shields.io/badge/Telegram-@Airwavbot-26A5E4.svg?logo=telegram&logoColor=white)](https://t.me/Airwavbot)

Autonomous Site Reliability Engineering (SRE), real-time log monitoring, incident response, and deployment orchestration for all services running on **Volcano**.

---

<!-- AUTO-DOCS-START -->
## 📚 Living Documentation

*Auto-generated on every push to `main`:*

* 📘 **[API Reference](docs/API.md)**: Interactive route catalog (7 registered FastAPI endpoints).
* 🏗️ **[Architecture & Topology](docs/ARCHITECTURE.md)**: Interactive Mermaid service mesh, isolation boundaries, and container specs.
* ⚡ **[Command Reference](docs/COMMANDS.md)**: Deterministic `@Airwavbot` commands, subflags, and conversational AI features.
* 🛠️ **[Rollout Guide](docs/TEMPLATES/AUTO_DOCS_GUIDE.md)**: Standard template for rolling auto-docs out to other Volcano repositories.
<!-- AUTO-DOCS-END -->

---

## 🚀 Quick Start

### 1. Telegram Interaction
Chat directly with **[@Airwavbot](https://t.me/Airwavbot)**:
* `status` — Instant host & project fleet health overview.
* `errors 24h` — Query aggregated Loki error logs across all containers.
* `status <project>` — Deep-dive metrics for a specific app (e.g. `status volc`).
* `docs` — View living API and architecture documentation.

### 2. Local Development
```bash
# Clone the repository
git clone https://github.com/d00mkeeps/observer.git
cd observer

# Generate or update documentation
python3 scripts/generate_docs.py

# Run operator locally (requires Python 3.12+)
cd operator
pip install -r requirements.txt
uvicorn app:app --reload --port 8006
```
