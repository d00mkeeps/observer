"""Unit tests for Research and Intelligence tools, rate limiting, and cost guardrails."""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add operator to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "operator")))

from tools_research import (
    DailyQuotaTracker,
    RateLimiter,
    search_google_web,
    search_google_books,
    search_google_trends,
    search_arxiv,
    search_app_store_reviews,
)


class TestQuotaAndRateLimiter(unittest.TestCase):

    def test_daily_quota_tracker_blocks_over_limit(self):
        tracker = DailyQuotaTracker()
        tracker.DAILY_LIMITS["test_service"] = 2

        can_call, err = tracker.can_consume("test_service")
        self.assertTrue(can_call)
        tracker.consume("test_service")

        can_call, err = tracker.can_consume("test_service")
        self.assertTrue(can_call)
        tracker.consume("test_service")

        # 3rd call should be blocked
        can_call, err = tracker.can_consume("test_service")
        self.assertFalse(can_call)
        self.assertIn("Daily free quota reached", err)

    def test_rate_limiter_min_interval(self):
        limiter = RateLimiter()
        limiter.MIN_INTERVALS["test_service"] = 0.05
        limiter.throttle("test_service")
        # Second immediate throttle should execute without error
        limiter.throttle("test_service")


class TestGoogleCustomSearch(unittest.TestCase):

    def test_missing_cse_id_message(self):
        with patch.dict(os.environ, {"GOOGLE_CSE_ID": ""}):
            result = search_google_web("competitor query")
            self.assertIn("GOOGLE_CSE_ID", result)

    @patch("urllib.request.urlopen")
    def test_google_web_search_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b"""{
            "items": [
                {
                    "title": "Whoop Fitness Tracker",
                    "link": "https://www.whoop.com",
                    "snippet": "Wearable fitness device tracking recovery and sleep."
                }
            ]
        }"""
        mock_urlopen.return_value.__enter__.return_value = mock_response

        with patch.dict(os.environ, {"GOOGLE_CSE_ID": "mock_cx_id", "GOOGLE_SEARCH_API_KEY": "mock_key"}):
            result = search_google_web("Whoop fitness", max_results=3)
            self.assertIn("Whoop Fitness Tracker", result)
            self.assertIn("https://www.whoop.com", result)


class TestGoogleBooks(unittest.TestCase):

    @patch("urllib.request.urlopen")
    def test_google_books_parsing(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b"""{
            "items": [
                {
                    "volumeInfo": {
                        "title": "Exercise Physiology: Human Bioenergetics",
                        "authors": ["George A. Brooks", "Thomas D. Fahey"],
                        "publishedDate": "2004",
                        "pageCount": 876,
                        "description": "Comprehensive textbook on exercise physiology and metabolism.",
                        "infoLink": "https://books.google.com/books/123"
                    }
                }
            ]
        }"""
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = search_google_books("exercise physiology", max_results=2)
        self.assertIn("Exercise Physiology: Human Bioenergetics", result)
        self.assertIn("George A. Brooks", result)
        self.assertIn("876", result)


class TestArxivSearch(unittest.TestCase):

    @patch("urllib.request.urlopen")
    def test_arxiv_atom_parsing(self, mock_urlopen):
        sample_atom = b"""<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <id>http://arxiv.org/abs/2301.00001</id>
                <title>Real-Time Human Pose Estimation on Mobile Devices</title>
                <summary>We present a lightweight neural network architecture for real-time human pose estimation on smartphones.</summary>
                <published>2023-01-01T00:00:00Z</published>
                <author><name>Jane Doe</name></author>
            </entry>
        </feed>"""
        mock_response = MagicMock()
        mock_response.read.return_value = sample_atom
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = search_arxiv("pose estimation mobile", max_results=2)
        self.assertIn("Real-Time Human Pose Estimation on Mobile Devices", result)
        self.assertIn("Jane Doe", result)
        self.assertIn("http://arxiv.org/abs/2301.00001", result)


class TestAppStoreReviews(unittest.TestCase):

    @patch("urllib.request.urlopen")
    def test_app_store_reviews_parsing(self, mock_urlopen):
        # First call is iTunes search, second is RSS reviews
        search_json = b"""{
            "results": [
                {"trackId": 6751469055, "trackName": "Volc AI Gym Coach"}
            ]
        }"""
        rss_json = b"""{
            "feed": {
                "entry": [
                    {"im:name": {"label": "Volc AI Gym Coach"}},
                    {
                        "im:rating": {"label": "1"},
                        "title": {"label": "Crash on iOS 17"},
                        "content": {"label": "The camera crashes when doing squats."},
                        "author": {"name": {"label": "AngryUser"}},
                        "im:version": {"label": "1.2.0"}
                    }
                ]
            }
        }"""
        resp1 = MagicMock()
        resp1.read.return_value = search_json
        resp2 = MagicMock()
        resp2.read.return_value = rss_json

        mock_urlopen.return_value.__enter__.side_effect = [resp1, resp2]

        result = search_app_store_reviews("Volc AI Gym Coach", country="us", max_results=2)
        self.assertIn("Volc AI Gym Coach", result)
        self.assertIn("Crash on iOS 17", result)
        self.assertIn("The camera crashes when doing squats", result)
        self.assertIn("AngryUser", result)


if __name__ == "__main__":
    unittest.main()
