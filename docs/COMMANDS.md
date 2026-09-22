# Observer / Airwavbot Command Reference

> *Auto-generated on every push via GitHub Actions. Do not edit manually.*  
> **Last Generated:** 2026-09-22 11:41:02 UTC

All commands work directly in Telegram with `@Airwavbot`. Commands are **slash-optional** (e.g. `status` and `/status` behave identically).

---

## ⚡ Deterministic Commands (Instant Execution, 0 Tokens)

These commands execute deterministically against Prometheus, Loki, and local state without calling an LLM:

| Command | Subflags / Arguments | Description | Example |
| :--- | :--- | :--- | :--- |
| `status` | *(none)* | High-level fleet overview: host RAM/Disk/Load, 8 project statuses, 24h error count, pending patches. | `status` |
| `status <project>` | `volc`, `clearbox`, `horizon`, `observer`, `portfolio`, `qa`, etc. | Deep-dive status for a specific project: container states, last deploy timestamp, and 24h Loki error tally. | `status volc` |
| `status -v` | `-v`, `--verbose`, `-a`, `--all` | Verbose mode: lists every single container and individual error count. | `status -v` |
| `status host` | `host`, `-h`, `--host`, `health` | Volcano host hardware metrics (RAM GB, Disk GB, 1m load, uptime in days, active container list). | `health` |
| `errors` | `[1h\|6h\|24h\|7d]` | Direct Loki error audit across all apps over custom lookback duration (default `24h`). | `errors 1h` |
| `patches` | *(none)* | Lists all sandbox bugfix patches currently awaiting your approval. | `patches` |
| `approve <id>` | `<patch_id>` | Commits the verified sandbox patch, pushes to GitHub via SSH, and triggers GitHub Actions deployment. | `/approve patch-volc-8821` |
| `reject <id>` | `<patch_id>` | Discards sandbox changes and resets the dev workspace. | `/reject patch-volc-8821` |
| `docs` | `[api\|arch\|commands]` | View living API routes, architecture diagrams, or command references directly in Telegram. | `docs api` |
| `help` | `?`, `commands`, `start` | Displays the interactive command cheat sheet and guide. | `help` |

---

## 🧠 Conversational AI Capabilities (Antigravity Agent)

Natural language queries are handled by Gemini with full codebase inspection and Loki log access:

* **Incident Diagnosis**: *"Why did supreme-octo-doodle-api crash at 08:30?"*
* **Multi-App Error Inquiries**: *"Show me all database connection errors across all apps in the last 12 hours."*
* **Code Inspection**: *"How is JWT authentication handled in Clearbox?"*
* **Sandbox Bugfixing**: *"Fix the missing null check in Horizon's price parser and run the test suite."*
