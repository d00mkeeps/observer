import os
import re
import glob
import logging

log = logging.getLogger("operator.tools.codebase")

CODEBASES_PATH = os.environ.get("CODEBASES_PATH", "/codebases")

FORBIDDEN_PATTERNS = [
    r"\.env",
    r"id_rsa",
    r"id_ed25519",
    r"\.pem$",
    r"\.key$",
    r"credentials",
    r"secrets?",
    r"\.git/",
]

# Map container names to directory names inside /codebases
CONTAINER_REPO_MAP = {
    "volc-website": "volc",
    "supreme-octo-doodle-api": "volc",
    "medicine-api": "clear-box",
    "cb_postgrest_api": "clear-box",
    "clearbox-site": "clearbox-site",
    "paper_frontend_ui": "horizon",
    "solana_paper_tracker": "horizon",
    "crucible-web": "qa",
    "crucible-api": "qa",
    "feat-to-spec": "qa",
    "obs-operator": "observer",
    "obs-grafana": "obs",
    "obs-prometheus": "obs",
    "obs-loki": "obs",
    "miles-portfolio": "portfolio",
    "prickly-crane-frontend-1": "prickly-crane",
    "prickly-crane-backend-1": "prickly-crane",
    "sturdy-robot-tunnel-1": "sturdy-robot",
}


def resolve_project_path(project_or_container: str) -> str | None:
    """Resolve project name or container name to an existing folder in CODEBASES_PATH."""
    target_name = CONTAINER_REPO_MAP.get(project_or_container, project_or_container)
    
    # Check direct match
    direct_path = os.path.join(CODEBASES_PATH, target_name)
    if os.path.isdir(direct_path):
        return os.path.realpath(direct_path)

    # Check case-insensitive match or substring
    if os.path.isdir(CODEBASES_PATH):
        for entry in os.listdir(CODEBASES_PATH):
            if entry.lower() == target_name.lower():
                return os.path.realpath(os.path.join(CODEBASES_PATH, entry))
            if target_name.lower() in entry.lower():
                return os.path.realpath(os.path.join(CODEBASES_PATH, entry))

    return None


def is_forbidden(path: str) -> bool:
    """Check if the target path matches any sensitive file patterns."""
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, path, re.IGNORECASE):
            return True
    return False


def read_codebase_file(project: str, filepath: str, start_line: int = 1, end_line: int = 100) -> str:
    """Read lines from a file in a project codebase (Strictly Read-Only).

    Args:
        project: Project name (e.g. 'volc', 'clear-box', 'horizon', 'observer') or container name.
        filepath: Relative path to the file within the project repository.
        start_line: 1-indexed start line number.
        end_line: 1-indexed end line number.
    """
    base_dir = resolve_project_path(project)
    if not base_dir:
        return f"Error: Project/container '{project}' codebase directory not found in {CODEBASES_PATH}."

    if is_forbidden(filepath):
        return f"Access Denied: Reading '{filepath}' is blocked for security/credential protection."

    target_path = os.path.realpath(os.path.join(base_dir, filepath))

    # Path traversal check
    if not target_path.startswith(base_dir):
        return f"Error: Attempted path traversal outside project root."

    if not os.path.isfile(target_path):
        return f"Error: File '{filepath}' does not exist in project '{project}'."

    try:
        with open(target_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        
        start_idx = max(0, start_line - 1)
        end_idx = min(len(lines), max(start_idx, end_line))
        
        result_lines = []
        for idx in range(start_idx, end_idx):
            result_lines.append(f"{idx + 1:4d} | {lines[idx]}")
            
        return "".join(result_lines) if result_lines else "(File is empty or range out of bounds)"
    except Exception as e:
        return f"Error reading file '{filepath}': {str(e)}"


def search_codebase(project: str, query: str) -> str:
    """Search for a keyword or function name across files in a project repository.

    Args:
        project: Project name or container name.
        query: Search string to look for.
    """
    base_dir = resolve_project_path(project)
    if not base_dir:
        return f"Error: Project '{project}' not found."

    matches = []
    query_lower = query.lower()
    
    # Allowed file extensions
    allowed_exts = {".py", ".ts", ".js", ".tsx", ".jsx", ".json", ".sql", ".sh", ".yml", ".yaml", ".md", ".html", ".css", ".go"}

    for root, dirs, files in os.walk(base_dir):
        # Ignore noisy directories
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules", ".venv", "venv", "__pycache__", ".next", "dist", "build"}]
        
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext not in allowed_exts:
                continue
            
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, base_dir)
            
            if is_forbidden(rel_path):
                continue
                
            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line_num, line in enumerate(f, 1):
                        if query_lower in line.lower():
                            matches.append(f"{rel_path}:{line_num}: {line.strip()}")
                            if len(matches) >= 20:
                                break
            except Exception:
                continue
        if len(matches) >= 20:
            break

    if not matches:
        return f"No matches found for '{query}' in project '{project}'."
    return "\n".join(matches[:20])


def list_project_files(project: str, subpath: str = "") -> str:
    """List files in a project directory.

    Args:
        project: Project name or container name.
        subpath: Optional subdirectory path within the project.
    """
    base_dir = resolve_project_path(project)
    if not base_dir:
        return f"Error: Project '{project}' not found."

    target_dir = os.path.realpath(os.path.join(base_dir, subpath)) if subpath else base_dir
    if not target_dir.startswith(base_dir) or not os.path.isdir(target_dir):
        return f"Error: Subdirectory '{subpath}' not found in project '{project}'."

    try:
        entries = []
        for item in sorted(os.listdir(target_dir)):
            if item in {".git", "node_modules", ".venv", "venv", "__pycache__"}:
                continue
            if is_forbidden(item):
                continue
            full = os.path.join(target_dir, item)
            suffix = "/" if os.path.isdir(full) else ""
            entries.append(f"{item}{suffix}")
        return "\n".join(entries[:40])
    except Exception as e:
        return f"Error listing files: {str(e)}"
