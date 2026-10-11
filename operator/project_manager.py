"""
Cano Project Registry & Lifecycle Manager
Maintains declarative project statuses, parked durations, current milestones, and notes.
"""

import os
import tempfile
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

try:
    import yaml
except ImportError:
    yaml = None

log = logging.getLogger("operator.project_manager")

CANDIDATE_PATHS = [
    os.environ.get("PROJECTS_YAML_PATH"),
    "/workspace/dev/observer/projects.yaml",
    "/home/ubuntu/dev/observer/projects.yaml",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "projects.yaml")),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "projects.yaml")),
]


def resolve_projects_yaml_path(custom_path: Optional[str] = None) -> str:
    """Resolve the location of projects.yaml across host and container environments."""
    if custom_path and os.path.exists(custom_path):
        return custom_path

    for candidate in CANDIDATE_PATHS:
        if candidate and os.path.exists(candidate):
            return candidate

    # Default fallback to parent of operator dir
    default_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "projects.yaml"))
    return default_path


def load_projects_registry(file_path: Optional[str] = None) -> Dict[str, Any]:
    """Load the full projects registry dictionary from projects.yaml."""
    if yaml is None:
        raise ImportError("pyyaml is required to load projects registry")

    target_path = resolve_projects_yaml_path(file_path)
    if not os.path.exists(target_path):
        log.warning("Projects registry file not found at %s; returning empty structure", target_path)
        return {"last_updated": datetime.now(timezone.utc).isoformat(), "projects": {}}

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            if "projects" not in data:
                data["projects"] = {}
            return data
    except Exception as e:
        log.error("Failed to load projects registry from %s: %s", target_path, e)
        return {"last_updated": datetime.now(timezone.utc).isoformat(), "projects": {}}


def save_projects_registry(data: Dict[str, Any], file_path: Optional[str] = None) -> str:
    """Save the projects registry atomically to prevent file corruption."""
    if yaml is None:
        raise ImportError("pyyaml is required to save projects registry")

    target_path = resolve_projects_yaml_path(file_path)
    data["last_updated"] = datetime.now(timezone.utc).isoformat()

    dir_name = os.path.dirname(os.path.abspath(target_path))
    os.makedirs(dir_name, exist_ok=True)

    # Atomic write pattern: write to tmp file in same dir, then atomic replace
    tmp_fd, tmp_path = tempfile.mkstemp(prefix="projects_", suffix=".tmp", dir=dir_name)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False, indent=2, allow_unicode=True)
        os.replace(tmp_path, target_path)
        log.info("Successfully saved projects registry to %s", target_path)
        return target_path
    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        log.error("Failed to save projects registry to %s: %s", target_path, e)
        raise e


