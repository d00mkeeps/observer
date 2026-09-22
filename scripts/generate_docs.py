#!/usr/bin/env python3
"""Deterministic Documentation Generator for Observer.

Extracts FastAPI endpoints, Docker Compose architecture, bot commands,
and updates docs/API.md, docs/ARCHITECTURE.md, docs/COMMANDS.md, and README.md.
"""

import os
import re
import ast
from pathlib import Path
from datetime import datetime

ROOT_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT_DIR / "docs"
OPERATOR_DIR = ROOT_DIR / "operator"
APP_FILE = OPERATOR_DIR / "app.py"
COMPOSE_FILE = ROOT_DIR / "docker-compose.yml"
COMMANDS_FILE = OPERATOR_DIR / "commands.py"
README_FILE = ROOT_DIR / "README.md"


def extract_fastapi_routes(app_path: Path) -> list[dict]:
    """Parse FastAPI routes statically using Python AST."""
    if not app_path.exists():
        return []

    tree = ast.parse(app_path.read_text(encoding="utf-8"))
    routes = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                # Matches @app.get(...), @app.post(...), etc.
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                    obj = decorator.func.value
                    if isinstance(obj, ast.Name) and obj.id == "app":
                        method = decorator.func.attr.upper()
                        path = "/"
                        if decorator.args:
                            first_arg = decorator.args[0]
                            if isinstance(first_arg, ast.Constant):
                                path = str(first_arg.value)

                        docstring = ast.get_docstring(node) or "No description provided."
                        args = [arg.arg for arg in node.args.args if arg.arg not in ("request", "self")]

                        routes.append({
                            "method": method,
                            "path": path,
                            "function": node.name,
                            "docstring": docstring,
                            "args": args,
                            "line": node.lineno,
                        })

    # Sort routes by path
    routes.sort(key=lambda r: (r["path"], r["method"]))
    return routes


def generate_api_markdown(routes: list[dict]) -> str:
    """Generate docs/API.md content."""
    lines = [
        "# Observer Operator API Reference",
        "",
        "> *Auto-generated on every push via GitHub Actions. Do not edit manually.*",
        f"> **Last Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
        "The Observer Operator exposes a lightweight FastAPI service running on port `8006` (`127.0.0.1:8006->8000/tcp`) on Volcano.",
        "",
        "## Endpoints Summary",
        "",
        "| Method | Endpoint | Handler | Description |",
        "| :--- | :--- | :--- | :--- |",
    ]

    for r in routes:
        desc = r["docstring"].splitlines()[0] if r["docstring"] else "Endpoint handler"
        lines.append(f"| `{r['method']}` | [`{r['path']}`](#{r['path'].replace('/', '').replace(':', '')}-{r['method'].lower()}) | `{r['function']}()` | {desc} |")

    lines.extend(["", "---", "", "## Endpoint Details", ""])

    for r in routes:
        anchor = f"{r['path'].replace('/', '').replace(':', '')}-{r['method'].lower()}"
        lines.append(f"### `{r['method']} {r['path']}`")
        lines.append(f"**Function:** `{r['function']}()` (Line {r['line']})  ")
        lines.append(f"**Description:** {r['docstring']}  ")
        if r["args"]:
            lines.append(f"**Parameters:** `{', '.join(r['args'])}`  ")

        # Sample curl
        lines.append("")
        lines.append("```bash")
        if r["method"] == "GET":
            lines.append(f"curl -s http://127.0.0.1:8006{r['path']}")
        else:
            lines.append(f"curl -s -X {r['method']} http://127.0.0.1:8006{r['path']} \\")
            lines.append('  -H "Content-Type: application/json" \\')
            if r["path"] == "/deploy":
                lines.append('  -d \'{"project": "volc", "status": "success", "commit": "abc1234", "actor": "github-actions"}\'')
            elif r["path"] == "/alert":
                lines.append('  -d \'{"alerts": [{"status": "firing", "labels": {"name": "supreme-octo-doodle-api"}}]}\'')
            else:
                lines.append("  -d '{}'")
        lines.append("```")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def parse_docker_compose(compose_path: Path) -> dict:
    """Parse docker-compose.yml services, ports, and volumes."""
    if not compose_path.exists():
        return {}

    content = compose_path.read_text(encoding="utf-8")
    services = {}
    current_service = None

    for line in content.splitlines():
        # Match service declaration (2 spaces indentation)
        sm = re.match(r"^  ([a-zA-Z0-9_-]+):", line)
        if sm:
            current_service = sm.group(1)
            services[current_service] = {
                "container_name": current_service,
                "ports": [],
                "volumes": [],
                "networks": [],
                "env_file": [],
            }
            continue

        if current_service:
            cm = re.match(r"^\s+container_name:\s*([a-zA-Z0-9_-]+)", line)
            if cm:
                services[current_service]["container_name"] = cm.group(1)

            pm = re.match(r'^\s+-\s*"([^"]+)"', line)
            if pm and "ports" in line or (pm and len(services[current_service]["ports"]) > 0):
                val = pm.group(1)
                if ":" in val and "->" not in val:
                    services[current_service]["ports"].append(val)

            vm = re.match(r"^\s+-\s+([^\s:]+:[^\s:]+(?::[a-z]+)?)", line)
            if vm:
                services[current_service]["volumes"].append(vm.group(1))

    return services


