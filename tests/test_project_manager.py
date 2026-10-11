import os
import sys
import unittest
import tempfile
import yaml
from datetime import datetime, timezone, timedelta

# Add operator to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "operator")))

from project_manager import (
    load_projects_registry,
    save_projects_registry,
    get_project,
    list_projects,
    update_project,
    park_project,
    unpark_project,
    format_projects_table,
    format_markdown_summary,
)
from commands import handle_projects_command, handle_status_command


class TestProjectManager(unittest.TestCase):
    def setUp(self):
        # Create a temporary projects.yaml file for isolated testing
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.test_yaml_path = os.path.join(self.tmp_dir.name, "projects.yaml")

        self.initial_data = {
            "last_updated": "2026-10-11T12:00:00Z",
            "projects": {
                "horizon": {
                    "name": "Horizon Paper Tracker",
                    "category": "Trading / Bot",
                    "status": "parked",
                    "status_reason": "Collecting 15s ticks for 7 days",
                    "current_focus": "Tick accumulation",
                    "parked_until": "2026-10-18",
                    "next_milestone": "Quant refactor",
                    "repo_path": "/home/ubuntu/dev/horizon",
                    "containers": ["solana_paper_tracker"],
                    "notes": ["Test note 1"],
                },
                "volc": {
                    "name": "Volc AI Gym Coach",
                    "category": "iOS / AI",
                    "status": "active",
                    "status_reason": "Active development",
                    "current_focus": "Workout intake pipeline",
                    "parked_until": None,
                    "next_milestone": "Exercise matcher",
                    "repo_path": "/home/ubuntu/dev/volc",
                    "containers": ["supreme-octo-doodle-api"],
                    "notes": [],
                },
            },
        }
        with open(self.test_yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.initial_data, f)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_load_projects_registry(self):
        data = load_projects_registry(self.test_yaml_path)
        self.assertIn("projects", data)
        self.assertEqual(len(data["projects"]), 2)
        self.assertIn("horizon", data["projects"])
        self.assertEqual(data["projects"]["horizon"]["status"], "parked")

    def test_save_and_atomic_replace(self):
        data = load_projects_registry(self.test_yaml_path)
        data["projects"]["new_app"] = {
            "name": "New App",
            "status": "active",
        }
        save_projects_registry(data, self.test_yaml_path)

        reloaded = load_projects_registry(self.test_yaml_path)
        self.assertIn("new_app", reloaded["projects"])
        self.assertIn("last_updated", reloaded)

    def test_get_project_exact_and_case_insensitive(self):
        proj = get_project("horizon", self.test_yaml_path)
        self.assertIsNotNone(proj)
        self.assertEqual(proj["name"], "Horizon Paper Tracker")
        self.assertEqual(proj["slug"], "horizon")

        # Case insensitive
        proj_upper = get_project("HORIZON", self.test_yaml_path)
        self.assertIsNotNone(proj_upper)
        self.assertEqual(proj_upper["slug"], "horizon")

        # Nonexistent
        self.assertIsNone(get_project("nonexistent_app", self.test_yaml_path))

    def test_list_projects_and_filtering(self):
        all_projs = list_projects(file_path=self.test_yaml_path)
        self.assertEqual(len(all_projs), 2)

        parked = list_projects(status_filter="parked", file_path=self.test_yaml_path)
        self.assertEqual(len(parked), 1)
        self.assertEqual(parked[0]["slug"], "horizon")

        active = list_projects(status_filter="active", file_path=self.test_yaml_path)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["slug"], "volc")

    def test_update_project(self):
        updated = update_project(
            "horizon",
            {"current_focus": "New focus text", "notes": "Appended note"},
            file_path=self.test_yaml_path,
        )
        self.assertEqual(updated["current_focus"], "New focus text")
        self.assertIn("Appended note", updated["notes"])

        # Verify persisted
        reloaded = get_project("horizon", self.test_yaml_path)
        self.assertEqual(reloaded["current_focus"], "New focus text")
        self.assertIn("Appended note", reloaded["notes"])

    def test_park_and_unpark(self):
        # Park volc for 14 days
        parked = park_project("volc", days=14, reason="Temporary hold", file_path=self.test_yaml_path)
        self.assertEqual(parked["status"], "parked")
        expected_date = (datetime.now(timezone.utc) + timedelta(days=14)).strftime("%Y-%m-%d")
        self.assertEqual(parked["parked_until"], expected_date)

        # Unpark volc
        unparked = unpark_project("volc", reason="Back to work", file_path=self.test_yaml_path)
        self.assertEqual(unparked["status"], "active")
        self.assertIsNone(unparked["parked_until"])

    def test_formatting_table_and_markdown(self):
        projs = list_projects(file_path=self.test_yaml_path)
        table = format_projects_table(projs)
        self.assertIn("CANO ECOSYSTEM PROJECT REGISTRY", table)
        self.assertIn("horizon", table)
        self.assertIn("volc", table)

        data = load_projects_registry(self.test_yaml_path)
        md = format_markdown_summary(data)
        self.assertIn("# 🌋 Cano Ecosystem Project Registry", md)
        self.assertIn("Horizon Paper Tracker", md)
        self.assertIn("Volc AI Gym Coach", md)

    def test_handle_projects_command(self):
        # Temporarily point PROJECTS_YAML_PATH env var
        old_env = os.environ.get("PROJECTS_YAML_PATH")
        os.environ["PROJECTS_YAML_PATH"] = self.test_yaml_path
        try:
            # Overview
            overview = handle_projects_command([])
            self.assertIn("CANO PROJECT REGISTRY", overview)
            self.assertIn("horizon", overview)

            # Specific project
            detail = handle_projects_command(["horizon"])
            self.assertIn("Horizon Paper Tracker", detail)
            self.assertIn("PARKED", detail)

            # Not found
            not_found = handle_projects_command(["unknown_app"])
            self.assertIn("Project not found", not_found)
        finally:
            if old_env is not None:
                os.environ["PROJECTS_YAML_PATH"] = old_env
            else:
                os.environ.pop("PROJECTS_YAML_PATH", None)


if __name__ == "__main__":
    unittest.main()
