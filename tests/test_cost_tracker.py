"""Unit tests for Cost Tracking & Financial Intelligence engine."""

import unittest
from pathlib import Path
import tempfile
import sys
import os

# Add operator to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "operator")))

from cost_tracker import CostTracker
from commands import handle_cost_command


class TestCostTracker(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_file = Path(self.temp_dir.name) / "test_costs.json"
        self.tracker = CostTracker(file_path=self.test_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_record_llm_usage_flash(self):
        # 10,000 input tokens, 2,000 output tokens for gemini-2.5-flash
        # Input: 10,000 / 1M * 0.075 = $0.00075
        # Output: 2,000 / 1M * 0.30 = $0.0006
        # Total = $0.00135
        self.tracker.record_llm_usage(app="volc", model="gemini-2.5-flash", input_tokens=10000, output_tokens=2000)

        summary = self.tracker.get_summary(timeframe="today")
        volc = summary["by_app"]["volc"]
        self.assertEqual(volc["llm_input_tokens"], 10000)
        self.assertEqual(volc["llm_output_tokens"], 2000)
        self.assertAlmostEqual(volc["llm_cost"], 0.00135, places=5)

        svc = summary["by_service"]["gemini_llm"]
        self.assertAlmostEqual(svc["cost"], 0.00135, places=5)
        self.assertEqual(svc["calls"], 1)

    def test_record_search_and_ci(self):
        self.tracker.record_search_usage(app="clearbox")
        self.tracker.record_ci_usage(app="clearbox", duration_seconds=60)

        summary = self.tracker.get_summary(timeframe="today")
        cb = summary["by_app"]["clearbox"]
        self.assertEqual(cb["search_calls"], 1)
        self.assertEqual(cb["ci_runs"], 1)
        self.assertAlmostEqual(cb["ci_minutes"], 1.0, places=1)

    def test_telegram_card_formatting(self):
        self.tracker.record_llm_usage(app="observer", model="gemini-2.5-flash", input_tokens=50000, output_tokens=5000)
        
        # General overview card
        overview = self.tracker.format_telegram_card(app_filter=None, timeframe="month")
        self.assertIn("Volcano Fleet Cost Intelligence", overview)
        self.assertIn("Gemini AI", overview)
        self.assertIn("observer", overview)

        # Single app card
        app_card = self.tracker.format_telegram_card(app_filter="observer", timeframe="month")
        self.assertIn("Cost Breakdown: OBSERVER", app_card)
        self.assertIn("Gemini LLM Tokens", app_card)


class TestCostCommand(unittest.TestCase):

    def test_handle_cost_command(self):
        card = handle_cost_command([])
        self.assertIn("Cost Intelligence", card)

        volc_card = handle_cost_command(["volc"])
        self.assertTrue("Cost Breakdown: VOLC" in volc_card or "No recorded usage" in volc_card)


if __name__ == "__main__":
    unittest.main()
