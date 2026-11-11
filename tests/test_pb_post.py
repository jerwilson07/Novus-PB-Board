"""Regression checks for the single-message public PB Top 10 snapshot."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import bot


class PBPostTests(unittest.IsolatedAsyncioTestCase):
    def test_slash_command_registry(self):
        self.assertIsNone(bot.bot.tree.get_command("checkemojis"))
        self.assertIsNotNone(bot.bot.tree.get_command("pbpost"))
        self.assertIsNotNone(bot.bot.tree.get_command("pbpanel"))

    def test_top_ten_card_is_compact_and_keeps_scores(self):
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
        view=bot.TopTenPBPost(points,"https://discord.com/channels/1/2/3")
        self.assertEqual(len(view.children),1)
        container=view.children[0]
        self.assertEqual(int(container.accent_colour),bot.GOLD)
        self.assertLessEqual(len(container.children),3)
        text="\n".join(
            child.content for child in container.children
            if isinstance(child,bot.ui.TextDisplay)
        )
        self.assertIn("PB TOP 10",text)
        self.assertIn("🏆 <@123> · **20 pts**",text)
        self.assertIn("🥈 <@456> · **8 pts**",text)
        self.assertNotIn("Boss Directory",text)
        self.assertNotIn("RECENT PBs",text)
        links=[child for child in container.children if isinstance(child,bot.ui.ActionRow)]
        self.assertEqual(len(links),1)
        self.assertEqual(links[0].children[0].url,"https://discord.com/channels/1/2/3")

    def test_no_points_or_missing_tracked_board(self):
        view=bot.TopTenPBPost([],None)
        self.assertEqual(len(view.children),1)
        contents=[child.content for child in view.children[0].children
                  if isinstance(child,bot.ui.TextDisplay)]
        self.assertTrue(any("No approved PB points yet." in value for value in contents))
        self.assertFalse(any(isinstance(child,bot.ui.ActionRow)
                             for child in view.children[0].children))

    async def test_pbpost_sends_exactly_one_public_card_without_mutating_main_board(self):
        points=[{"member_id":123,"points":5,"firsts":1,"seconds":0,"thirds":0}]
        message=SimpleNamespace(id=100,jump_url="https://discord.com/channels/123/456/100")
        channel=SimpleNamespace(send=AsyncMock(return_value=message))
        tracked={"channel":999,"message":888}
        with (
            patch.object(bot,"calculate_pb_points",new_callable=AsyncMock,return_value=points) as scores,
            patch.object(bot.store,"panel",new_callable=AsyncMock,return_value=tracked) as panel,
            patch.object(bot.store,"set_panel",new_callable=AsyncMock) as set_panel,
            patch.object(bot.store,"set_boss_board",new_callable=AsyncMock) as set_boss_board,
            patch.object(bot.store,"clear_boss_boards",new_callable=AsyncMock) as clear_boards,
        ):
            actual,total=await bot.post_current_pb_board(channel,123)
        self.assertIs(actual,message)
        self.assertEqual(total,1)
        channel.send.assert_awaited_once()
        scores.assert_awaited_once_with(123)
        panel.assert_awaited_once_with(123)
        kwargs=channel.send.await_args.kwargs
        self.assertIsInstance(kwargs["view"],bot.TopTenPBPost)
        self.assertFalse(kwargs["allowed_mentions"].everyone)
        self.assertFalse(kwargs["allowed_mentions"].users)
        self.assertFalse(kwargs["allowed_mentions"].roles)
        link=kwargs["view"].children[0].children[-1].children[0]
        self.assertEqual(link.url,"https://discord.com/channels/123/999/888")
        set_panel.assert_not_awaited()
        set_boss_board.assert_not_awaited()
        clear_boards.assert_not_awaited()

    async def test_failed_single_send_does_not_touch_existing_board(self):
        channel=SimpleNamespace(send=AsyncMock(side_effect=RuntimeError("send failed")))
        with (
            patch.object(bot,"calculate_pb_points",new_callable=AsyncMock,return_value=[]),
            patch.object(bot.store,"panel",new_callable=AsyncMock,return_value=None),
            patch.object(bot.store,"clear_boss_boards",new_callable=AsyncMock) as clear_boards,
        ):
            with self.assertRaises(RuntimeError):
                await bot.post_current_pb_board(channel,123)
        channel.send.assert_awaited_once()
        clear_boards.assert_not_awaited()


if __name__=="__main__":
    unittest.main()
