---
name: volcano-auto-docs
description: "Universal living documentation generator for Volcano projects. Auto-introspects FastAPI/Python, Next.js/Express, Docker Compose topology, and Database models into self-healing Markdown and Mermaid diagrams on push. ACTIVATE when adding, updating, or maintaining documentation across Volcano repositories."
---

# Volcano Auto-Docs System

The **Volcano Auto-Docs** system automatically maintains authoritative, living documentation across all Volcano server repositories. It extracts route tables, architecture topology, database schemas, and command catalogs without hallucinations or manual upkeep.

> [!IMPORTANT]
> **Always-Ask Policy**:
> Before installing, generating, or modifying auto-documentation scripts on any new or untracked repository, **you MUST explicitly ask the user for confirmation**. Never install auto-docs silently.

---

## Capabilities & Extracted Artifacts

| Source Code Element | Extracted Artifact | Output File | Formats & Features |
| :--- | :--- | :--- | :--- |
| **FastAPI / Python Routes** | Route table, parameters, docstrings, curl commands | `docs/API.md` | Markdown table + anchor links + curl samples |
| **Next.js / Express Routes** | API routes from `pages/api` or `app/api` | `docs/API.md` | Endpoint summary & file paths |
| **Docker Compose** | Services, ports, networks, volume mounts, memory limits | `docs/ARCHITECTURE.md` | Interactive **Mermaid.js** flowchart diagram |
| **SQLAlchemy / SQL Models** | Tables, fields, column types, vector indexes | `docs/DATABASE.md` | Interactive **Mermaid.js** ER diagram |
| **Bot / CLI Commands** | Command table, subflags, natural language features | `docs/COMMANDS.md` | Formatted cheat sheet |
| **Root README** | Living documentation index & status badges | `README.md` | Injected between `<!-- AUTO-DOCS-START -->` |

---

## Generator Tool: `volcano_docgen.py`

The generator script is completely self-contained and zero-dependency (using only Python's standard library `ast`, `re`, `json`, `pathlib`, `argparse`).

### Running the Generator

```bash
# In the root of any Volcano repository:
python3 scripts/volcano_docgen.py

# Or target a specific project directory from anywhere:
python3 /home/miles/prod/observer/scripts/volcano_docgen.py --project-dir /path/to/project --title "Project Name"
```

---

## Standard Installation Checklist for a New Repository

Follow these 4 steps whenever rolling auto-docs out to a new repository:

### 1. Ask User Confirmation
Confirm with the user that they want auto-documentation enabled on the target project.

### 2. Copy the Generator Script
Place `scripts/volcano_docgen.py` into the target repo's `scripts/` directory:
```bash
mkdir -p scripts
cp /home/miles/prod/observer/scripts/volcano_docgen.py scripts/
```

### 3. Add GitHub Actions CI/CD Step
Add the documentation generator and auto-commit step to `.github/workflows/deploy.yml` (or `.github/workflows/docs.yml`):

```yaml
permissions:
  contents: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Auto-Generate Documentation
        run: |
          python3 scripts/volcano_docgen.py

      - name: Commit and Push Documentation Updates
        uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: "docs: auto-update API and architecture specs [skip ci]"
          file_pattern: 'docs/* README.md'
```

### 4. Verify & Test
Run `python3 scripts/volcano_docgen.py` locally and verify the resulting `docs/` markdown files. Commit and push.

---

## On-Demand Telegram Integration (`@Airwavbot`)

The Observer operator exposes the documentation on demand:
* `docs` — Lists all living documentation sections.
* `docs api` — Summarizes API routes and handlers.
* `docs arch` — Shows container topology and isolation boundaries.
