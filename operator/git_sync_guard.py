#!/usr/bin/env python3
"""Volcano Cloud Git Synchronization & Integrity Guard.

Ensures development workspaces, production server deployments, and GitHub remotes
remain strictly synchronized, preventing stale-base commits, accidental overwrites,
and surfacing rogue uncommitted changes with actionable diff summaries.
"""

import os
import sys
import json
import argparse
import subprocess
from typing import Dict, Any, List, Tuple, Optional

KNOWN_REPOSITORIES = [
    "volc",
    "clear-box",
    "horizon",
    "observer",
    "portfolio",
    "sturdy-robot",
]

DEFAULT_DEV_ROOT = os.environ.get("DEV_WORKSPACE_PATH", "/home/miles/dev")
DEFAULT_PROD_ROOT = os.environ.get("CODEBASES_PATH", "/home/miles/prod")


def run_cmd(args: List[str], cwd: Optional[str] = None, timeout: int = 15) -> Tuple[int, str, str]:
    """Execute a local shell command and return (code, stdout, stderr)."""
    try:
        res = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return -1, "", str(e)


def get_git_sha(repo_path: str, ref: str = "HEAD") -> Optional[str]:
    """Get the short commit SHA for a ref."""
    if not os.path.isdir(os.path.join(repo_path, ".git")):
        return None
    code, stdout, _ = run_cmd(["git", "rev-parse", "--short", ref], cwd=repo_path)
    return stdout if code == 0 else None


def get_git_commit_msg(repo_path: str, ref: str = "HEAD") -> str:
    """Get the commit subject for a ref."""
    code, stdout, _ = run_cmd(["git", "log", "-1", "--format=%s", ref], cwd=repo_path)
    return stdout if code == 0 else ""


def get_uncommitted_changes(repo_path: str) -> List[Dict[str, str]]:
    """Return list of uncommitted / untracked files in the working directory."""
    code, stdout, _ = run_cmd(["git", "status", "--porcelain"], cwd=repo_path)
    if code != 0 or not stdout:
        return []

    changes = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        status = line[:2].strip()
        filename = line[2:].strip()
        changes.append({"status": status, "file": filename})
    return changes


def get_rogue_diff_summary(repo_path: str) -> str:
    """Generate a concise, human-readable summary of rogue / uncommitted changes."""
    changes = get_uncommitted_changes(repo_path)
    if not changes:
        return "Clean working directory (no rogue changes)."

    lines = [f"Found {len(changes)} uncommitted change(s):"]
    for c in changes:
        status_label = {
            "M": "Modified",
            "A": "Added",
            "D": "Deleted",
            "??": "Untracked (Rogue)",
            "R": "Renamed",
        }.get(c["status"], c["status"])
        lines.append(f"  [{status_label}] {c['file']}")

    # Add stat diff if modified files exist
    code, stat_out, _ = run_cmd(["git", "diff", "--stat"], cwd=repo_path)
    if code == 0 and stat_out:
        lines.append("\nDiff Stat:")
        lines.append(stat_out)

    return "\n".join(lines)


def get_full_diff(repo_path: str) -> str:
    """Get full patch diff including untracked files."""
    code, diff_out, _ = run_cmd(["git", "diff"], cwd=repo_path)
    untracked = [c["file"] for c in get_uncommitted_changes(repo_path) if c["status"] == "??"]

    result = diff_out if code == 0 else ""
    if untracked:
        result += "\n\n--- Untracked Files ---\n"
        for u in untracked:
            u_path = os.path.join(repo_path, u)
            if os.path.isfile(u_path):
                try:
                    with open(u_path, "r", encoding="utf-8", errors="replace") as f:
                        preview = f.read(1024)
                    result += f"\nFile: {u} (preview):\n{preview}\n"
                except Exception:
                    result += f"\nFile: {u} (binary/unreadable)\n"
    return result.strip()


