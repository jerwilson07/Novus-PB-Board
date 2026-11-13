import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import bot
from test_pb_ui import record


def view_text(view):
    def walk(item):
        return [getattr(item, "content", ""), *(
            s for child in getattr(item, "children", ()) for s in walk(child)
        )]
    return "\n".join(walk(view))


class PBRosterTests(unittest.TestCase):
    def test_historical_duo_is_visible_in_public_second_place_and_approved_review(self):
        ezra = record(id=35, guild=bot.NOVUS_GUILD_ID, category="Bosses",
                      activity="Royal Titans", variant="Standard", ms=46800,
                      pb_date="2026-11-11", status="approved", members="07 Ezra",
                      member_ids="707", submitter=808)
        leader = dict(ezra, id=40, ms=37200, member_ids="222,333")
        board = bot.BossLeaderboard("Royal Titans", [("Standard", [leader, ezra])])
        self.assertIn("**0:46.80** · <@707> · What A Piety", view_text(board))
        self.assertIn("<@707> · What A Piety", view_text(bot.Review(ezra)))
        with patch.object(bot, "royal_titans_35_partner_id", 808):
            self.assertEqual(bot.public_members(ezra), "<@707> · <@808>")
        self.assertEqual(bot.public_members(dict(ezra, guild=123)), "<@707>")
        self.assertEqual(bot.public_members(dict(ezra, member_ids="707,808")), "<@707> · <@808>")

    def test_team_roster_shared_by_other_bosses_raids_and_announcements(self):
        team = record(activity="Yama", category="Bosses", variant="Standard",
                      members="Player One, Player Two", member_ids="111,222",
                      submitter=333, ms=35000)
        self.assertIn("<@111> · <@222>", view_text(bot.BossLeaderboard("Yama", [("Standard", [team])])))
        self.assertIn("<@111> · <@222>", view_text(bot.Review(team)))
        self.assertIn("<@111> · <@222>", bot.first_place_announcement(team, None))
        self.assertNotIn("<@333>", bot.public_members(team))
        self.assertEqual(bot.public_members(dict(team, member_ids="111")), "Player One · Player Two")
        raid = record(activity="Tombs of Amascut", variant="Expert · 8-Man",
                      member_ids="1,2,3,4,5,6,7,8")
        self.assertIn(" · ".join(f"<@{n}>" for n in range(1, 9)),
                      view_text(bot.RaidLeaderboard("Tombs of Amascut", [("Expert · 8-Man", [raid])])))


class PBRosterSubmitTests(unittest.IsolatedAsyncioTestCase):
    async def test_historical_mention_only_resolves_verified_named_submitter(self):
        ezra = record(id=35, guild=bot.NOVUS_GUILD_ID, category="Bosses",
                      activity="Royal Titans", variant="Standard", ms=46800,
                      pb_date="2026-11-11", members="07 Ezra", member_ids="707", submitter=808)
        member = SimpleNamespace(id=808, name="not-the-teammate", global_name=None,
                                 display_name="Someone Else")
        guild = SimpleNamespace(id=bot.NOVUS_GUILD_ID, get_member=Mock(return_value=None),
                                fetch_member=AsyncMock(return_value=member))
        with (patch.object(bot, "store", SimpleNamespace(one=AsyncMock(return_value=ezra))),
              patch.object(bot, "royal_titans_35_partner_id", None)):
            await bot.resolve_royal_titans_35_partner(guild)
            self.assertEqual(bot.public_members(ezra), "<@707> · What A Piety")
            member.display_name = "What A Piety"
            await bot.resolve_royal_titans_35_partner(guild)
            self.assertEqual(bot.public_members(ezra), "<@707> · <@808>")

    async def test_duo_requires_two_and_both_are_saved_even_if_someone_else_submits(self):
        for activity in sorted(bot.NON_SOLO_BOSSES):
            with self.subTest(activity=activity):
                i = SimpleNamespace(guild_id=123, user=SimpleNamespace(id=999),
                                    response=SimpleNamespace(send_message=AsyncMock(), defer=AsyncMock()),
                                    followup=SimpleNamespace(send=AsyncMock()))
                one = SimpleNamespace(id=111, display_name="One")
                two = SimpleNamespace(id=222, display_name="Two")
                db = SimpleNamespace(add=AsyncMock(return_value=7), attach_review=AsyncMock(),
                                     one=AsyncMock(return_value=record()))
                channel = SimpleNamespace(id=1, send=AsyncMock(return_value=SimpleNamespace(id=2)))
                with (patch.object(bot, "store", db), patch.object(bot.bot, "get_channel", return_value=channel),
                      patch.object(bot.Review, "make", new_callable=AsyncMock),
                      patch.object(bot, "datetime", wraps=datetime) as clock):
                    clock.now.return_value = datetime(2026, 11, 13, tzinfo=timezone.utc)
                    await bot.submit(i, "Bosses", activity, "Standard", "0:46.80",
                                     "11/11/2026", [one], party_size=2)
                    i.response.send_message.assert_awaited_once()
                    self.assertIn("both Discord members", i.response.send_message.await_args.args[0])
                    db.add.assert_not_called()
                    await bot.submit(i, "Bosses", activity, "Standard", "0:46.80",
                                     "11/11/2026", [one, two], party_size=2)
                    db.add.assert_awaited_once()
                    self.assertEqual(db.add.await_args.args[5:7], ("One, Two", "111,222"))
