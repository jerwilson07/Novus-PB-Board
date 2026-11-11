"""Regression checks for publicly posted PB board copies and slash command cleanup."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import bot


class FakeMessage:
    def __init__(self, number):
        self.id = number
        self.jump_url = f"https://discord.com/channels/123/456/{number}"
        self.edit = AsyncMock()
        self.delete = AsyncMock()


class PBPostTests(unittest.IsolatedAsyncioTestCase):
    def test_slash_command_registry(self):
        self.assertIsNone(bot.bot.tree.get_command("checkemojis"))
        self.assertIsNotNone(bot.bot.tree.get_command("pbpost"))
        self.assertIsNotNone(bot.bot.tree.get_command("pbpanel"))

    async def test_public_board_copy_has_every_activity_and_does_not_replace_main_board(self):
        messages = []
        async def fake_send(*args, **kwargs):
            msg = FakeMessage(1000 + len(messages))
            messages.append((msg, args, kwargs))
            return msg
        channel = SimpleNamespace(send=AsyncMock(side_effect=fake_send))
        expected_activities = 3 + len(bot.RAIDS) + len(bot.BOSSES) - 3

        with (
            patch.object(bot.Home, "make", new_callable=AsyncMock, return_value=bot.Home()),
            patch.object(bot.SnapshotPanel, "make", new_callable=AsyncMock,
                         return_value=bot.SnapshotPanel()),
            patch.object(bot.BossLeaderboard, "make", new_callable=AsyncMock,
                         return_value=bot.BossLeaderboard("Vorkath", [("Standard", [])])) as boss_make,
            patch.object(bot.RaidLeaderboard, "make", new_callable=AsyncMock,
                         return_value=bot.RaidLeaderboard("The Fractured Archive", [("Solo", [])])) as raid_make,
            patch.object(bot.store, "set_panel", new_callable=AsyncMock) as set_panel,
            patch.object(bot.store, "set_boss_board", new_callable=AsyncMock) as set_boss_board,
            patch.object(bot.store, "clear_boss_boards", new_callable=AsyncMock) as clear_boards,
            patch.object(bot.asyncio, "sleep", new_callable=AsyncMock),
        ):
            home, total = await bot.post_current_pb_board(channel, 123)

        self.assertEqual(total, expected_activities + 4)
        self.assertEqual(len(messages), total)
        self.assertEqual(home.id, messages[0][0].id)
        self.assertEqual(raid_make.await_count, len(bot.RAIDS))
        self.assertEqual(boss_make.await_count, len(bot.BOSSES))
        self.assertFalse(messages[0][2]["allowed_mentions"].everyone)
        self.assertFalse(messages[0][2]["allowed_mentions"].users)
        self.assertFalse(messages[0][2]["allowed_mentions"].roles)
        self.assertEqual(messages[1][0].edit.await_count, 1)
        directory_view = messages[1][0].edit.await_args.kwargs["view"]
        self.assertIsInstance(directory_view, bot.BossDirectory)
        self.assertEqual(len(directory_view.children), 1)
        self.assertEqual(messages[-1][1][0].count(home.jump_url), 1)
        set_panel.assert_not_awaited()
        set_boss_board.assert_not_awaited()
        clear_boards.assert_not_awaited()

    async def test_failed_copy_deletes_only_the_messages_just_posted(self):
        messages = []
        async def fake_send(*args, **kwargs):
            if len(messages) == 3:
                raise RuntimeError("simulated send failure")
            msg=FakeMessage(2000 + len(messages))
            messages.append(msg)
            return msg
        channel = SimpleNamespace(send=AsyncMock(side_effect=fake_send))
        with (
            patch.object(bot.Home,"make",new_callable=AsyncMock,return_value=bot.Home()),
            patch.object(bot.BossLeaderboard,"make",new_callable=AsyncMock,
                         return_value=bot.BossLeaderboard("Vorkath",[("Standard",[])])),
            patch.object(bot.asyncio,"sleep",new_callable=AsyncMock),
        ):
            with self.assertRaises(RuntimeError):
                await bot.post_current_pb_board(channel,123)
        self.assertEqual(len(messages),3)
        for msg in messages:
            msg.delete.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