def inspect_repository(
    repo_name: str,
    dev_root: str = DEFAULT_DEV_ROOT,
    prod_root: str = DEFAULT_PROD_ROOT,
    fetch_remote: bool = True,
    branch: str = "main",
) -> Dict[str, Any]:
    """Inspect a single repository across dev, origin, and prod environments."""
    dev_path = os.path.join(dev_root, repo_name)
    prod_path = os.path.join(prod_root, repo_name)

    res: Dict[str, Any] = {
        "repo": repo_name,
        "dev_exists": os.path.isdir(dev_path),
        "prod_exists": os.path.isdir(prod_path),
        "dev_path": dev_path,
        "prod_path": prod_path,
        "dev_sha": None,
        "dev_commit_msg": "",
        "prod_sha": None,
        "origin_sha": None,
        "dev_clean": True,
        "prod_clean": True,
        "rogue_changes": [],
        "rogue_summary": "",
        "ahead_count": 0,
        "behind_count": 0,
        "status": "UNKNOWN",
        "details": [],
    }

    if not res["dev_exists"]:
        res["status"] = "MISSING_DEV"
        res["details"].append(f"Dev directory not found at {dev_path}")
        return res

    # 1. Check uncommitted changes in dev
    rogue = get_uncommitted_changes(dev_path)
    res["rogue_changes"] = rogue
    res["dev_clean"] = len(rogue) == 0
    if rogue:
        res["rogue_summary"] = get_rogue_diff_summary(dev_path)
        res["details"].append(f"Dev has {len(rogue)} uncommitted rogue change(s)")

    # 2. Get dev HEAD SHA
    res["dev_sha"] = get_git_sha(dev_path)
    res["dev_commit_msg"] = get_git_commit_msg(dev_path)

    # 3. Check prod HEAD SHA & cleanliness
    if res["prod_exists"]:
        res["prod_sha"] = get_git_sha(prod_path)
        prod_rogue = get_uncommitted_changes(prod_path)
        res["prod_clean"] = len(prod_rogue) == 0
        if prod_rogue:
            res["details"].append(f"Prod has {len(prod_rogue)} dirty change(s) (unexpected!)")

    # 4. Fetch origin if requested
    if fetch_remote:
        run_cmd(["git", "fetch", "origin", branch], cwd=dev_path, timeout=15)

    res["origin_sha"] = get_git_sha(dev_path, f"origin/{branch}")

    # 5. Calculate commit divergence between dev and origin
    if res["dev_sha"] and res["origin_sha"]:
        code_ahead, stdout_ahead, _ = run_cmd(
            ["git", "rev-list", "--count", f"origin/{branch}..HEAD"], cwd=dev_path
        )
        code_behind, stdout_behind, _ = run_cmd(
            ["git", "rev-list", "--count", f"HEAD..origin/{branch}"], cwd=dev_path
        )
        if code_ahead == 0 and stdout_ahead.isdigit():
            res["ahead_count"] = int(stdout_ahead)
        if code_behind == 0 and stdout_behind.isdigit():
            res["behind_count"] = int(stdout_behind)

    # 6. Determine status label
    if not res["dev_clean"]:
        if res["behind_count"] > 0:
            res["status"] = "STALE_BASE_DIRTY"
            res["details"].append(
                f"DANGER: Rogue changes exist on top of a stale base ({res['behind_count']} commits behind origin)"
            )
        else:
            res["status"] = "ROGUE_CHANGES"
    elif res["behind_count"] > 0 and res["ahead_count"] > 0:
        res["status"] = "DIVERGED"
        res["details"].append(
            f"Diverged from origin (+{res['ahead_count']}, -{res['behind_count']} commits)"
        )
    elif res["behind_count"] > 0:
        res["status"] = "BEHIND"
        res["details"].append(f"Dev is {res['behind_count']} commit(s) behind origin")
    elif res["ahead_count"] > 0:
        res["status"] = "AHEAD"
        res["details"].append(f"Dev has {res['ahead_count']} unpushed commit(s)")
    elif res["prod_sha"] and res["prod_sha"] != res["origin_sha"]:
        res["status"] = "PROD_OUT_OF_SYNC"
        res["details"].append(
            f"Prod ({res['prod_sha']}) does not match origin ({res['origin_sha']})"
        )
    else:
        res["status"] = "SYNCED"

    return res


