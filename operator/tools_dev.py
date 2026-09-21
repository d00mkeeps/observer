import os
import subprocess
import logging
import html
from tools_codebase import resolve_project_path, is_forbidden
from patch_manager import register_patch

log = logging.getLogger("operator.tools.dev")

DEV_WORKSPACE_PATH = os.environ.get("DEV_WORKSPACE_PATH", "/workspace/dev")

# Track latest test results per project: {project: {"passed": bool, "output": str, "time": float}}
_last_test_results: dict[str, dict] = {}


def prepare_dev_workspace(project: str) -> str:
    """Prepare or synchronize an isolated development workspace for a project under /workspace/dev/<project>.

    Args:
        project: Project name (e.g. 'volc', 'clear-box', 'horizon', 'observer').
    """
    prod_dir = resolve_project_path(project)
    if not prod_dir:
        return f"Error: Cannot find production repository for '{project}'."

    os.makedirs(DEV_WORKSPACE_PATH, exist_ok=True)
    dev_dir = os.path.join(DEV_WORKSPACE_PATH, project)

    try:
        # If dev dir doesn't exist, clone from prod or GitHub
        if not os.path.isdir(dev_dir):
            log.info("Initializing dev workspace for %s at %s from %s", project, dev_dir, prod_dir)
            # Use git clone from the local prod directory to create a fast, isolated clone
            res = subprocess.run(["git", "clone", prod_dir, dev_dir], capture_output=True, text=True, timeout=30)
            if res.returncode != 0:
                return f"Failed cloning into dev workspace: {res.stderr}"
            
            # Set remote URL to match production's origin URL
            remote_res = subprocess.run(["git", "config", "--get", "remote.origin.url"], cwd=prod_dir, capture_output=True, text=True)
            if remote_res.returncode == 0 and remote_res.stdout.strip():
                origin_url = remote_res.stdout.strip()
                subprocess.run(["git", "remote", "set-url", "origin", origin_url], cwd=dev_dir)
        else:
            # Sync with latest prod branch
            subprocess.run(["git", "fetch", prod_dir, "main:main"], cwd=dev_dir, capture_output=True)

        return f"Dev workspace for '{project}' is ready at {dev_dir}. Production code is untouched."
    except Exception as e:
        return f"Error preparing dev workspace for '{project}': {str(e)}"


def write_dev_file(project: str, filepath: str, content: str) -> str:
    """Write or modify a file strictly inside the /workspace/dev/<project> sandbox.

    Args:
        project: Project name.
        filepath: Relative file path within the project (e.g. 'backend/app/main.py', 'tests/test_fix.py').
        content: The complete new content to write to the file.
    """
    if is_forbidden(filepath):
        return f"Access Denied: Writing to credential file '{filepath}' is forbidden."

    dev_dir = os.path.realpath(os.path.join(DEV_WORKSPACE_PATH, project))
    if not os.path.isdir(dev_dir):
        # Auto-prepare dev workspace if needed
        prep_msg = prepare_dev_workspace(project)
        if not os.path.isdir(dev_dir):
            return prep_msg

    target_file = os.path.realpath(os.path.join(dev_dir, filepath))

    # Guardrail: Never allow escaping dev_dir
    if not target_file.startswith(dev_dir):
        return "Error: Path traversal attempt outside dev workspace."

    try:
        os.makedirs(os.path.dirname(target_file), exist_ok=True)
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote {len(content)} bytes to dev file: '{filepath}' in {project}."
    except Exception as e:
        return f"Error writing dev file: {str(e)}"


