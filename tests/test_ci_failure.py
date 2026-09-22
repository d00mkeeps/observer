"""Unit tests for GitHub Actions CI failure logging to Loki and Telegram alerts."""

import unittest
from unittest.mock import patch, MagicMock
import json
import sys
import os

# Add operator to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "operator")))

from tools_observability import push_loki_log


class TestLokiPush(unittest.TestCase):

    @patch("urllib.request.urlopen")
    def test_push_loki_log_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 204
        mock_urlopen.return_value.__enter__.return_value = mock_response

        labels = {
            "job": "github-actions",
            "container": "github-actions",
            "repository": "d00mkeeps/observer",
            "workflow": "Deploy",
            "level": "error",
        }
        msg = "Test error message"
        success = push_loki_log(labels=labels, message=msg, timestamp_ns=1700000000000000000)
        self.assertTrue(success)

        # Verify request sent to Loki
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_method(), "POST")
        self.assertIn("/loki/api/v1/push", req.full_url)
        payload = json.loads(req.data.decode("utf-8"))
        self.assertIn("streams", payload)
        self.assertEqual(payload["streams"][0]["stream"], labels)
        self.assertEqual(payload["streams"][0]["values"][0], ["1700000000000000000", msg])


if __name__ == "__main__":
    unittest.main()
