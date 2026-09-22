# 🛠️ Standard Guide: Auto-Updating Documentation for Volcano Projects

This guide defines the standard architecture and template for adding self-updating documentation to any Volcano repository (`volc`, `clearbox`, `horizon`, `qa`, `portfolio`, etc.).

> [!IMPORTANT]
> **Antigravity Instruction / Policy**:
> When an agent is working on any Volcano repository, it must **always ask the user for confirmation** before installing or generating the auto-documentation pipeline on that project.

---

## Architecture Blueprint

Every participating project includes:
1. `scripts/generate_docs.py`: A project-specific deterministic extractor that parses code AST, FastAPI/Express routes, Prisma/SQL schemas, or Docker configs into markdown docs (`docs/API.md`, `docs/ARCHITECTURE.md`, `docs/DATABASE.md`).
2. `.github/workflows/deploy.yml` (or `.github/workflows/docs.yml`): Runs the generator during CI and automatically commits the resulting markdown with `[skip ci]`.
3. `README.md` living documentation index.

```mermaid
flowchart LR
    Push[Git Push to main] --> CI[GitHub Actions Runner]
    CI --> Gen[Run scripts/generate_docs.py]
    Gen --> Diff{Docs Changed?}
    Diff -->|Yes| Commit[git-auto-commit-action: 'docs: auto-update [skip ci]']
    Diff -->|No| Skip[No commit needed]
    Commit --> Deploy[Deploy to Volcano]
    Skip --> Deploy
```

---

## 1. Fast Template: FastAPI Projects (e.g. `clearbox`, `volc`, `qa`)

Create `scripts/generate_docs.py` in the target repository root:

```python
#!/usr/bin/env python3
"""Auto-generate API documentation for FastAPI services."""
import ast
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DOCS.mkdir(parents=True, exist_ok=True)

def extract_routes(app_file: Path) -> list[dict]:
    tree = ast.parse(app_file.read_text())
    routes = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and getattr(dec.func, 'attr', '') in ('get', 'post', 'put', 'delete', 'patch'):
                    method = dec.func.attr.upper()
                    path = dec.args[0].value if dec.args and isinstance(dec.args[0], ast.Constant) else "/"
                    doc = ast.get_docstring(node) or "No description"
                    routes.append({"method": method, "path": path, "doc": doc, "func": node.name})
    return sorted(routes, key=lambda r: (r["path"], r["method"]))

def main():
    # Update with your app entrypoint:
    app_file = ROOT / "app" / "main.py"
    if not app_file.exists():
        app_file = ROOT / "main.py"
    
    routes = extract_routes(app_file)
    lines = [
        f"# API Reference ({len(routes)} Endpoints)",
        f"> *Auto-generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}*",
        "",
        "| Method | Path | Handler | Description |",
        "| :--- | :--- | :--- | :--- |",
    ]
    for r in routes:
        lines.append(f"| `{r['method']}` | `{r['path']}` | `{r['func']}()` | {r['doc']} |")
    
    (DOCS / "API.md").write_text("\n".join(lines) + "\n")
    print(f"Generated docs/API.md ({len(routes)} routes)")

if __name__ == "__main__":
    main()
```

---

## 2. GitHub Actions Integration Snippet

Add this step to `.github/workflows/deploy.yml` right before your remote deployment step:

```yaml
permissions:
  contents: write

steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-python@v5
    with:
      python-version: '3.12'

  - name: Auto-Generate Documentation
    run: |
      python3 scripts/generate_docs.py

  - name: Commit Updated Docs
    uses: stefanzweifel/git-auto-commit-action@v5
    with:
      commit_message: "docs: auto-update API and architecture specs [skip ci]"
      file_pattern: 'docs/* README.md'
```

---

## 3. Checklist for Rolling Out to a New Project

- [ ] **Ask User First**: Confirm user wants auto-documentation enabled on `<project>`.
- [ ] **Create Generator**: Place `scripts/generate_docs.py` tailored for that project's framework (FastAPI, Express, React, etc.).
- [ ] **Add Workflow Step**: Add `generate_docs` and `git-auto-commit-action` with `[skip ci]` to `.github/workflows/deploy.yml`.
- [ ] **Test Locally**: Run `python3 scripts/generate_docs.py` to confirm clean markdown output.
- [ ] **Verify CI**: Push a commit and ensure docs commit without re-triggering CI loops.
