import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bot
from test_pb_ui import record


class RaidSizeTests(unittest.TestCase):
    def test_shared_options_and_populated_leaderboards(self):
        sizes = ["Solo", "Duo", "Trio", "4-Man", "5-Man"]
        options = [option.value for option in bot.submission_format_options()]
        for size in sizes:
            self.assertEqual(options.count(size), 1)
        self.assertFalse(any(option.startswith("Normal · ") for option in options))
        self.assertLessEqual(len(options), 25)
        self.assertEqual(bot.RAIDS["Tombs of Amascut"], ["Expert · Solo", "Expert · 8-Man"])
        for activity in bot.SHARED_SIZE_RAIDS:
            with self.subTest(activity=activity):
                variants = bot.RAIDS[activity]
                excluded = {"Theatre of Blood": "Solo", "Chambers of Xeric": "4-Man"}.get(activity)
                regular = [size for size in sizes if size != excluded]
                self.assertEqual(variants[:len(regular)], regular)
                if excluded:
                    self.assertNotIn(excluded, variants)
                self.assertEqual([bot.team_size("Raids", size, activity) for size in sizes],
                                 [1, 2, 3, 4, 5])
                board = bot.RaidLeaderboard(activity, [
                    (variant, [record(id=i, activity=activity, variant=variant)])
                    for i, variant in enumerate(variants, 1)
                ])
                self.assertLessEqual(board.total_children_count, 40)
                self.assertEqual(len(board.children), len(variants) + 1)
                for panel, variant in zip(board.children[1:], variants):
                    self.assertEqual(panel.children[0].content, f"### {variant}")


class RaidSizeMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_rows_are_relabelled_in_place_without_touching_other_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(bot, "DBPATH", str(Path(directory) / "pb.sqlite3")):
                db = bot.Store()
                await db.open()
                rows = [
                    (1, "Raids", "Theatre of Blood", "Normal · Trio", "approved"),
                    (2, "Raids", "Chambers of Xeric", "Normal · 5-Man", "pending"),
                    (3, "Raids", "Theatre of Blood", "Hard Mode · Trio", "approved"),
                    (4, "Raids", "Chambers of Xeric", "Challenge Mode · 5-Man", "approved"),
                    (5, "Raids", "Theatre of Blood", "Trio", "approved"),
                    (6, "Raids", "Tombs of Amascut", "Expert · Solo", "approved"),
                    (7, "Bosses", "Vardorvis", "Normal", "approved"),
                ]
                await db.conn.executemany(
                    """INSERT INTO submissions
                       (id,category,activity,variant,status,guild,submitter,members,
                        member_ids,ms,proof,review_message,updated)
                       VALUES (?,?,?,?,?,123,456,'Players','456,789,100',872600,
                               'https://example.com/proof.png',987,'unchanged')""",
                    rows,
                )
                await db.conn.commit()
                before = {r["id"]: dict(r) for r in await db.all("SELECT * FROM submissions")}
                await db.conn.close()
                for _ in range(2):
                    await db.open()
                    try:
                        after = {r["id"]: dict(r) for r in await db.all("SELECT * FROM submissions")}
                        self.assertEqual(after, {
                            **before,
                            1: dict(before[1], variant="Trio"),
                            2: dict(before[2], variant="5-Man"),
                        })
                        ranked = await db.ranking(123, "Raids", "Theatre of Blood", "Trio")
                        self.assertEqual([r["id"] for r in ranked], [1])
                        self.assertEqual((await db.best_approved(
                            123, "Raids", "Theatre of Blood", "Hard Mode · Trio"
                        ))["id"], 3)
                    finally:
                        await db.conn.close()
