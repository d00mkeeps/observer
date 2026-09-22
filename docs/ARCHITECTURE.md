# Observer Architecture & Topology

> *Auto-generated on every push via GitHub Actions. Do not edit manually.*  
> **Last Generated:** 2026-09-22 10:26:25 UTC

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
