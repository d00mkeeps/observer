#!/usr/bin/env python3
"""Volcano Universal Documentation Generator (volcano_docgen).

A zero-dependency, multi-framework documentation generator that auto-detects
and introspects FastAPI, Express/Next.js, Docker Compose, and Database schemas
into self-healing, living Markdown docs and Mermaid.js diagrams.
"""

import os
import re
import ast
import json
import argparse
from pathlib import Path
from datetime import datetime


class VolcanoDocGen:
    def __init__(self, project_dir: Path, output_dir: Path | None = None, title: str | None = None):
        self.project_dir = project_dir.resolve()
        self.output_dir = (output_dir or (self.project_dir / "docs")).resolve()
        self.title = title or self.project_dir.name.replace("-", " ").replace("_", " ").title()
        self.generated_files = []

    def run(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        print(f"🌋 Generating documentation for '{self.title}' in {self.project_dir}...")

        # 1. Detect & Extract API routes
        routes = self.extract_api_routes()
        if routes:
            api_md = self.generate_api_markdown(routes)
            api_file = self.output_dir / "API.md"
            api_file.write_text(api_md, encoding="utf-8")
            self.generated_files.append("API.md")
            print(f"  ✅ Generated docs/API.md ({len(routes)} endpoints)")

        # 2. Detect & Extract Docker Compose Architecture
        compose_file = self._find_compose_file()
        if compose_file:
            arch_md = self.generate_architecture_markdown(compose_file)
            arch_file = self.output_dir / "ARCHITECTURE.md"
            arch_file.write_text(arch_md, encoding="utf-8")
            self.generated_files.append("ARCHITECTURE.md")
            print("  ✅ Generated docs/ARCHITECTURE.md")

        # 3. Detect & Extract Database Models / Schemas
        db_models = self.extract_db_models()
        if db_models:
            db_md = self.generate_database_markdown(db_models)
            db_file = self.output_dir / "DATABASE.md"
            db_file.write_text(db_md, encoding="utf-8")
            self.generated_files.append("DATABASE.md")
            print(f"  ✅ Generated docs/DATABASE.md ({len(db_models)} models/tables)")

        # 4. Update root README.md
        self.update_readme(routes, bool(compose_file), bool(db_models))
        print("  ✅ Updated README.md with living docs index")

    # ==========================================
    # API EXTRACTION (FastAPI & Next.js/Express)
    # ==========================================
    def extract_api_routes(self) -> list[dict]:
        routes = []
        # A. Search for Python FastAPI routes
        for py_path in self.project_dir.rglob("*.py"):
            if any(part in py_path.parts for part in ("venv", ".venv", "__pycache__", "site-packages", "node_modules", "dev")):
                continue
            routes.extend(self._parse_fastapi_file(py_path))

        # B. Search for Next.js / Express API routes
        if not routes:
            routes.extend(self._scan_node_api_routes())

        # Sort and deduplicate by (path, method)
        seen = set()
        deduped = []
        for r in sorted(routes, key=lambda x: (x["path"], x["method"])):
            key = (r["path"], r["method"])
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        return deduped

    def _parse_fastapi_file(self, file_path: Path) -> list[dict]:
        routes = []
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            return []

        rel_path = file_path.relative_to(self.project_dir)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                        obj = dec.func.value
                        attr = dec.func.attr.lower()
                        # Matches @app.get, @router.post, etc.
                        if attr in ("get", "post", "put", "delete", "patch", "options", "head"):
                            path = "/"
                            if dec.args and isinstance(dec.args[0], ast.Constant):
                                path = str(dec.args[0].value)
                            elif dec.keywords:
                                for kw in dec.keywords:
                                    if kw.arg == "path" and isinstance(kw.value, ast.Constant):
                                        path = str(kw.value.value)

                            docstring = ast.get_docstring(node) or "No description provided."
                            args = [arg.arg for arg in node.args.args if arg.arg not in ("request", "self", "db", "session")]

                            routes.append({
                                "method": attr.upper(),
                                "path": path,
                                "function": node.name,
                                "docstring": docstring,
                                "params": args,
                                "file": str(rel_path),
                                "line": node.lineno,
                            })
        return routes

    def _scan_node_api_routes(self) -> list[dict]:
        routes = []
        api_dirs = [
            self.project_dir / "pages" / "api",
            self.project_dir / "src" / "pages" / "api",
            self.project_dir / "app" / "api",
            self.project_dir / "src" / "app" / "api",
        ]
        for api_dir in api_dirs:
            if api_dir.exists():
                for route_file in api_dir.rglob("*"):
                    if route_file.suffix in (".js", ".ts", ".mjs"):
                        rel = route_file.relative_to(api_dir)
                        # Remove extension and handle index/[param]
                        path_part = str(rel.with_suffix("")).replace("\\", "/")
                        if path_part.endswith("/index") or path_part == "index":
                            path_part = path_part[:-6] if path_part.endswith("/index") else ""
                        route_path = f"/api/{path_part}".rstrip("/") or "/api"
                        routes.append({
                            "method": "ANY",
                            "path": route_path,
                            "function": route_file.stem,
                            "docstring": f"Next.js API route handler in {route_file.name}",
                            "params": [],
                            "file": str(route_file.relative_to(self.project_dir)),
                            "line": 1,
                        })
        return routes

    def generate_api_markdown(self, routes: list[dict]) -> str:
        lines = [
            f"# {self.title} API Reference",
            "",
            "> *Auto-generated on every push via GitHub Actions. Do not edit manually.*  ",
            f"> **Last Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
            f"> **Total Endpoints:** {len(routes)}",
            "",
            "## Endpoints Summary",
            "",
            "| Method | Endpoint | Handler | Source File | Description |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
        for r in routes:
            desc = r["docstring"].splitlines()[0] if r["docstring"] else "Endpoint handler"
            clean_anchor = f"{r['path'].replace('/', '').replace(':', '').replace('[', '').replace(']', '')}-{r['method'].lower()}"
            lines.append(f"| `{r['method']}` | [`{r['path']}`](#{clean_anchor}) | `{r['function']}()` | `{r['file']}:{r['line']}` | {desc} |")

        lines.extend(["", "---", "", "## Endpoint Details", ""])
        for r in routes:
            clean_anchor = f"{r['path'].replace('/', '').replace(':', '').replace('[', '').replace(']', '')}-{r['method'].lower()}"
            lines.append(f"### `{r['method']} {r['path']}`")
            lines.append(f"**Handler:** `{r['function']}()` (`{r['file']}:{r['line']}`)  ")
            lines.append(f"**Description:** {r['docstring']}  ")
            if r["params"]:
                lines.append(f"**Parameters:** `{', '.join(r['params'])}`  ")

            lines.append("")
            lines.append("```bash")
            if r["method"] == "GET":
                lines.append(f"curl -s http://127.0.0.1:8000{r['path']}")
            else:
                lines.append(f"curl -s -X {r['method']} http://127.0.0.1:8000{r['path']} \\")
                lines.append('  -H "Content-Type: application/json" \\')
                lines.append("  -d '{}'")
            lines.append("```")
            lines.append("")

        return "\n".join(lines).strip() + "\n"

    # ==========================================
    # DOCKER TOPOLOGY & ARCHITECTURE
    # ==========================================
    def _find_compose_file(self) -> Path | None:
        for name in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
            p = self.project_dir / name
            if p.exists():
                return p
        return None

    def generate_architecture_markdown(self, compose_path: Path) -> str:
        services = self._parse_compose_file(compose_path)
        nodes = []
        tables = []

        for sname, sinfo in services.items():
            cname = sinfo.get("container_name", sname)
            ports_str = f"Ports: {', '.join(sinfo['ports'])}" if sinfo["ports"] else "Internal only"
            nodes.append(f'        {sname}["<b>{cname}</b><br/>{ports_str}"]')
            tables.append(
                f"| `{cname}` | `{sname}` | `{', '.join(sinfo['ports']) or 'None'}` | `{', '.join(sinfo['volumes']) or 'None'}` | `{sinfo.get('memory', 'unlimited')}` |"
            )

        nodes_text = "\n".join(nodes)
        tables_text = "\n".join(tables)

        return f"""# {self.title} Architecture & Topology

> *Auto-generated on every push via GitHub Actions. Do not edit manually.*  
> **Last Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

## Service Mesh Overview

```mermaid
graph TD
    subgraph Volcano_Host["Volcano Server (Docker Mesh)"]
{nodes_text}
    end

    External[Client / Ingress] --> Volcano_Host
```

---

## Container Specifications

| Container Name | Service Name | Mapped Ports | Volumes | Memory Limit |
| :--- | :--- | :--- | :--- | :--- |
{tables_text}
"""

    def _parse_compose_file(self, compose_path: Path) -> dict:
        content = compose_path.read_text(encoding="utf-8", errors="ignore")
        services = {}
        current_service = None

        for line in content.splitlines():
            sm = re.match(r"^  ([a-zA-Z0-9_-]+):", line)
            if sm and not line.strip().startswith("#"):
                current_service = sm.group(1)
                services[current_service] = {
                    "container_name": current_service,
                    "ports": [],
                    "volumes": [],
                    "memory": "unlimited",
                }
                continue

            if current_service:
                cm = re.match(r"^\s+container_name:\s*([a-zA-Z0-9_-]+)", line)
                if cm:
                    services[current_service]["container_name"] = cm.group(1)

                pm = re.match(r'^\s+-\s*"([^"]+)"', line)
                if pm:
                    services[current_service]["ports"].append(pm.group(1))

                vm = re.match(r"^\s+-\s+([^\s:]+:[^\s:]+(?::[a-z]+)?)", line)
                if vm:
                    services[current_service]["volumes"].append(vm.group(1))

                mem = re.match(r"^\s+memory:\s*([0-9a-zA-Z]+)", line)
                if mem:
                    services[current_service]["memory"] = mem.group(1)

        return services

    # ==========================================
    # DATABASE & SCHEMA MODELS
    # ==========================================
    def extract_db_models(self) -> list[dict]:
        models = []
        for py_path in self.project_dir.rglob("*.py"):
            if any(part in py_path.parts for part in ("venv", ".venv", "__pycache__", "node_modules", "dev")):
                continue
            models.extend(self._parse_sqlalchemy_models(py_path))
        return models

    def _parse_sqlalchemy_models(self, file_path: Path) -> list[dict]:
        models = []
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            return []

        rel = str(file_path.relative_to(self.project_dir))

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                fields = []
                is_db_model = False

                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name):
                                name = target.id
                                val_str = ast.unparse(item.value) if hasattr(ast, "unparse") else "Column"
                                if "Column" in val_str or "Field" in val_str or name.startswith("__tablename__"):
                                    is_db_model = True
                                    fields.append({"name": name, "type": val_str})

                if is_db_model or any(base.id in ("Base", "Model", "SQLModel") for base in node.bases if isinstance(base, ast.Name)):
                    models.append({
                        "name": node.name,
                        "file": rel,
                        "line": node.lineno,
                        "fields": fields,
                    })
        return models

    def generate_database_markdown(self, models: list[dict]) -> str:
        mermaid_lines = ["erDiagram"]
        for m in models:
            cname = m["name"]
            mermaid_lines.append(f"    {cname} {{")
            for f in m["fields"][:8]:  # limit fields in diagram for clarity
                fname = f["name"]
                if fname != "__tablename__":
                    ftype = f["type"].replace("Column(", "").replace(")", "").split(",")[0].strip() or "string"
                    ftype_clean = re.sub(r"[^a-zA-Z0-9_]", "", ftype) or "string"
                    mermaid_lines.append(f"        {ftype_clean} {fname}")
            mermaid_lines.append("    }")

        mermaid_block = "\n".join(mermaid_lines)

        tables = []
        for m in models:
            tables.append(f"### `{m['name']}` (Source: `{m['file']}:{m['line']}`)")
            tables.append("| Field | Definition |")
            tables.append("| :--- | :--- |")
            for f in m["fields"]:
                tables.append(f"| `{f['name']}` | `{f['type']}` |")
            tables.append("")

        tables_block = "\n".join(tables)

        return f"""# {self.title} Database Schema & Models

> *Auto-generated on every push via GitHub Actions. Do not edit manually.*  
> **Last Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

```mermaid
{mermaid_block}
```

---

## Model Specifications

{tables_block}
"""

    # ==========================================
    # ROOT README INJECTION
    # ==========================================
    def update_readme(self, routes: list, has_compose: bool, has_db: bool):
        readme_path = self.project_dir / "README.md"
        if not readme_path.exists():
            readme_content = f"# {self.title}\n\n<!-- AUTO-DOCS-START -->\n<!-- AUTO-DOCS-END -->\n"
        else:
            readme_content = readme_path.read_text(encoding="utf-8")

        links = []
        if routes:
            links.append(f"* 📘 **[API Reference](docs/API.md)**: Route catalog with {len(routes)} registered endpoints.")
        if has_compose:
            links.append("* 🏗️ **[Architecture & Topology](docs/ARCHITECTURE.md)**: Interactive Mermaid service mesh and container specifications.")
        if has_db:
            links.append("* 🗄️ **[Database Schema](docs/DATABASE.md)**: Entity-Relationship diagram and table definitions.")
        if (self.output_dir / "COMMANDS.md").exists():
            links.append("* ⚡ **[Command Reference](docs/COMMANDS.md)**: Deterministic commands and AI capabilities.")

        doc_section = "<!-- AUTO-DOCS-START -->\n## 📚 Living Documentation\n\n*Auto-generated on every push to `main`:*\n\n" + "\n".join(links) + "\n<!-- AUTO-DOCS-END -->"

        if "<!-- AUTO-DOCS-START -->" in readme_content and "<!-- AUTO-DOCS-END -->" in readme_content:
            new_content = re.sub(
                r"<!-- AUTO-DOCS-START -->.*?<!-- AUTO-DOCS-END -->",
                doc_section,
                readme_content,
                flags=re.DOTALL,
            )
        else:
            new_content = readme_content.rstrip() + "\n\n---\n\n" + doc_section + "\n"

        readme_path.write_text(new_content, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Volcano Universal Documentation Generator")
    parser.add_argument("--project-dir", type=Path, default=Path.cwd(), help="Path to project repository root")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output directory for markdown docs (default: <project>/docs)")
    parser.add_argument("--title", type=str, default=None, help="Custom human-readable project title")
    args = parser.parse_args()

    docgen = VolcanoDocGen(project_dir=args.project_dir, output_dir=args.output_dir, title=args.title)
    docgen.run()


if __name__ == "__main__":
    main()