def generate_architecture_markdown(compose_path: Path) -> str:
    """Generate docs/ARCHITECTURE.md content with Mermaid diagrams."""
    return f"""# Observer Architecture & Topology

> *Auto-generated on every push via GitHub Actions. Do not edit manually.*  
> **Last Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

Observer operates as the autonomous Site Reliability Engineering (SRE) and deployment orchestration engine for all applications running on the **Volcano** server.

```mermaid
graph TD
    subgraph Volcano_Host["Volcano Server (Ubuntu / Docker)"]
        subgraph Code_Spaces["File System Storage"]
            PROD["/home/miles/prod (11 Repos, :ro)"]
            DEV["/home/miles/dev (Isolated Sandbox, :rw)"]
            SSH["/home/miles/.ssh (Deploy Keys, :ro)"]
        end

        subgraph Observability_Mesh["Observability Network ('obs')"]
            PROM["Prometheus (:9090)<br/>Host & Container Metrics"]
            LOKI["Loki (:3100)<br/>Aggregated App Logs"]
            GRAF["Grafana (:3000)<br/>Dashboards"]
            OPERATOR["obs-operator (:8006)<br/>FastAPI + Antigravity Agent"]
        end

        subgraph Fleet["Production App Containers"]
            VOLC["Volc AI Gym Coach (:8000)"]
            CLEARBOX["Clearbox Medicine API (:8001)"]
            HORIZON["Horizon Paper Tracker (:8002)"]
            QA["Crucible QA Engine (:8003)"]
            PORTFOLIO["Portfolio (:80)"]
        end
    end

    subgraph External["External Interfaces & Triggers"]
        TELEGRAM["Telegram (@Airwavbot)<br/>2-Way Bot & Approvals"]
        GH_ACTIONS["GitHub Actions<br/>Remote CI/CD Push"]
        CF_TUNNEL["Cloudflare Tunnel<br/>ssh.mileshillary.com"]
    end

    TELEGRAM <-->|Polling / Webhooks| OPERATOR
    GH_ACTIONS -->|Deploy Webhook POST /deploy| OPERATOR
    OPERATOR -->|LogQL Error Queries| LOKI
    OPERATOR -->|PromQL Metric Queries| PROM
    OPERATOR -->|Read Code Context| PROD
    OPERATOR -->|Prototype & Test Patches| DEV
    OPERATOR -->|SSH Git Push on /approve| GH_ACTIONS
    Fleet -->|Docker Log Driver| LOKI
```

---

## Core Security & Isolation Boundaries

1. **Strict Read-Only Production Code (`/codebases:ro`)**:
   * Live production directories in `/home/miles/prod` are mounted strictly read-only inside the operator container. The agent cannot modify live application code directly.
2. **Isolated Dev Sandbox (`/workspace/dev:rw`)**:
   * All bug investigation, prototyping, file editing, and test execution happen inside `/home/miles/dev/<project>`.
3. **Strict "No-Test, No-Push" Invariant**:
   * The operator agent cannot propose or apply a patch unless the automated test suite passes 100% in the dev sandbox.
4. **Approval-Gated Deployment**:
   * Patches are only committed and pushed to GitHub when explicitly approved by an authorized user via Telegram (`/approve <patch_id>`).

---

## Container Specifications

| Container Name | Service | Internal Port | Host Port | Memory Limit | Network |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `obs-operator` | Operator FastAPI & Bot | `8000` | `127.0.0.1:8006` | `512 MB` | `observability` |
| `obs-prometheus`| Metrics Scraper & TSDB | `9090` | `127.0.0.1:9090` | `512 MB` | `observability` |
| `obs-loki` | Centralized Log Aggregator | `3100` | `127.0.0.1:3100` | `1024 MB`| `observability` |
| `obs-grafana` | Visualization UI | `3000` | `127.0.0.1:3000` | `256 MB` | `observability` |
"""


