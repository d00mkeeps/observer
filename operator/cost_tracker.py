"""Cost Tracking & Financial Intelligence Engine for Volcano & Observer.

Tracks, attributes, and calculates expenses both overall and broken down
by app (volc, clearbox, horizon, observer, portfolio, qa) and service layer
(Gemini LLM tokens, Google Search API queries, Volcano host compute, GitHub Actions CI).
"""

import os
import json
import time
import html
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("operator.costs")

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
if not DATA_DIR.exists():
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        DATA_DIR = Path("/tmp")

COSTS_FILE = DATA_DIR / "costs.json"

# Pricing Table (in USD)
PRICING = {
    # LLM pricing per 1,000,000 tokens
    "gemini-2.5-flash": {
        "input_per_m": float(os.environ.get("PRICE_FLASH_INPUT", "0.075")),
        "output_per_m": float(os.environ.get("PRICE_FLASH_OUTPUT", "0.30")),
    },
    "gemini-2.5-pro": {
        "input_per_m": float(os.environ.get("PRICE_PRO_INPUT", "1.25")),
        "output_per_m": float(os.environ.get("PRICE_PRO_OUTPUT", "5.00")),
    },
    # Search pricing per query (first 100/day free)
    "google_search": {
        "free_per_day": 100,
        "cost_per_k": 5.00,
    },
    # Infrastructure baseline (monthly host cost in USD)
    "host_monthly_usd": float(os.environ.get("HOST_MONTHLY_COST_USD", "15.00")),
    # GitHub Actions Linux runner per minute (first 2,000 mins/mo free)
    "github_actions_per_min": 0.008,
    "github_actions_free_mins": 2000,
}

KNOWN_APPS = ["observer", "volc", "clearbox", "horizon", "portfolio", "qa", "tax", "brain"]