def inspect_all_repositories(
    dev_root: str = DEFAULT_DEV_ROOT,
    prod_root: str = DEFAULT_PROD_ROOT,
    fetch_remote: bool = True,
) -> Dict[str, Dict[str, Any]]:
    """Inspect all known repositories and return status dictionary."""
    results = {}
    for repo in KNOWN_REPOSITORIES:
        results[repo] = inspect_repository(
            repo_name=repo,
            dev_root=dev_root,
            prod_root=prod_root,
            fetch_remote=fetch_remote,
        )
    return results


def sync_repository(
    repo_name: str,
    dev_root: str = DEFAULT_DEV_ROOT,
    prod_root: str = DEFAULT_PROD_ROOT,
    discard_rogue: bool = False,
    branch: str = "main",
) -> Tuple[bool, str]:
    """Safely synchronize dev and prod workspaces with origin/main."""
    status = inspect_repository(
        repo_name=repo_name,
        dev_root=dev_root,
        prod_root=prod_root,
        fetch_remote=True,
        branch=branch,
    )

    dev_path = status["dev_path"]
    prod_path = status["prod_path"]

    # 1. Guard against rogue changes
    if not status["dev_clean"]:
        if not discard_rogue:
            summary = status["rogue_summary"]
            return False, (
                f"🛑 Cannot sync '{repo_name}' because uncommitted rogue changes exist in dev:\n\n"
                f"{summary}\n\n"
                f"To discard rogue changes and force sync, use '--discard-rogue'."
            )
        else:
            # Discard rogue changes cleanly
            run_cmd(["git", "reset", "--hard", "HEAD"], cwd=dev_path)
            run_cmd(["git", "clean", "-fd"], cwd=dev_path)

    # 2. Fast-forward Dev to origin
    code, stdout, stderr = run_cmd(
        ["git", "merge", "--ff-only", f"origin/{branch}"], cwd=dev_path
    )
    if code != 0:
        # If ff-only fails, check if ahead
        if status["ahead_count"] > 0:
            return False, f"Dev has {status['ahead_count']} local commits. Push them or rebase first."
        return False, f"Failed to fast-forward dev for '{repo_name}': {stderr or stdout}"

    new_dev_sha = get_git_sha(dev_path)

    # 3. Pull Prod if exists
    prod_synced = False
    if status["prod_exists"]:
        # Prod must be clean
        if not status["prod_clean"]:
            # Hard reset prod to avoid any stuck states
            run_cmd(["git", "reset", "--hard", "HEAD"], cwd=prod_path)
            run_cmd(["git", "clean", "-fd"], cwd=prod_path)

        code_prod, _, err_prod = run_cmd(["git", "fetch", "origin", branch], cwd=prod_path)
        code_pull, _, err_pull = run_cmd(["git", "pull", "--ff-only", "origin", branch], cwd=prod_path)
        if code_pull != 0:
            return False, f"Failed fast-forwarding prod: {err_pull}"

        new_prod_sha = get_git_sha(prod_path)
        prod_synced = (new_prod_sha == new_dev_sha)
    else:
        new_prod_sha = "N/A"
        prod_synced = True

    if prod_synced:
        return True, (
            f"✅ '{repo_name}' fully synchronized!\n"
            f"• Dev SHA:  {new_dev_sha}\n"
            f"• Prod SHA: {new_prod_sha}\n"
            f"• Origin:   {status['origin_sha']}\n"
            f"Environments are identical."
        )
    else:
        return False, f"Dev updated ({new_dev_sha}) but Prod is at {new_prod_sha}."