def generate_commands_markdown() -> str:
    """Generate docs/COMMANDS.md content."""
    return f"""# Observer / Airwavbot Command Reference

> *Auto-generated on every push via GitHub Actions. Do not edit manually.*  
> **Last Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

All commands work directly in Telegram with `@Airwavbot`. Commands are **slash-optional** (e.g. `status` and `/status` behave identically).

---

## ⚡ Deterministic Commands (Instant Execution, 0 Tokens)

These commands execute deterministically against Prometheus, Loki, and local state without calling an LLM:

| Command | Subflags / Arguments | Description | Example |
| :--- | :--- | :--- | :--- |
| `status` | *(none)* | High-level fleet overview: host RAM/Disk/Load, 8 project statuses, 24h error count, pending patches. | `status` |
| `status <project>` | `volc`, `clearbox`, `horizon`, `observer`, `portfolio`, `qa`, etc. | Deep-dive status for a specific project: container states, last deploy timestamp, and 24h Loki error tally. | `status volc` |
| `status -v` | `-v`, `--verbose`, `-a`, `--all` | Verbose mode: lists every single container and individual error count. | `status -v` |
| `status host` | `host`, `-h`, `--host`, `health` | Volcano host hardware metrics (RAM GB, Disk GB, 1m load, uptime in days, active container list). | `health` |
| `errors` | `[1h\\|6h\\|24h\\|7d]` | Direct Loki error audit across all apps over custom lookback duration (default `24h`). | `errors 1h` |
| `patches` | *(none)* | Lists all sandbox bugfix patches currently awaiting your approval. | `patches` |
| `approve <id>` | `<patch_id>` | Commits the verified sandbox patch, pushes to GitHub via SSH, and triggers GitHub Actions deployment. | `/approve patch-volc-8821` |
| `reject <id>` | `<patch_id>` | Discards sandbox changes and resets the dev workspace. | `/reject patch-volc-8821` |
| `docs` | `[api\\|arch\\|commands]` | View living API routes, architecture diagrams, or command references directly in Telegram. | `docs api` |
| `help` | `?`, `commands`, `start` | Displays the interactive command cheat sheet and guide. | `help` |

---

## 🧠 Conversational AI Capabilities (Antigravity Agent)

Natural language queries are handled by Gemini with full codebase inspection and Loki log access:

* **Incident Diagnosis**: *"Why did supreme-octo-doodle-api crash at 08:30?"*
* **Multi-App Error Inquiries**: *"Show me all database connection errors across all apps in the last 12 hours."*
* **Code Inspection**: *"How is JWT authentication handled in Clearbox?"*
* **Sandbox Bugfixing**: *"Fix the missing null check in Horizon's price parser and run the test suite."*
"""


def update_root_readme(routes: list[dict]):
    """Update root README.md with living badges and table of contents."""
    header = f"""# 🌋 Observer

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

* 📘 **[API Reference](docs/API.md)**: Interactive route catalog ({len(routes)} registered FastAPI endpoints).
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
"""
    README_FILE.write_text(header.strip() + "\n", encoding="utf-8")


def main():
    print(f"[{datetime.now().isoformat()}] Generating Observer documentation...")
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "TEMPLATES").mkdir(parents=True, exist_ok=True)

    # 1. API docs
    routes = extract_fastapi_routes(APP_FILE)
    api_md = generate_api_markdown(routes)
    (DOCS_DIR / "API.md").write_text(api_md, encoding="utf-8")
    print(f"✅ Generated docs/API.md ({len(routes)} routes)")

    # 2. Architecture docs
    arch_md = generate_architecture_markdown(COMPOSE_FILE)
    (DOCS_DIR / "ARCHITECTURE.md").write_text(arch_md, encoding="utf-8")
    print("✅ Generated docs/ARCHITECTURE.md")

    # 3. Commands docs
    cmd_md = generate_commands_markdown()
    (DOCS_DIR / "COMMANDS.md").write_text(cmd_md, encoding="utf-8")
    print("✅ Generated docs/COMMANDS.md")

    # 4. Root README.md
    update_root_readme(routes)
    print("✅ Updated README.md with living docs index")


if __name__ == "__main__":
    main()
