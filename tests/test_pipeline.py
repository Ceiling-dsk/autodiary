import json
import tempfile
import unittest
from pathlib import Path

from chatdiary.db import connect, upsert_conversation
from chatdiary.lifeday import life_day, window
from chatdiary.parse import load_conversations, parse_conversation
from chatdiary.render import collect_day

FIXTURE = Path(__file__).parent / "fixtures" / "conversation_branching.json"


def load():
    return parse_conversation(load_conversations(json.loads(FIXTURE.read_text()))[0])


class LifeDayTest(unittest.TestCase):
    def test_boundary_at_4am(self):
        msgs = {m.id: m for m in load().messages}
        self.assertEqual(life_day(msgs["u1"].create_time), "2026-10-08")
        self.assertEqual(life_day(msgs["u2"].create_time), "2026-10-08")  # 03:59
        self.assertEqual(life_day(msgs["a2b"].create_time), "2026-10-09")  # 04:01

    def test_dst_day_is_25_hours(self):
        start, end = window("2026-10-31")  # 2026-11-01 凌晨夏令时结束
        self.assertEqual(end.timestamp() - start.timestamp(), 25 * 3600)


class ParseTest(unittest.TestCase):
    def test_main_branch_and_hidden(self):
        msgs = {m.id: m for m in load().messages}
        self.assertTrue(msgs["a2b"].on_main_branch)
        self.assertFalse(msgs["a2a"].on_main_branch)
        self.assertTrue(msgs["sys"].hidden)

    def test_multimodal_placeholder(self):
        msgs = {m.id: m for m in load().messages}
        self.assertIn("[image_asset_pointer]", msgs["u2"].text)


class DbTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_import_is_idempotent(self):
        upsert_conversation(self.conn, load())
        upsert_conversation(self.conn, load())
        n = self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        self.assertEqual(n, 6)

    def test_conversation_split_across_days(self):
        upsert_conversation(self.conn, load())
        d1 = collect_day(self.conn, "2026-10-08")
        d2 = collect_day(self.conn, "2026-10-09")
        self.assertEqual([m["id"] for m in d1["conversations"][0]["messages"]], ["u1", "a1", "u2"])
        self.assertEqual({m["id"] for m in d2["conversations"][0]["messages"]}, {"a2a", "a2b"})

    def test_search(self):
        upsert_conversation(self.conn, load())
        rows = self.conn.execute("SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?", ("吃了拉面",)).fetchall()
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
