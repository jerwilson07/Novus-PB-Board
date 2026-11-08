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

    def test_raid_and_boss_navigation_render(self):
        self.assertTrue(bot.RaidBrowser(123, 0, 0, []))
        self.assertTrue(bot.Browser(123, "Bosses", 0, [("Normal", [])]))

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


if __name__ == "__main__":
    unittest.main()
