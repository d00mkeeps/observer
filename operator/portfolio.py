import time
import logging
from datetime import datetime
import httpx
from report import _prom, _loki

log = logging.getLogger("operator.portfolio")

# Mapping of project slugs to their core container names
PROJECT_CONTAINERS = {
    "volc": ["volc-website", "supreme-octo-doodle-api"],
    "clearbox": ["clearbox-site", "medicine-api", "cb_postgres_db"],
    "horizon": ["paper_frontend_ui", "solana_paper_tracker", "paper_postgres_db"],
    "qa": ["crucible-web", "crucible-api"],
    "observer": ["obs-operator", "obs-grafana", "obs-prometheus", "obs-loki"],
    "portfolio": ["miles-portfolio"],
}

PROJECT_METADATA = {
    "volc": {
        "title": "Volc AI Gym Coach",
        "description": "AI-powered workout tracking and computer vision coaching.",
        "url": "https://apps.apple.com/gb/app/volc-ai-gym-coach/id6751469055",
        "category": "iOS / AI",
    },
    "clearbox": {
        "title": "Clearbox Medicine API",
        "description": "Biomedical knowledge retrieval and pgvector embeddings engine.",
        "url": "https://clearbox.mileshillary.com",
        "category": "API / RAG",
    },
    "horizon": {
        "title": "Horizon Paper Tracker",
        "description": "Algorithmic token tracking and simulation trading platform.",
        "url": "https://horizon.mileshillary.com",
        "category": "Trading / Bot",
    },
    "qa": {
        "title": "Crucible QA",
        "description": "Autonomous end-to-end testing and feature-to-spec pipeline.",
        "url": "https://qa.mileshillary.com",
        "category": "DevOps",
    },
    "tax": {
        "title": "Tax Estimator",
        "description": "Interactive tax computation and financial modeling tool.",
        "url": "https://tax.mileshillary.com",
        "category": "Web App",
    },
    "brain": {
        "title": "Brain Knowledge Base",
        "description": "Historical knowledge graph and cognitive research notes.",
        "url": "https://brain.mileshillary.com",
        "category": "Research",
    },
    "observer": {
        "title": "Observer Ops",
        "description": "Autonomous host monitoring, alerting, and deployment orchestrator.",
        "url": "https://observer.mileshillary.com",
        "category": "SRE",
    },
}

# Recent deployments log (in-memory)
_recent_deploys = []


def record_deploy_event(project: str, status: str, commit: str = "", actor: str = "", message: str = ""):
    entry = {
        "project": project,
        "status": status,
        "commit": commit,
        "actor": actor,
        "message": message,
        "timestamp": datetime.now().isoformat(),
        "unix_time": time.time(),
    }
    _recent_deploys.insert(0, entry)
    if len(_recent_deploys) > 50:
        _recent_deploys.pop()
    log.info("Recorded deploy event for %s (%s)", project, status)


async def get_system_status() -> dict:
    async with httpx.AsyncClient() as client:
        # Running containers
        running_res = await _prom(client, 'time() - container_last_seen{name=~".+"} < 60')
        running_names = {r["metric"]["name"] for r in running_res}

        # Host resources
        ram_total_r = await _prom(client, "node_memory_MemTotal_bytes")
        ram_avail_r = await _prom(client, "node_memory_MemAvailable_bytes")
        disk_total_r = await _prom(client, 'node_filesystem_size_bytes{mountpoint="/"}')
        disk_avail_r = await _prom(client, 'node_filesystem_avail_bytes{mountpoint="/"}')
        load1_r = await _prom(client, "node_load1")
        uptime_r = await _prom(client, "time() - node_boot_time_seconds")

    now = time.time()
    projects_status = {}

    for slug, meta in PROJECT_METADATA.items():
        containers = PROJECT_CONTAINERS.get(slug, [])
        active_containers = [c for c in containers if c in running_names]

        # Check recent deploy within last 5 minutes
        recent_deploy = next((d for d in _recent_deploys if d["project"].lower() == slug and (now - d["unix_time"]) < 300), None)

        if recent_deploy and recent_deploy["status"] == "updating":
            state = "updating"
            detail = "Deploy in progress"
        elif containers and len(active_containers) == len(containers):
            state = "live"
            detail = f"All {len(containers)} containers healthy"
        elif containers and len(active_containers) > 0:
            state = "degraded"
            detail = f"{len(active_containers)}/{len(containers)} containers running"
        elif slug in ("tax", "brain"):
            state = "archived"
            detail = "Live static archive"
        else:
            state = "archived"
            detail = "Archived project"

        projects_status[slug] = {
            "slug": slug,
            "title": meta["title"],
            "description": meta["description"],
            "url": meta["url"],
            "category": meta["category"],
            "state": state,
            "detail": detail,
            "active_containers": active_containers,
            "total_containers": len(containers),
        }

    # Host summary
    ram_pct = 0
    if ram_total_r and ram_avail_r:
        t = float(ram_total_r[0]["value"][1])
        a = float(ram_avail_r[0]["value"][1])
        ram_pct = round((t - a) / t * 100)

    disk_pct = 0
    if disk_total_r and disk_avail_r:
        t = float(disk_total_r[0]["value"][1])
        a = float(disk_avail_r[0]["value"][1])
        disk_pct = round((t - a) / t * 100)

    load = float(load1_r[0]["value"][1]) if load1_r else 0.0
    uptime_secs = float(uptime_r[0]["value"][1]) if uptime_r else 0

    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "host": {
            "name": "volcano",
            "ram_pct": ram_pct,
            "disk_pct": disk_pct,
            "load": round(load, 2),
            "uptime_days": round(uptime_secs / 86400, 1),
            "containers_running": len(running_names),
        },
        "projects": projects_status,
        "recent_deploys": _recent_deploys[:10],
    }
