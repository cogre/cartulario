import os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cartulario as c  # noqa: E402


def msg(text, user=7, kind="private", update=1):
    return {"update_id": update, "message": {"text": text, "from": {"id": user}, "chat": {"id": user, "type": kind}}}


def fake_download(ok=True):
    def dl(url, folder, when=None):
        return (True, "Vídeo de ação", os.path.join("2026-10", "vídeo [1].mp4"), "") if ok else (False, "", "", "the site asked for a login")
    return dl


class Text(unittest.TestCase):
    def test_links_and_note(self):
        t = "great pacing https://www.instagram.com/reel/ABC/?igsh=x, watch the cuts"
        self.assertEqual(c.links(t), ["https://www.instagram.com/reel/ABC/?igsh=x"])
        self.assertEqual(c.note_of(t), "great pacing watch the cuts")
        self.assertEqual(c.links("no link here"), [])

    def test_origin(self):
        self.assertEqual(c.origin("https://vm.tiktok.com/x"), "tiktok.com")
        self.assertEqual(c.origin("https://twitter.com/a/status/1"), "x.com")
        self.assertEqual(c.origin("https://youtu.be/abc"), "youtube.com")

    def test_errors_are_said_plainly(self):
        self.assertIn("login", c.short_error("WARNING: x\nERROR: [instagram] abc: Requested content is not available, rate-limit reached or login required"))
        self.assertIn("does not know", c.short_error("ERROR: Unsupported URL: https://example.com"))
        self.assertEqual(c.short_error(""), "yt-dlp gave no reason")

    def test_download_refuses_non_http(self):
        self.assertEqual(c.download("file:///etc/passwd", tempfile.gettempdir())[3], "not an http address")
        self.assertEqual(c.download("--exec=calc", tempfile.gettempdir())[3], "not an http address")


class Bot(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.cfg = {"token": "T", "owner": "7", "folder": self.dir.name}
        self.sent = []

    def tearDown(self):
        self.dir.cleanup()

    def run_updates(self, updates, ok=True):
        def call(token, method, **p):
            if method == "getUpdates":
                return [u for u in updates if u["update_id"] >= p["offset"]]
            self.sent.append((p["chat_id"], p["text"]))
        return c.poll_once(self.cfg, call=call, dl=fake_download(ok), log=lambda *_: None)

    def test_owner_link_is_saved_indexed_and_answered(self):
        self.assertEqual(self.run_updates([msg("https://x.com/a/status/1 ritmo bom")]), 1)
        self.assertTrue(self.sent[-1][1].startswith("Saved: Vídeo de ação"))
        index = open(os.path.join(self.dir.name, "INDEX.txt"), encoding="utf-8").read()
        self.assertIn("| x.com | Vídeo de ação", index)
        self.assertIn("note: ritmo bom", index)

    def test_strangers_and_groups_are_ignored_silently(self):
        n = self.run_updates([msg("https://x.com/a/status/1", user=99), msg("https://x.com/a/status/2", kind="group", update=2)])
        self.assertEqual((n, self.sent), (0, []))
        self.assertFalse(os.path.exists(os.path.join(self.dir.name, "INDEX.txt")))

    def test_no_owner_configured_obeys_nobody(self):
        self.cfg["owner"] = ""
        self.assertEqual(self.run_updates([msg("https://x.com/a/status/1")]), 0)

    def test_failure_is_reported_and_not_indexed(self):
        self.run_updates([msg("https://www.instagram.com/reel/ABC/")], ok=False)
        self.assertIn("Could not download (instagram.com)", self.sent[-1][1])
        self.assertFalse(os.path.exists(os.path.join(self.dir.name, "INDEX.txt")))

    def test_each_message_is_handled_once(self):
        ups = [msg("https://x.com/a/status/1"), msg("https://x.com/a/status/2", update=2)]
        self.assertEqual(self.run_updates(ups), 2)
        self.assertEqual(self.run_updates(ups), 0)

    def test_message_without_link_gets_help(self):
        self.run_updates([msg("oi")])
        self.assertIn("Send me a video link", self.sent[-1][1])


if __name__ == "__main__":
    unittest.main()
