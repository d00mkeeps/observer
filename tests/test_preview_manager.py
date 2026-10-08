import unittest
import asyncio
from unittest.mock import AsyncMock, patch
import os
import sys

# Add operator to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../operator")))

from preview_manager import (
    render_trampoline_html,
    start_preview_session,
    stop_preview_session,
    get_active_preview,
    _active_previews,
)
from telegram_handler import handle_telegram_update


class TestPreviewManager(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _active_previews.clear()

    def tearDown(self):
        _active_previews.clear()

    def test_render_trampoline_html_with_url(self):
        url = "exp+volc://expo-development-client/?url=https%3A%2F%2Ftest-tunnel.exp.direct"
        html = render_trampoline_html("volc", url)
        self.assertIn("Launching Volc Dev Preview", html)
        self.assertIn("Tap to Open in Volc", html)
        self.assertIn("test-tunnel.exp.direct", html)

    def test_render_trampoline_html_ended(self):
        html = render_trampoline_html("volc", None)
        self.assertIn("Preview Session Ended", html)
        self.assertIn("⏹️", html)

    @patch("preview_manager.send_telegram", new_callable=AsyncMock)
    async def test_start_and_stop_preview_session(self, mock_send):
        mock_send.return_value = {
            "ok": True,
            "result": {
                "message_id": 999,
                "chat": {"id": 12345},
            },
        }

        url = "exp+volc://expo-development-client/?url=https%3A%2F%2Ftest-8081.exp.direct"
        res = await start_preview_session(project="volc", tunnel_url=url, timeout_minutes=15)
        self.assertTrue(res["ok"])
        self.assertIn("trampoline_url", res)

        session = get_active_preview("volc")
        self.assertIsNotNone(session)
        self.assertEqual(session["tunnel_url"], url)
        self.assertEqual(session["message_id"], 999)

        # Verify telegram was sent with markup
        mock_send.assert_awaited_once()
        _, kwargs = mock_send.call_args
        self.assertIn("reply_markup", kwargs)
        buttons = kwargs["reply_markup"]["inline_keyboard"][0]
        self.assertEqual(buttons[0]["text"], "📱 Open in Volc")
        self.assertEqual(buttons[1]["callback_data"], "preview_stop:volc")

        # Test stop session
        with patch("preview_manager.edit_telegram_message", new_callable=AsyncMock) as mock_edit:
            stopped = await stop_preview_session("volc", reason="Test reason")
            self.assertTrue(stopped)
            self.assertIsNone(get_active_preview("volc"))
            mock_edit.assert_awaited_once()
            _, edit_kwargs = mock_edit.call_args
            self.assertEqual(edit_kwargs["chat_id"], 12345)
            self.assertEqual(edit_kwargs["message_id"], 999)
            self.assertIn("VOLC Dev Preview Closed", edit_kwargs["text"])

    @patch("telegram_handler.is_authorized", return_value=True)
    @patch("telegram_handler.answer_callback_query", new_callable=AsyncMock)
    @patch("preview_manager.edit_telegram_message", new_callable=AsyncMock)
    @patch("preview_manager.send_telegram", new_callable=AsyncMock)
    async def test_telegram_callback_stop_preview(self, mock_send, mock_edit, mock_answer, mock_auth):
        mock_send.return_value = {"ok": True, "result": {"message_id": 100, "chat": {"id": 555}}}
        await start_preview_session(project="volc", tunnel_url="exp+volc://test", timeout_minutes=10)

        update = {
            "callback_query": {
                "id": "cb_query_123",
                "from": {"id": 555, "first_name": "Miles"},
                "message": {"message_id": 100, "chat": {"id": 555}},
                "data": "preview_stop:volc",
            }
        }

        result = await handle_telegram_update(update)
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "preview_stopped")
        self.assertEqual(result["project"], "volc")
        mock_answer.assert_awaited_once()
        self.assertIsNone(get_active_preview("volc"))


if __name__ == "__main__":
    unittest.main()