def run_dev_tests(project: str, test_command: str = "") -> str:
    """Run the test suite inside the dev workspace /workspace/dev/<project> to verify fixes.

    Args:
        project: Project name.
        test_command: Optional explicit test command (e.g. 'pytest', 'python3 -m unittest discover tests', 'npm test').
    """
    dev_dir = os.path.join(DEV_WORKSPACE_PATH, project)
    if not os.path.isdir(dev_dir):
        return f"Error: Dev workspace for '{project}' does not exist. Call 'prepare_dev_workspace' first."

    # Auto-detect test runner if not provided
    if not test_command:
        if os.path.isfile(os.path.join(dev_dir, "pytest.ini")) or os.path.isdir(os.path.join(dev_dir, "tests")):
            test_command = "pytest -q"
        elif os.path.isfile(os.path.join(dev_dir, "backend", "pytest.ini")) or os.path.isdir(os.path.join(dev_dir, "backend", "tests")):
            test_command = "pytest -q backend"
        elif os.path.isfile(os.path.join(dev_dir, "package.json")):
            test_command = "npm test --if-present"
        else:
            test_command = "python3 -m unittest discover -s . -q"

    try:
        log.info("Running dev tests in %s with command: %s", dev_dir, test_command)
        res = subprocess.run(
            test_command,
            shell=True,
            cwd=dev_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )

        passed = (res.returncode == 0)
        output = (res.stdout + "\n" + res.stderr).strip()

        _last_test_results[project] = {
            "passed": passed,
            "output": output[:500],
            "command": test_command,
        }

        if passed:
            return f"✅ ALL TESTS PASSED for {project}!\nCommand: `{test_command}`\nOutput:\n{output[:400]}"
        else:
            return f"❌ TESTS FAILED for {project} (exit code {res.returncode}):\nCommand: `{test_command}`\nOutput:\n{output[:500]}"
    except subprocess.TimeoutExpired:
        _last_test_results[project] = {"passed": False, "output": "Test execution timed out after 60s."}
        return "❌ Test execution timed out after 60s."
    except Exception as e:
        _last_test_results[project] = {"passed": False, "output": str(e)}
        return f"Error executing tests: {str(e)}"


def propose_patch(project: str, commit_message: str) -> str:
    """Generate a formal patch proposal for Telegram approval AFTER tests have passed.

    Args:
        project: Project name.
        commit_message: Clear git commit message describing the fix.
    """
    dev_dir = os.path.join(DEV_WORKSPACE_PATH, project)
    if not os.path.isdir(dev_dir):
        return f"Error: No dev workspace found for '{project}'."

    # 1. Verification Gate: Check that tests were executed and passed
    test_record = _last_test_results.get(project)
    if not test_record or not test_record.get("passed"):
        return (
            f"🛑 CANNOT PROPOSE PATCH: Tests have not passed in dev workspace!\n"
            f"Rule: All fixes must be verified by running 'run_dev_tests' before proposing a push."
        )

    # 2. Get git diff
    diff_res = subprocess.run(["git", "diff"], cwd=dev_dir, capture_output=True, text=True)
    diff = diff_res.stdout.strip()
    if not diff:
        # Check untracked files
        untracked = subprocess.run(["git", "status", "--short"], cwd=dev_dir, capture_output=True, text=True).stdout.strip()
        if not untracked:
            return f"No changes found in dev workspace for '{project}'."
        diff = f"(New untracked files added:\n{untracked})"

    # 3. Register pending patch
    patch_id = register_patch(
        project=project,
        commit_message=commit_message,
        diff=diff,
        test_summary=test_record.get("output", "All automated tests passed."),
    )

    diff_preview = diff[:300] + ("\n..." if len(diff) > 300 else "")

    return (
        f"🧪 <b>Patch Verified & Ready for Approval</b>\n"
        f"• <b>Project:</b> <code>{project}</code>\n"
        f"• <b>Patch ID:</b> <code>{patch_id}</code>\n"
        f"• <b>Commit:</b> {html.escape(commit_message)}\n"
        f"• <b>Test Verification:</b> ✅ Passed\n\n"
        f"<b>Diff Preview:</b>\n<pre>{html.escape(diff_preview)}</pre>\n\n"
        f"💡 <i>Reply with <code>/approve {patch_id}</code> to push to GitHub and deploy to live containers, or <code>/reject {patch_id}</code> to discard.</i>"
    )