class CostTracker:
    """Manages recording, persistent storage, and rollup reporting for all system expenses."""

    def __init__(self, file_path: Path = COSTS_FILE):
        self.file_path = file_path
        self._data = self._load()

    def _get_today_str(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _get_current_month_str(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m")

    def _load(self) -> dict:
        if self.file_path.exists():
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                log.warning("Failed to load costs ledger from %s: %s", self.file_path, e)
        return {"days": {}}

    def _save(self):
        try:
            temp_file = self.file_path.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
            temp_file.replace(self.file_path)
        except Exception as e:
            log.warning("Failed to save costs ledger to %s: %s", self.file_path, e)

    def _ensure_day(self, day_str: str) -> dict:
        if "days" not in self._data:
            self._data["days"] = {}
        if day_str not in self._data["days"]:
            self._data["days"][day_str] = {
                "apps": {app: {"llm_cost": 0.0, "llm_input_tokens": 0, "llm_output_tokens": 0, "search_calls": 0, "ci_seconds": 0, "ci_runs": 0} for app in KNOWN_APPS},
                "services": {
                    "gemini_llm": {"cost": 0.0, "input_tokens": 0, "output_tokens": 0, "calls": 0},
                    "google_search": {"cost": 0.0, "calls": 0},
                    "github_actions": {"cost": 0.0, "seconds": 0, "runs": 0},
                    "infrastructure": {"cost": round(PRICING["host_monthly_usd"] / 30.0, 4)},
                },
            }
        return self._data["days"][day_str]

    def record_llm_usage(self, app: str, model: str, input_tokens: int, output_tokens: int):
        """Record token usage and compute dollar cost for a Gemini turn."""
        app = app.lower() if app else "observer"
        if app not in KNOWN_APPS:
            app = "observer"

        model_key = "gemini-2.5-pro" if "pro" in model.lower() else "gemini-2.5-flash"
        pricing = PRICING.get(model_key, PRICING["gemini-2.5-flash"])

        in_cost = (input_tokens / 1_000_000.0) * pricing["input_per_m"]
        out_cost = (output_tokens / 1_000_000.0) * pricing["output_per_m"]
        turn_cost = round(in_cost + out_cost, 6)

        day_str = self._get_today_str()
        day_entry = self._ensure_day(day_str)

        # Update per-app
        if app not in day_entry["apps"]:
            day_entry["apps"][app] = {"llm_cost": 0.0, "llm_input_tokens": 0, "llm_output_tokens": 0, "search_calls": 0, "ci_seconds": 0, "ci_runs": 0}
        app_rec = day_entry["apps"][app]
        app_rec["llm_cost"] = round(app_rec.get("llm_cost", 0.0) + turn_cost, 6)
        app_rec["llm_input_tokens"] = app_rec.get("llm_input_tokens", 0) + input_tokens
        app_rec["llm_output_tokens"] = app_rec.get("llm_output_tokens", 0) + output_tokens

        # Update per-service
        svc_rec = day_entry["services"]["gemini_llm"]
        svc_rec["cost"] = round(svc_rec.get("cost", 0.0) + turn_cost, 6)
        svc_rec["input_tokens"] = svc_rec.get("input_tokens", 0) + input_tokens
        svc_rec["output_tokens"] = svc_rec.get("output_tokens", 0) + output_tokens
        svc_rec["calls"] = svc_rec.get("calls", 0) + 1

        self._save()
        log.info("Recorded LLM usage for %s (%s): %d in, %d out -> $%.6f", app, model_key, input_tokens, output_tokens, turn_cost)

    def record_search_usage(self, app: str = "observer"):
        """Record a Google Custom Search query and track billable overflow if any."""
        app = app.lower() if app else "observer"
        day_str = self._get_today_str()
        day_entry = self._ensure_day(day_str)

        if app not in day_entry["apps"]:
            day_entry["apps"][app] = {"llm_cost": 0.0, "llm_input_tokens": 0, "llm_output_tokens": 0, "search_calls": 0, "ci_seconds": 0, "ci_runs": 0}
        day_entry["apps"][app]["search_calls"] = day_entry["apps"][app].get("search_calls", 0) + 1

        svc = day_entry["services"]["google_search"]
        svc["calls"] = svc.get("calls", 0) + 1
        free_limit = PRICING["google_search"]["free_per_day"]
        if svc["calls"] > free_limit:
            overflow_cost = round((1 / 1000.0) * PRICING["google_search"]["cost_per_k"], 4)
            svc["cost"] = round(svc.get("cost", 0.0) + overflow_cost, 4)

        self._save()

    def record_ci_usage(self, app: str, duration_seconds: int = 45):
        """Record a GitHub Actions CI workflow run."""
        app = app.lower() if app else "observer"
        day_str = self._get_today_str()
        day_entry = self._ensure_day(day_str)

        if app not in day_entry["apps"]:
            day_entry["apps"][app] = {"llm_cost": 0.0, "llm_input_tokens": 0, "llm_output_tokens": 0, "search_calls": 0, "ci_seconds": 0, "ci_runs": 0}
        app_rec = day_entry["apps"][app]
        app_rec["ci_seconds"] = app_rec.get("ci_seconds", 0) + duration_seconds
        app_rec["ci_runs"] = app_rec.get("ci_runs", 0) + 1

        svc = day_entry["services"]["github_actions"]
        svc["seconds"] = svc.get("seconds", 0) + duration_seconds
        svc["runs"] = svc.get("runs", 0) + 1

        self._save()

    def get_summary(self, timeframe: str = "month") -> dict:
        """Calculate total spend, per-app breakdown, and per-service breakdown for a timeframe."""
        target_prefix = self._get_current_month_str() if timeframe == "month" else self._get_today_str()
        days_data = {k: v for k, v in self._data.get("days", {}).items() if k.startswith(target_prefix)}

        app_totals = {}
        service_totals = {
            "gemini_llm": {"cost": 0.0, "input_tokens": 0, "output_tokens": 0, "calls": 0},
            "google_search": {"cost": 0.0, "calls": 0},
            "github_actions": {"cost": 0.0, "minutes": 0.0, "runs": 0},
            "infrastructure": {"cost": 0.0},
        }

        for day, content in days_data.items():
            # Rollup services
            for svc_name, svc_val in content.get("services", {}).items():
                if svc_name not in service_totals:
                    service_totals[svc_name] = {"cost": 0.0}
                service_totals[svc_name]["cost"] += svc_val.get("cost", 0.0)
                if svc_name == "gemini_llm":
                    service_totals[svc_name]["input_tokens"] += svc_val.get("input_tokens", 0)
                    service_totals[svc_name]["output_tokens"] += svc_val.get("output_tokens", 0)
                    service_totals[svc_name]["calls"] += svc_val.get("calls", 0)
                elif svc_name == "google_search":
                    service_totals[svc_name]["calls"] += svc_val.get("calls", 0)
                elif svc_name == "github_actions":
                    service_totals[svc_name]["minutes"] += round(svc_val.get("seconds", 0) / 60.0, 1)
                    service_totals[svc_name]["runs"] += svc_val.get("runs", 0)

            # Rollup apps
            for app_name, app_val in content.get("apps", {}).items():
                if app_name not in app_totals:
                    app_totals[app_name] = {
                        "llm_cost": 0.0,
                        "llm_input_tokens": 0,
                        "llm_output_tokens": 0,
                        "search_calls": 0,
                        "ci_minutes": 0.0,
                        "ci_runs": 0,
                        "total_cost": 0.0,
                    }
                rec = app_totals[app_name]
                rec["llm_cost"] += app_val.get("llm_cost", 0.0)
                rec["llm_input_tokens"] += app_val.get("llm_input_tokens", 0)
                rec["llm_output_tokens"] += app_val.get("llm_output_tokens", 0)
                rec["search_calls"] += app_val.get("search_calls", 0)
                rec["ci_minutes"] += round(app_val.get("ci_seconds", 0) / 60.0, 1)
                rec["ci_runs"] += app_val.get("ci_runs", 0)

        # Allocate prorated infra cost across active apps
        active_apps_count = max(1, len([a for a, v in app_totals.items() if (v["llm_cost"] > 0 or v["ci_runs"] > 0 or a in ("volc", "clearbox", "horizon", "observer"))]))
        infra_per_app = (service_totals["infrastructure"]["cost"]) / active_apps_count if active_apps_count else 0.0

        for app_name, rec in app_totals.items():
            rec["infra_cost"] = round(infra_per_app, 4) if (rec["llm_cost"] > 0 or rec["ci_runs"] > 0 or app_name in ("volc", "clearbox", "horizon", "observer")) else 0.0
            rec["total_cost"] = round(rec["llm_cost"] + rec.get("infra_cost", 0.0), 4)

        total_system_cost = sum(s.get("cost", 0.0) for s in service_totals.values())

        return {
            "timeframe": timeframe,
            "period": target_prefix,
            "total_cost_usd": round(total_system_cost, 4),
            "by_app": app_totals,
            "by_service": service_totals,
        }

    def format_telegram_card(self, app_filter: str | None = None, timeframe: str = "month") -> str:
        """Construct a formatted Telegram HTML card summarizing costs."""
        summary = self.get_summary(timeframe=timeframe)
        total = summary["total_cost_usd"]
        period_title = "Month-to-Date" if timeframe == "month" else "Today"

        if app_filter:
            app_clean = app_filter.lower().strip()
            app_data = summary["by_app"].get(app_clean)
            if not app_data:
                return f"ℹ️ No recorded usage for app <code>{html.escape(app_filter)}</code> in {period_title} ({summary['period']})."

            tokens_in = app_data.get("llm_input_tokens", 0)
            tokens_out = app_data.get("llm_output_tokens", 0)
            llm_cost = app_data.get("llm_cost", 0.0)
            infra_cost = app_data.get("infra_cost", 0.0)
            app_total = app_data.get("total_cost", 0.0)
            searches = app_data.get("search_calls", 0)
            ci_runs = app_data.get("ci_runs", 0)
            ci_mins = app_data.get("ci_minutes", 0.0)

            return (
                f"💳 <b>Cost Breakdown: {html.escape(app_clean.upper())}</b> ({period_title})\n"
                f"• <b>Total Cost:</b> <code>${app_total:.4f} USD</code>\n\n"
                f"🧠 <b>Gemini LLM Tokens:</b>\n"
                f"  - Input: <code>{tokens_in:,}</code> tokens\n"
                f"  - Output: <code>{tokens_out:,}</code> tokens\n"
                f"  - Token Cost: <code>${llm_cost:.4f}</code>\n\n"
                f"🖥️ <b>Infrastructure Share:</b> <code>${infra_cost:.4f}</code>\n"
                f"🔍 <b>Google Searches:</b> <code>{searches}</code> queries ($0.00 free)\n"
                f"⚙️ <b>GitHub Actions CI:</b> <code>{ci_runs}</code> runs ({ci_mins:.1f}m) ($0.00 free)\n\n"
                f"<i>Period: {summary['period']}</i>"
            )

        # Full Overview Card
        lines = [
            f"💳 <b>Volcano Fleet Cost Intelligence</b> ({period_title})",
            f"• <b>Total Estimated Cost:</b> <code>${total:.4f} USD</code>\n",
            f"📊 <b>Breakdown by Service:</b>",
        ]

        svc = summary["by_service"]
        llm_c = svc.get("gemini_llm", {}).get("cost", 0.0)
        llm_tok = svc.get("gemini_llm", {}).get("input_tokens", 0) + svc.get("gemini_llm", {}).get("output_tokens", 0)
        infra_c = svc.get("infrastructure", {}).get("cost", 0.0)
        search_c = svc.get("google_search", {}).get("cost", 0.0)
        search_cnt = svc.get("google_search", {}).get("calls", 0)
        ci_runs = svc.get("github_actions", {}).get("runs", 0)
        ci_mins = svc.get("github_actions", {}).get("minutes", 0.0)

        lines.append(f"• <b>Gemini AI:</b> <code>${llm_c:.4f}</code> (<code>{llm_tok:,}</code> tokens)")
        lines.append(f"• <b>Host Compute:</b> <code>${infra_c:.4f}</code> (Volcano baseline)")
        lines.append(f"• <b>Google Search:</b> <code>${search_c:.4f}</code> (<code>{search_cnt}</code> free queries)")
        lines.append(f"• <b>GitHub Actions CI:</b> <code>$0.0000</code> (<code>{ci_runs}</code> runs, {ci_mins:.1f}m free)")

        lines.append("\n📱 <b>Breakdown by App:</b>")
        sorted_apps = sorted(
            summary["by_app"].items(),
            key=lambda x: -x[1].get("total_cost", 0.0)
        )

        for app_name, d in sorted_apps:
            c = d.get("total_cost", 0.0)
            t_in = d.get("llm_input_tokens", 0)
            t_out = d.get("llm_output_tokens", 0)
            lines.append(f"• <code>{app_name}</code>: <b>${c:.4f}</b> (LLM: ${d.get('llm_cost', 0):.4f} | {t_in+t_out:,} tokens)")

        lines.append(f"\n💡 <i>Use <code>/cost &lt;app&gt;</code> for individual app details.</i>")
        return "\n".join(lines)


# Singleton instance
cost_tracker = CostTracker()
