import os
import time
import uuid
import logging
import subprocess
from tools_codebase import resolve_project_path

log = logging.getLogger("operator.patch_manager")

DEV_WORKSPACE_PATH = os.environ.get("DEV_WORKSPACE_PATH", "/workspace/dev")

# Store pending verified patches: {patch_id: patch_data}
_pending_patches: dict[str, dict] = {}


def register_patch(project: str, commit_message: str, diff: str, test_summary: str, branch: str = "main") -> str:
    """Register a new test-verified patch ready for user approval."""
    patch_id = f"patch_{project}_{uuid.uuid4().hex[:6]}"
    _pending_patches[patch_id] = {
        "patch_id": patch_id,
        "project": project,
        "commit_message": commit_message,
        "diff": diff,
        "test_summary": test_summary,
        "branch": branch,
        "created_at": time.time(),
    }
    log.info("Registered pending patch %s for project %s", patch_id, project)
    return patch_id


def get_pending_patches() -> list[dict]:
    """Get all active pending patches."""
    return list(_pending_patches.values())


def get_latest_patch() -> dict | None:
    """Get the most recently proposed patch."""
    if not _pending_patches:
        return None
    # Sort by created_at descending
    return sorted(_pending_patches.values(), key=lambda p: p["created_at"], reverse=True)[0]


def apply_and_push_patch(patch_id: str = "") -> tuple[bool, str]:
    """Approve, commit, and push a test-verified patch to GitHub."""
    patch = None
    if patch_id and patch_id in _pending_patches:
        patch = _pending_patches[patch_id]
    elif not patch_id:
        patch = get_latest_patch()

    if not patch:
        return False, "No matching pending patch found to approve."

    p_id = patch["patch_id"]
    project = patch["project"]
    commit_msg = patch["commit_message"]
    branch = patch.get("branch", "main")
    dev_dir = os.path.join(DEV_WORKSPACE_PATH, project)

    if not os.path.isdir(dev_dir):
        return False, f"Dev workspace directory not found at {dev_dir}."

    try:
        # 1. Stage all changes
        add_res = subprocess.run(["git", "add", "-A"], cwd=dev_dir, capture_output=True, text=True, timeout=15)
        if add_res.returncode != 0:
            return False, f"Git add failed: {add_res.stderr}"

        # 2. Commit
        commit_res = subprocess.run(
            ["git", "commit", "-m", f"{commit_msg}\n\n[verified-by: Volcano Observer AI Agent]"],
            cwd=dev_dir,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if commit_res.returncode != 0 and "nothing to commit" not in commit_res.stdout:
            return False, f"Git commit failed: {commit_res.stderr or commit_res.stdout}"

        # 3. Push to GitHub
        push_res = subprocess.run(
            ["git", "push", "origin", branch],
            cwd=dev_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if push_res.returncode != 0:
            return False, f"Git push failed: {push_res.stderr or push_res.stdout}"

        # Clean up patch from pending
        _pending_patches.pop(p_id, None)
        log.info("Successfully pushed patch %s for %s to %s", p_id, project, branch)

        return True, (
            f"🚀 <b>Patch Approved & Pushed!</b>\n"
            f"• <b>Project:</b> <code>{project}</code>\n"
            f"• <b>Branch:</b> <code>{branch}</code>\n"
            f"• <b>Message:</b> {commit_msg}\n\n"
            f"<i>GitHub Actions CI/CD has been triggered to deploy the updated containers to Volcano.</i>"
        )
    except Exception as e:
        log.error("Exception applying patch %s: %s", p_id, e)
        return False, f"Failed pushing patch: {str(e)}"


def reject_patch(patch_id: str = "") -> tuple[bool, str]:
    """Reject and discard a proposed patch, cleaning up the dev workspace."""
    patch = None
    if patch_id and patch_id in _pending_patches:
        patch = _pending_patches[patch_id]
    elif not patch_id:
        patch = get_latest_patch()

    if not patch:
        return False, "No matching pending patch found to reject."

    p_id = patch["patch_id"]
    project = patch["project"]
    dev_dir = os.path.join(DEV_WORKSPACE_PATH, project)

    if os.path.isdir(dev_dir):
        try:
            subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=dev_dir, capture_output=True, timeout=15)
            subprocess.run(["git", "clean", "-fd"], cwd=dev_dir, capture_output=True, timeout=15)
        except Exception as e:
            log.warning("Failed resetting dev git state: %s", e)

    _pending_patches.pop(p_id, None)
    log.info("Rejected and discarded patch %s for %s", p_id, project)
    return True, f"🗑️ <b>Patch Rejected</b>: <code>{p_id}</code> for <code>{project}</code> was discarded."
