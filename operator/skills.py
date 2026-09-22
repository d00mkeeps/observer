"""Skills Management & Dynamic Progressive Disclosure Engine for Observer.

Loads, indexes, and binds Addy Osmani's Agent Skills library (and custom skills)
for on-demand activation via Telegram commands (ideate, spec, plan, build, review, ship).
"""

import os
import re
import logging
import subprocess
from pathlib import Path

log = logging.getLogger("operator.skills")

SKILLS_ROOTS = [
    Path(os.environ.get("SKILLS_PATH", "/skills")),
    Path("/skills/agent-skills/skills"),
    Path("/skills/agent-skills"),
    Path("/home/miles/skills/agent-skills/skills"),
    Path("/home/miles/skills"),
]

# Mapping of phase commands to preferred Addy Osmani skill directory names
PHASE_SKILL_MAP = {
    "ideate": ["idea-refine", "interview-me", "brainstorming"],
    "spec": ["spec-driven-development", "api-and-interface-design"],
    "plan": ["planning-and-task-breakdown"],
    "build": ["test-driven-development", "incremental-implementation"],
    "review": ["code-review-and-quality", "security-and-hardening", "code-simplification"],
    "ship": ["shipping-and-launch", "deployment-and-verification"],
}

# Strict Anti-Rationalization Guardrails
ANTI_RATIONALIZATION_RULES = """
### 🛡️ STRICT ANTI-RATIONALIZATION RULES (MANDATORY QUALITY GATES)
You must NEVER rationalize cutting corners or skipping steps:
1. ❌ DO NOT say "I'm confident this works" without running the actual automated test command.
2. ❌ DO NOT write or edit implementation code before the test harness/contract test is created (Test-First Invariant).
3. ❌ DO NOT modify or weaken existing test assertions to make failing tests pass without explicit justification.
4. ❌ DO NOT mock out entire systems when a real sandbox execution is possible.
5. ❌ DO NOT propose a patch or suggest pushing unless 100% of the test suite passes in the dev sandbox.
"""


def _find_skill_file(skill_name: str) -> Path | None:
    """Search for SKILL.md for a given skill name across all candidate roots."""
    for root in SKILLS_ROOTS:
        if not root.exists():
            continue
        # Direct folder match: root/skill_name/SKILL.md
        direct = root / skill_name / "SKILL.md"
        if direct.exists():
            return direct
        # Nested search
        for candidate in root.rglob("SKILL.md"):
            if candidate.parent.name.lower() == skill_name.lower():
                return candidate
    return None


def get_skill(skill_name: str) -> dict | None:
    """Load and parse a skill by name."""
    path = _find_skill_file(skill_name)
    if not path or not path.exists():
        return None

    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        # Extract YAML frontmatter if present
        meta = {}
        body = content
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                body = parts[2].strip()
                for line in parts[1].strip().splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip()] = v.strip()

        return {
            "name": meta.get("name", skill_name),
            "description": meta.get("description", ""),
            "path": str(path),
            "body": body,
            "full_content": content,
        }
    except Exception as e:
        log.warning("Failed to load skill %s: %s", skill_name, e)
        return None


def get_skill_for_command(command: str) -> dict | None:
    """Resolve the appropriate skill for a given phase command."""
    cmd = command.strip().lower()
    candidate_names = PHASE_SKILL_MAP.get(cmd, [cmd])

    for name in candidate_names:
        skill = get_skill(name)
        if skill:
            return skill

    # Return built-in standard fallback if repo mirror is loading
    return _get_builtin_fallback_skill(cmd)


def _get_builtin_fallback_skill(command: str) -> dict | None:
    """Fallback standard definitions for core SDLC phases."""
    fallbacks = {
        "ideate": {
            "name": "idea-refine",
            "description": "Refines and brainstorms feature ideas, architectural trade-offs, and user workflows.",
            "body": """# Ideation & Concept Refinement

1. **Problem Exploration**: Clarify what core user need or system capability is being addressed.
2. **Options & Trade-offs**: Present at least 2 distinct technical or architectural approaches with pros & cons.
3. **Constraints & Anti-Goals**: Define explicit boundaries (what we are NOT building).
4. **Recommended Path**: Provide a clear recommendation with rationale.
""",
        },
        "spec": {
            "name": "spec-driven-development",
            "description": "Generates structured product specifications and API contracts before coding.",
            "body": """# Spec-Driven Development

1. **Objectives & Success Criteria**: Measurable outcomes.
2. **Functional Requirements**: Step-by-step capabilities.
3. **API Contracts / Schemas**: Exact endpoint routes, request bodies, query params, and status codes.
4. **Edge Cases & Error States**: Explicit failure modes and boundary handling.
5. **Anti-Goals**: Explicitly out-of-scope items.
""",
        },
        "plan": {
            "name": "planning-and-task-breakdown",
            "description": "Decomposes specifications into atomic, test-gated implementation tasks.",
            "body": """# Implementation Planning & Task Breakdown

1. **Prerequisites & Dependencies**: Target repository and environment setup.
2. **Atomic Tasks**: Break the feature into small, independently testable steps.
3. **Test Strategy**: List of specific unit, integration, and contract tests to write first.
4. **Verification Gates**: Checkpoints that must pass before advancing.
""",
        },
        "build": {
            "name": "test-driven-development",
            "description": "Implements features using strict Test-Driven Development (Red -> Green).",
            "body": """# Test-Driven Development (TDD) Invariant

1. **Sandbox Setup**: Prepare `/workspace/dev/<project>`.
2. **Red Phase**: Write comprehensive tests FIRST (e.g. `tests/test_<feature>.py`). Run tests and confirm they fail.
3. **Green Phase**: Write the minimal production code needed to pass all tests.
4. **Refactor & Verification**: Re-run test suite. Propose patch only when 100% pass rate is achieved.
""",
        },
        "review": {
            "name": "code-review-and-quality",
            "description": "Performs security, performance, and edge-case code quality audit.",
            "body": """# Code Review & Quality Audit

1. **Correctness**: Does the code fulfill the specification without side-effects?
2. **Security & Validation**: Are inputs sanitized? No secret leaks? Auth checked?
3. **Error Handling**: Graceful recovery on network/db timeouts?
4. **Performance**: No n+1 queries or memory leaks?
""",
        },
        "ship": {
            "name": "shipping-and-launch",
            "description": "Verifies test suite, formats release notes, and deploys to production.",
            "body": """# Shipping & Release Invariant

1. **Final Verification**: Confirm all automated tests pass in sandbox.
2. **Release Summary**: Generate clean release notes summarizing new features and bugfixes.
3. **Deploy & Push**: Commit with SSH signature, push to GitHub `main`, and trigger CI/CD deploy.
""",
        },
    }
    return fallbacks.get(command)


def sync_skills_repo():
    """Background sync: git pull latest upstream skills."""
    for root in SKILLS_ROOTS:
        git_dir = root / ".git" if (root / ".git").exists() else root / "agent-skills" / ".git"
        if git_dir.exists():
            target_repo = git_dir.parent
            try:
                log.info("Syncing Agent Skills mirror at %s...", target_repo)
                res = subprocess.run(
                    ["git", "pull", "--ff-only"],
                    cwd=str(target_repo),
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                if res.returncode == 0:
                    log.info("Agent Skills mirror updated: %s", res.stdout.strip())
                else:
                    log.warning("Agent Skills git pull returned %d: %s", res.returncode, res.stderr)
            except Exception as e:
                log.warning("Skills sync failed: %s", e)
            break