def get_project(slug: str, file_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve details for a specific project by slug."""
    data = load_projects_registry(file_path)
    projects = data.get("projects", {})
    slug_clean = slug.strip().lower()

    if slug_clean in projects:
        entry = dict(projects[slug_clean])
        entry["slug"] = slug_clean
        return entry

    # Fallback partial matching
    for key, item in projects.items():
        if key.lower() == slug_clean or item.get("name", "").lower() == slug_clean:
            entry = dict(item)
            entry["slug"] = key
            return entry
    return None


def list_projects(status_filter: Optional[str] = None, file_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all projects, optionally filtered by lifecycle status."""
    data = load_projects_registry(file_path)
    projects = data.get("projects", {})
    results = []

    for slug, entry in projects.items():
        item = dict(entry)
        item["slug"] = slug
        if status_filter:
            if item.get("status", "").lower() != status_filter.strip().lower():
                continue
        results.append(item)

    return sorted(results, key=lambda x: (x.get("status") != "active", x.get("name", "")))


def update_project(slug: str, updates: Dict[str, Any], file_path: Optional[str] = None) -> Dict[str, Any]:
    """Update fields for a project entry and persist changes."""
    data = load_projects_registry(file_path)
    projects = data.get("projects", {})
    slug_clean = slug.strip().lower()

    target_key = None
    if slug_clean in projects:
        target_key = slug_clean
    else:
        for k, v in projects.items():
            if k.lower() == slug_clean or v.get("name", "").lower() == slug_clean:
                target_key = k
                break

    if not target_key:
        # Create new project entry if it does not exist
        target_key = slug_clean
        projects[target_key] = {
            "name": slug.title(),
            "category": "Service",
            "status": "active",
            "status_reason": "",
            "current_focus": "",
            "parked_until": None,
            "next_milestone": "",
            "repo_path": f"/home/ubuntu/dev/{slug_clean}",
            "containers": [],
            "notes": [],
        }

    proj = projects[target_key]
    for key, val in updates.items():
        if key == "notes" and isinstance(val, str):
            # Append string note if given
            notes = proj.get("notes", [])
            if not isinstance(notes, list):
                notes = [notes] if notes else []
            if val not in notes:
                notes.append(val)
            proj["notes"] = notes
        elif key != "slug":
            proj[key] = val

    projects[target_key] = proj
    data["projects"] = projects
    save_projects_registry(data, file_path)

    res = dict(proj)
    res["slug"] = target_key
    return res


def park_project(slug: str, days: int = 7, reason: Optional[str] = None, file_path: Optional[str] = None) -> Dict[str, Any]:
    """Convenience helper to park a project for a specified duration."""
    parked_until_date = (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d")
    status_reason = reason or f"Parked for {days} days"
    updates = {
        "status": "parked",
        "status_reason": status_reason,
        "parked_until": parked_until_date,
    }
    return update_project(slug, updates, file_path)


def unpark_project(slug: str, reason: Optional[str] = None, file_path: Optional[str] = None) -> Dict[str, Any]:
    """Convenience helper to resume/activate a parked project."""
    updates = {
        "status": "active",
        "status_reason": reason or "Resumed active status",
        "parked_until": None,
    }
    return update_project(slug, updates, file_path)


def format_projects_table(projects_list: List[Dict[str, Any]]) -> str:
    """Format projects into a clean terminal ASCII table."""
    status_emojis = {
        "active": "🟢",
        "parked": "⏸️",
        "in-development": "🔨",
        "maintenance": "🟡",
        "archived": "⚪",
    }

    lines = []
    lines.append("=" * 86)
    lines.append(f"{'CANO ECOSYSTEM PROJECT REGISTRY':^86}")
    lines.append("=" * 86)
    lines.append(f"{'SLUG':<14} {'STATUS':<12} {'PROJECT NAME':<24} {'CURRENT FOCUS / PARKED UNTIL'}")
    lines.append("-" * 86)

    for p in projects_list:
        slug = p.get("slug", "")
        status = p.get("status", "unknown").lower()
        emoji = status_emojis.get(status, "🔹")
        status_str = f"{emoji} {status.capitalize()}"
        name = p.get("name", slug)[:23]

        if status == "parked" and p.get("parked_until"):
            detail = f"Until {p.get('parked_until')} | {p.get('current_focus', '')}"
        else:
            detail = p.get("current_focus", "") or p.get("status_reason", "")
        if len(detail) > 42:
            detail = detail[:39] + "..."

        lines.append(f"{slug:<14} {status_str:<12} {name:<24} {detail}")

    lines.append("=" * 86)
    return "\n".join(lines)


def format_markdown_summary(projects_data: Dict[str, Any]) -> str:
    """Format projects into a markdown report."""
    projects = projects_data.get("projects", {})
    last_updated = projects_data.get("last_updated", "N/A")

    lines = [
        "# 🌋 Cano Ecosystem Project Registry",
        f"*Last updated: `{last_updated}`*\n",
        "| Project | Status | Current Focus | Next Milestone | Parked Until |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]

    status_badges = {
        "active": "🟢 Active",
        "parked": "⏸️ Parked",
        "in-development": "🔨 Dev",
        "maintenance": "🟡 Maintenance",
        "archived": "⚪ Archived",
    }

    for slug, p in projects.items():
        name = p.get("name", slug)
        raw_status = p.get("status", "active").lower()
        badge = status_badges.get(raw_status, raw_status.title())
        focus = p.get("current_focus", "-").replace("|", "/")
        milestone = p.get("next_milestone", "-").replace("|", "/")
        parked_until = f"`{p.get('parked_until')}`" if p.get("parked_until") else "-"
        lines.append(f"| **{name}** (`{slug}`) | {badge} | {focus} | {milestone} | {parked_until} |")

    lines.append("\n## Detailed Project Notes")
    for slug, p in projects.items():
        notes = p.get("notes", [])
        if notes:
            lines.append(f"\n### {p.get('name', slug)} (`{slug}`)")
            if p.get("status_reason"):
                lines.append(f"> **Status Note:** {p.get('status_reason')}\n")
            for n in notes:
                lines.append(f"- {n}")

    return "\n".join(lines)
