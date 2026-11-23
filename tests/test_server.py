"""HTTP API: start the real server on a free port against a throwaway repo."""

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from git_graph_server.cli import make_handler
from test_rebase import commit, sh


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        repo = cls.repo = cls.tmp.name
        sh(repo, "init", "-qb", "main")
        commit(repo, "a.txt", "hello\n", "first")
        sh(repo, "checkout", "-qb", "feature")
        cls.tip = commit(repo, "a.txt", "hello world\n", "second")
        sh(repo, "tag", "v1")
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(repo, 100, False, 0))
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_page(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"<title>git-graph-server</title>", body)

    def test_graph(self):
        status, body = self.get("/api/graph")
        d = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(d["head"], "feature")
        self.assertEqual([c["subject"] for c in d["commits"]], ["second", "first"])
        self.assertEqual({(r["type"], r["name"]) for r in d["refs"]}, {("heads", "main"), ("heads", "feature"), ("tags", "v1")})
        self.assertEqual(d["links"], [])

    def test_commit_and_diff(self):
        d = json.loads(self.get(f"/api/commit?sha={self.tip}")[1])
        self.assertEqual(d["files"], [{"path": "a.txt", "add": "1", "del": "1"}])
        diff = json.loads(self.get(f"/api/diff?sha={self.tip}&path=a.txt")[1])["diff"]
        self.assertIn("+hello world", diff)

    def test_rejects_bad_input(self):
        for path in ["/api/commit?sha=--output=x", "/api/commit?sha=zzzz", "/api/diff?sha=;rm", "/api/pr?number=1;x"]:
            self.assertIn(self.get(path)[0], (400, 502), path)
        self.assertEqual(self.get("/nope")[0], 404)

    def test_prs_disabled(self):
        d = json.loads(self.get("/api/prs")[1])
        self.assertEqual(d["prs"], [])
        self.assertIn("disabled", d["error"])


if __name__ == "__main__":
    unittest.main()
