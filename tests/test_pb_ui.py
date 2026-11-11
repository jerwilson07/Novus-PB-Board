"""Smoke tests for Components V2 layouts and record presentation."""

import unittest

import bot


def record(**overrides):
    item = {
        "id": 1,
        "guild": 123,
        "submitter": 456,
        "category": "Raids",
        "activity": "The Fractured Archive",
        "variant": "Trio",
        "members": "Vecs, Mohi, Hokage",
        "member_ids": "456,789,100",
        "ms": 872600,
        "pb_date": "2026-11-07",
        "proof": "https://example.com/proof.png",
        "status": "pending",
        "updated": "2026-11-07T22:00:00+00:00",
    }
    item.update(overrides)
    return item


class PBLayoutTests(unittest.TestCase):
    def test_raid_order_and_tfa_name(self):
        self.assertEqual(
            list(bot.RAIDS),
            [
                "The Fractured Archive",
                "Theatre of Blood",
                "Chambers of Xeric",
                "Tombs of Amascut",
            ],
        )

    def test_public_board_and_rules_render(self):
        self.assertTrue(bot.Home())
        self.assertTrue(bot.RulesModal())
        self.assertTrue(bot.SubmitModal())

    def test_single_modal_submission_options(self):
        self.assertEqual(
            [option.label for option in bot.submission_target_options()[:4]],
            list(bot.RAIDS),
        )
        self.assertEqual(bot.submission_target_options()[-1].label, "Boss PB")
        format_labels = [option.label for option in bot.submission_format_options()]
        self.assertIn("Solo", format_labels)
        self.assertIn("Hard Mode · Trio", format_labels)
        self.assertIn("Expert · 8-Man", format_labels)
        self.assertIn("Normal", format_labels)
        self.assertIn("Awakened", format_labels)
        boss_labels = [option.label for option in bot.boss_submission_options()]
        self.assertIn("Inferno", boss_labels)
        self.assertIn("Vardorvis", boss_labels)
        self.assertTrue(bot.SubmitModal())

    def test_pb_time_then_date_format(self):
        self.assertEqual(
            bot.parse_submission_details("14:32.60 | 11-08-2026"),
            ("11-08-2026", "14:32.60"),
        )

    def test_subminute_pb_times(self):
        self.assertEqual(bot.parse_ms("30.60"), 30600)
        self.assertEqual(bot.parse_ms("00:30.60"), 30600)
        self.assertEqual(bot.parse_ms("14:32.60"), 872600)
        self.assertEqual(bot.parse_ms("1:02:03.50"), 3723500)
        self.assertEqual(bot.fmt(bot.parse_ms("30.60")), "0:30.60")
        for value in ("60.00", "00:60.00", "-5.00", "0.00"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                bot.parse_ms(value)

    def test_both_pb_date_separators(self):
        for date_value in ("11/08/2026", "11-08-2026"):
            with self.subTest(date_value=date_value):
                self.assertEqual(
                    bot.parse_submission_details(f"30.60 | {date_value}"),
                    (date_value, "30.60"),
                )
                parsed = None
                for date_format in ("%m-%d-%Y", "%Y-%m-%d", "%m/%d/%Y"):
                    try:
                        parsed = bot.datetime.strptime(date_value, date_format).date()
                        break
                    except ValueError:
                        pass
                self.assertEqual(parsed.isoformat(), "2026-11-08")

    def test_pb_cutoff_date_is_enforced(self):
        before = bot.datetime.strptime("2026-11-06", "%Y-%m-%d").date()
        cutoff = bot.datetime.strptime("2026-11-07", "%Y-%m-%d").date()
        after = bot.datetime.strptime("2026-11-08", "%Y-%m-%d").date()

        self.assertFalse(bot.pb_date_eligible(before))
        self.assertTrue(bot.pb_date_eligible(cutoff))
        self.assertTrue(bot.pb_date_eligible(after))

    def test_paired_bosses_stay_adjacent_in_submission_order(self):
        bosses = list(bot.BOSSES)
        self.assertLess(bosses.index("Gauntlet"), bosses.index("Corrupted Gauntlet"))
        self.assertEqual(bosses.index("Corrupted Gauntlet"), bosses.index("Gauntlet") + 1)
        self.assertLess(bosses.index("Doom of Mokhaiotl"), bosses.index("Demonic Brutus"))
        self.assertEqual(bosses.index("Demonic Brutus"), bosses.index("Doom of Mokhaiotl") + 1)


    def test_raid_and_boss_navigation_render(self):
        self.assertTrue(bot.RaidBrowser(123, 0, 0, []))
        self.assertTrue(bot.Browser(123, "Bosses", 0, [("Normal", [])]))

    def test_public_boards_feature_champion_and_keep_empty_slots(self):
        champion = record(id=41, category="Bosses", activity="Vorkath",
                          variant="Standard")
        runner_up = record(id=42, category="Bosses", activity="Vorkath",
                           variant="Standard", ms=925000)
        board = bot.BossLeaderboard(
            "Vorkath", [("Standard", [champion, runner_up])]
        )
        self.assertEqual(len(board.children), 1)
        panel = board.children[0]
        self.assertTrue(any(isinstance(child, bot.ui.Section)
                            and child.accessory.label == "NOVUS #1"
                            for child in panel.children))
        text = "\\n".join(
            child.content for child in panel.children
            if isinstance(child, bot.ui.TextDisplay)
        )
        self.assertNotIn("TOP 5", text)
        self.assertIn("15:25.00", text)
        self.assertIn("Empty", text)

    def test_boss_heading_and_records_share_one_container(self):
        champion = record(id=50, category="Bosses", activity="Vorkath",
                          variant="Standard")
        board = bot.BossLeaderboard("Vorkath", [("Standard", [champion])])
        self.assertEqual(len(board.children), 1)
        panel = board.children[0]
        heading = panel.children[0]
        self.assertIsInstance(heading, bot.ui.TextDisplay)
        self.assertIn("Vorkath", heading.content)
        self.assertTrue(any(isinstance(item, bot.ui.Section)
                            and item.accessory.label == "NOVUS #1"
                            for item in panel.children))
        self.assertLessEqual(len(panel.children), 10)

    def test_two_variant_boss_stays_within_discord_component_limit(self):
        first = record(id=51, category="Bosses", activity="Vardorvis",
                       variant="Normal")
        second = record(id=52, category="Bosses", activity="Vardorvis",
                        variant="Awakened")
        board = bot.BossLeaderboard(
            "Vardorvis", [("Normal", [first]), ("Awakened", [second])]
        )
        self.assertEqual(len(board.children), 1)
        self.assertLessEqual(len(board.children[0].children), 10)
        headings = [item.content for item in board.children[0].children
                    if isinstance(item, bot.ui.TextDisplay)]
        self.assertTrue(any("Normal" in item for item in headings))
        self.assertTrue(any("Awakened" in item for item in headings))

    def test_first_place_always_uses_trophy(self):
        self.assertEqual(bot.MEDALS[0], "🏆")
        self.assertNotIn("🥇", bot.short_record(record(), 0))
        self.assertIn("🏆", bot.short_record(record(), 0))
        board = bot.BossLeaderboard(
            "Vorkath", [("Standard", [record(id=53)])]
        )
        champion = next(child for child in board.children[0].children
                        if isinstance(child, bot.ui.Section))
        self.assertIn("🏆", champion.children[0].content)
        self.assertEqual(champion.accessory.label, "NOVUS #1")
        self.assertTrue(champion.accessory.disabled)
        self.assertEqual(champion.accessory.style, bot.discord.ButtonStyle.secondary)

    def test_raid_variants_have_separate_containers(self):
        modes = bot.RAIDS["Theatre of Blood"]
        board = bot.RaidLeaderboard(
            "Theatre of Blood", [(variant, []) for variant in modes]
        )
        self.assertEqual(len(board.children), 1 + len(modes))
        for variant_panel in board.children[1:]:
            self.assertLessEqual(len(variant_panel.children), 10)

    def test_browsers_feature_first_record_with_native_section(self):
        first = record(id=71, category="Bosses", activity="Vorkath",
                       variant="Standard")
        boss = bot.Browser(123, "Bosses",
                           list(bot.BOSSES).index("Vorkath"),
                           [("Standard", [first])])
        raid = bot.RaidBrowser(123, 0, 0, [record(id=72)])
        for view in (boss, raid):
            self.assertTrue(
                any(isinstance(child, bot.ui.Section)
                    and child.accessory.label == "NOVUS #1"
                    for panel in view.children
                    for child in getattr(panel, "children", []))
            )


    def test_empty_board_prompt_and_no_claimed_counter(self):
        board = bot.BossLeaderboard("Vorkath", [("Standard", [])])
        text = "\n".join(
            part.content for part in board.children[0].children
            if isinstance(part, bot.ui.TextDisplay)
        )
        self.assertIn("Be the first to claim this record!", text)
        self.assertNotIn("Records Claimed", text)

    def test_champion_trophy_date_and_gray_label(self):
        board = bot.BossLeaderboard(
            "Vorkath", [("Standard", [record(pb_date="2026-11-08")])]
        )
        components = board.children[0].children
        section = next(x for x in components if isinstance(x, bot.ui.Section))
        self.assertIn("🏆", section.children[0].content)
        self.assertIn("November 8, 2026", section.children[0].content)
        self.assertEqual(section.accessory.label, "NOVUS #1")
        self.assertTrue(section.accessory.disabled)
        self.assertEqual(section.accessory.style, bot.discord.ButtonStyle.secondary)

    def test_board_titles_keep_variant_without_redundant_top_five(self):
        record_one = record()
        boards = [
            bot.BossLeaderboard("Vorkath", [("Standard", [record_one])]),
            bot.BossLeaderboard("Vardorvis", [("Normal", []), ("Awakened", [])]),
            bot.RaidLeaderboard("Theatre of Blood", [("Normal · Trio", [])]),
            bot.RaidBrowser(123, 0, 0, [record_one]),
            bot.Browser(123, "Bosses", 0, [("Standard", [record_one])]),
        ]
        def text_displays(root):
            for item in getattr(root, "children", []):
                if isinstance(item, bot.ui.TextDisplay):
                    yield item.content
                yield from text_displays(item)
        for board in boards:
            with self.subTest(board=type(board).__name__):
                self.assertNotIn("TOP 5", "\n".join(text_displays(board)))
        multi = "\n".join(text_displays(boards[1]))
        self.assertIn("Normal", multi)
        self.assertIn("Awakened", multi)
        self.assertIn("Normal · Trio", "\n".join(text_displays(boards[2])))

    def test_gold_announcement_card_and_date(self):
        pb = record(id=81, pb_date="2026-11-08", ms=872600)
        previous = record(id=82, ms=885000)
        card = bot.FirstPlaceAnnouncementCard(
            pb, previous, "https://discord.com/channels/1/2/3"
        )
        self.assertEqual(len(card.children), 1)
        self.assertEqual(int(card.children[0].accent_colour), bot.GOLD)
        text = card.children[0].children[0].content
        self.assertIn("NEW NOVUS #1", text)
        self.assertIn("November 8, 2026", text)
        self.assertIn("0:12.40", text)
        self.assertIn("14:32.60", text)

    def test_member_profile_uses_team_placements_and_points(self):
        p1 = record(id=101, member_ids="123,456,789", ms=600000)
        p2 = record(id=102, member_ids="123,222,333", ms=620000)
        p3 = record(id=103, member_ids="123", ms=40000,
                    category="Bosses", activity="Vorkath", variant="Standard")
        summary = bot.build_member_profile([p1, p2, p3], 123)
        self.assertEqual(summary["approved_count"], 3)
        self.assertEqual(summary["firsts"], 2)
        self.assertEqual(summary["seconds"], 1)
        self.assertEqual(summary["points"], 13)
        self.assertTrue(bot.PersonalPBProfile(123, summary))
        other = bot.build_member_profile([p1, p2, p3], 999)
        self.assertEqual(other["approved_count"], 0)
        self.assertEqual(other["points"], 0)

    def test_home_has_my_pbs_button(self):
        home = bot.Home()
        actions = next(x for x in home.children[0].children
                       if isinstance(x, bot.ui.ActionRow))
        self.assertIn("My PBs", [x.label for x in actions.children])

    def test_review_card_with_media_does_not_exceed_container_limit(self):
        review = bot.Review(record())
        self.assertLessEqual(len(review.children[0].children), 10)

    def test_review_comparison_and_approved_card(self):
        self.assertTrue(bot.Review(record(), record(ms=1000000)))
        self.assertTrue(bot.Review(record(status="approved")))

    def test_record_formatting_and_timestamp(self):
        self.assertIn("14:32.60", bot.short_record(record(), 0))
        self.assertIn("Proof", bot.short_record(record(), 0))
        self.assertIsNotNone(bot.discord_updated("2026-11-07T22:00:00+00:00"))
        self.assertIsNone(bot.discord_updated(None))




class NewFirstAnnouncementTests(unittest.TestCase):
    def test_only_a_new_fastest_approved_record_qualifies(self):
        leader = record(id=11, ms=885000)
        contender = record(id=12, ms=872600)
        tied = record(id=13, ms=885000)
        slower = record(id=14, ms=900000)
        self.assertTrue(bot.qualifies_for_first_place(contender, leader, [contender, leader]))
        self.assertTrue(bot.qualifies_for_first_place(contender, None, [contender]))
        self.assertFalse(bot.qualifies_for_first_place(tied, leader, [leader, tied]))
        self.assertFalse(bot.qualifies_for_first_place(slower, leader, [leader, slower]))
        self.assertFalse(bot.qualifies_for_first_place(contender, leader, [leader, contender]))
        self.assertFalse(bot.qualifies_for_first_place(contender, leader, []))

    def test_announcement_contains_time_players_proof_and_improvement(self):
        contender = record(id=12, ms=872600)
        leader = record(id=11, ms=885000)
        message = bot.first_place_announcement(
            contender, leader,
            "https://discord.com/channels/123/789/456"
        )
        self.assertIn("NEW NOVUS #1", message)
        self.assertIn("The Fractured Archive", message)
        self.assertIn("Trio", message)
        self.assertIn("14:32.60", message)
        self.assertIn("<@456>", message)
        self.assertIn("<@789>", message)
        self.assertIn("0:12.40", message)
        self.assertIn("Proof", message)
        self.assertIn("View leaderboard", message)

    def test_first_ever_record_message_is_clear(self):
        message = bot.first_place_announcement(record(), None)
        self.assertIn("First approved PB", message)
        self.assertNotIn("previous #1 by", message)

    def test_empty_leaderboard_invites_submissions_without_counter(self):
        board = bot.BossLeaderboard("Vorkath", [("Standard", [])])
        content = "\n".join(
            item.content for item in board.children[0].children
            if isinstance(item, bot.ui.TextDisplay)
        )
        self.assertIn("Be the first to claim this record!", content)
        self.assertNotIn("3/5", content)
        self.assertNotIn("Empty", content)
        raid = bot.RaidLeaderboard("The Fractured Archive", [("Solo", [])])
        self.assertTrue(any(
            "Be the first to claim this record!" in item.content
            for panel in raid.children
            for item in getattr(panel, "children", [])
            if isinstance(item, bot.ui.TextDisplay)
        ))


class PBStartupRefreshTests(unittest.TestCase):
    def test_refresh_pacing_calls_include_the_target_message(self):
        """Regression: missing message argument breaks the whole on_ready refresh."""
        import ast
        from pathlib import Path

        tree = ast.parse(Path(bot.__file__).read_text(encoding="utf-8"))
        ready = next(
            node for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "on_ready"
        )
        calls = [
            node for node in ast.walk(ready)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "paced_startup_edit"
        ]
        self.assertEqual(len(calls), 5)
        for call in calls:
            self.assertTrue(call.args, "Target Discord message must be first argument")
            self.assertIsInstance(call.args[0], ast.Name)
            self.assertEqual(call.args[0].id, "message")

if __name__ == "__main__":
    unittest.main()