def main():
    parser = argparse.ArgumentParser(description="Volcano Git Sync & Integrity Guard")
    subparsers = parser.add_subparsers(dest="command")

    # check
    check_parser = subparsers.add_parser("check", help="Inspect all repositories for sync & rogue changes")
    check_parser.add_argument("--repo", help="Check specific repo only")
    check_parser.add_argument("--json", action="store_true", help="Output raw JSON")
    check_parser.add_argument("--no-fetch", action="store_true", help="Skip remote fetch")

    # diff
    diff_parser = subparsers.add_parser("diff", help="Show rogue / uncommitted changes summary for a repo")
    diff_parser.add_argument("repo", help="Repository name")
    diff_parser.add_argument("--full", action="store_true", help="Show full unified diff")

    # sync
    sync_parser = subparsers.add_parser("sync", help="Synchronize dev and prod workspaces with origin/main")
    sync_parser.add_argument("repo", nargs="?", default="all", help="Repository name or 'all'")
    sync_parser.add_argument("--discard-rogue", action="store_true", help="Discard rogue changes before syncing")

    args = parser.parse_args()

    if not args.command or args.command == "check":
        fetch = not getattr(args, "no_fetch", False)
        specific_repo = getattr(args, "repo", None)

        if specific_repo:
            data = {specific_repo: inspect_repository(specific_repo, fetch_remote=fetch)}
        else:
            data = inspect_all_repositories(fetch_remote=fetch)

        if getattr(args, "json", False):
            print(json.dumps(data, indent=2))
            return

        # Pretty print with Rich if available, otherwise formatted table
        try:
            from rich.console import Console
            from rich.table import Table

            console = Console()
            table = Table(title="🌋 Volcano Fleet Git Integrity & Parity Matrix")
            table.add_column("Repository", style="bold cyan")
            table.add_column("Dev SHA", justify="center")
            table.add_column("Origin SHA", justify="center")
            table.add_column("Prod SHA", justify="center")
            table.add_column("Rogue / Dirty", justify="center")
            table.add_column("Status", style="bold")

            status_styles = {
                "SYNCED": "[green]🟢 SYNCED[/green]",
                "ROGUE_CHANGES": "[yellow]⚠️  ROGUE CHANGES[/yellow]",
                "STALE_BASE_DIRTY": "[bold red]🛑 STALE BASE + DIRTY[/bold red]",
                "BEHIND": "[yellow]⬇️  BEHIND ORIGIN[/yellow]",
                "AHEAD": "[cyan]⬆️  AHEAD OF ORIGIN[/cyan]",
                "DIVERGED": "[magenta]🔀 DIVERGED[/magenta]",
                "PROD_OUT_OF_SYNC": "[bold red]⚠️  PROD OUT OF SYNC[/bold red]",
                "MISSING_DEV": "[red]❌ MISSING DEV[/red]",
            }

            for repo_name, s in data.items():
                rogue_txt = f"[red]{len(s['rogue_changes'])} file(s)[/red]" if not s["dev_clean"] else "[green]Clean[/green]"
                status_txt = status_styles.get(s["status"], s["status"])
                table.add_row(
                    repo_name,
                    s["dev_sha"] or "—",
                    s["origin_sha"] or "—",
                    s["prod_sha"] or "—",
                    rogue_txt,
                    status_txt,
                )

            console.print(table)

            # Print rogue change details if any
            for repo_name, s in data.items():
                if not s["dev_clean"]:
                    console.print(f"\n[bold yellow]Rogue changes in dev/{repo_name}:[/bold yellow]")
                    console.print(s["rogue_summary"])

        except ImportError:
            # Fallback plain text table
            print(f"{'Repository':<15} {'Dev SHA':<10} {'Origin SHA':<12} {'Prod SHA':<10} {'Rogue':<10} {'Status'}")
            print("-" * 75)
            for repo_name, s in data.items():
                rogue_txt = f"{len(s['rogue_changes'])} dirty" if not s["dev_clean"] else "Clean"
                print(f"{repo_name:<15} {s['dev_sha'] or '—':<10} {s['origin_sha'] or '—':<12} {s['prod_sha'] or '—':<10} {rogue_txt:<10} {s['status']}")

    elif args.command == "diff":
        repo_path = os.path.join(DEFAULT_DEV_ROOT, args.repo)
        if not os.path.isdir(repo_path):
            print(f"Error: Dev repo '{args.repo}' not found at {repo_path}")
            sys.exit(1)

        if args.full:
            diff = get_full_diff(repo_path)
            print(diff if diff else "No changes.")
        else:
            summary = get_rogue_diff_summary(repo_path)
            print(summary)

    elif args.command == "sync":
        targets = KNOWN_REPOSITORIES if args.repo == "all" else [args.repo]
        all_ok = True
        for t in targets:
            ok, msg = sync_repository(t, discard_rogue=args.discard_rogue)
            print(msg)
            if not ok:
                all_ok = False
        sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
