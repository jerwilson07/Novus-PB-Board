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
        self.assertEqual(len(board.children), 2)
        panel = board.children[1]
        self.assertTrue(any(isinstance(child, bot.ui.Section)
                            for child in panel.children))
        text = "\\n".join(
            child.content for child in panel.children
            if isinstance(child, bot.ui.TextDisplay)
        )
        self.assertIn("TOP 5", text)
        self.assertIn("15:25.00", text)
        self.assertIn("Empty", text)

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
                    for panel in view.children
                    for child in getattr(panel, "children", []))
            )

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
