"""Regression checks for /pbpost displaying the same home panel as #pb-leaderboard."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import bot


class PBPostTests(unittest.IsolatedAsyncioTestCase):
    def test_slash_command_registry(self):
        self.assertIsNone(bot.bot.tree.get_command("checkemojis"))
        self.assertIsNotNone(bot.bot.tree.get_command("pbpost"))
        self.assertIsNotNone(bot.bot.tree.get_command("pbpanel"))

    def test_home_panel_includes_banner_top_ten_and_three_buttons(self):
        points = [
            {
                "member_id": 123, "points": 20,
                "firsts": 2, "seconds": 3, "thirds": 1,
            },
            {
                "member_id": 456, "points": 8,
                "firsts": 1, "seconds": 1, "thirds": 0,
            },
        ]
        view = bot.Home(points)
        self.assertEqual(len(view.children), 1)
        panel = view.children[0]
        self.assertEqual(int(panel.accent_colour), bot.GOLD)
        self.assertIsInstance(panel.children[0], bot.ui.MediaGallery)
        text = "\n".join(
            child.content for child in panel.children
            if isinstance(child, bot.ui.TextDisplay)
        )
        self.assertIn("NOVUS · PERSONAL BESTS", text)
        self.assertIn("TOP 10", text)
        self.assertIn("🏆 <@123> · **20 pts**", text)
        self.assertIn("🥈 <@456> · **8 pts**", text)
        actions = [
            child for child in panel.children
            if isinstance(child, bot.ui.ActionRow)
        ]
        self.assertEqual(len(actions), 1)
        self.assertEqual(
            [button.label for button in actions[0].children],
            ["Submit PB", "PB Rules", "My PBs"],
        )
        self.assertLessEqual(len(panel.children), 10)

    async def test_pbpost_sends_exact_same_home_view_once_and_keeps_main_board(self):
        message = SimpleNamespace(id=100, jump_url="https://discord.com/channels/123/456/100")
        channel = SimpleNamespace(send=AsyncMock(return_value=message))
        current = bot.Home([
            {"member_id": 123, "points": 5, "firsts": 1, "seconds": 0, "thirds": 0}
        ])
        with (
            patch.object(bot.Home, "make", new_callable=AsyncMock, return_value=current) as make,
            patch.object(bot.store, "set_panel", new_callable=AsyncMock) as set_panel,
            patch.object(bot.store, "set_boss_board", new_callable=AsyncMock) as set_boss_board,
            patch.object(bot.store, "clear_boss_boards", new_callable=AsyncMock) as clear_boards,
        ):
            result, count = await bot.post_current_pb_board(channel, 123)

        self.assertIs(result, message)
        self.assertEqual(count, 1)
        make.assert_awaited_once_with(123)
        channel.send.assert_awaited_once()
        kwargs = channel.send.await_args.kwargs
        self.assertIs(kwargs["view"], current)
        self.assertFalse(kwargs["allowed_mentions"].everyone)
        self.assertFalse(kwargs["allowed_mentions"].users)
        self.assertFalse(kwargs["allowed_mentions"].roles)
        set_panel.assert_not_awaited()
        set_boss_board.assert_not_awaited()
        clear_boards.assert_not_awaited()

    async def test_failed_send_does_not_touch_existing_board(self):
        channel = SimpleNamespace(send=AsyncMock(side_effect=RuntimeError("send failed")))
        with (
            patch.object(bot.Home, "make", new_callable=AsyncMock, return_value=bot.Home()),
            patch.object(bot.store, "clear_boss_boards", new_callable=AsyncMock) as clear_boards,
        ):
            with self.assertRaises(RuntimeError):
                await bot.post_current_pb_board(channel, 123)
        channel.send.assert_awaited_once()
        clear_boards.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
