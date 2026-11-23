"""PR reading: feed canned gh output through the parsers."""

import json
import subprocess
import unittest
from unittest import mock

from git_graph_server import git


def fake_gh(responses):
    """subprocess.run stand-in: picks the canned stdout whose key appears in the command line."""
    calls = []

    def run(args, **kw):
        calls.append(args)
        line = " ".join(args)
        for key, out in responses:
            if key in line:
                return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")
        raise AssertionError("unexpected command: " + line)
    return run, calls


def page(nodes, more=False, cursor=None):
    return json.dumps({"data": {"repository": {"pullRequests": {
        "pageInfo": {"hasNextPage": more, "endCursor": cursor}, "nodes": nodes}}}})


def node(n, state="MERGED", merge="m" * 40):
    return {"number": n, "title": f"PR {n}", "url": f"https://x/pull/{n}", "state": state, "isDraft": False,
            "headRefName": f"feat/{n}", "headRefOid": "h" * 40, "baseRefName": "main",
            "mergeCommit": {"oid": merge} if merge else None, "mergedAt": "2026-01-01T00:00:00Z",
            "commits": {"nodes": [{"commit": {"oid": "c" * 40}}]}}


class MergedPrs(unittest.TestCase):
    def test_pages_until_done_and_maps_fields(self):
        run, calls = fake_gh([("after=CUR", page([node(2, "OPEN", merge=None)])), ("graphql", page([node(1)], True, "CUR"))])
        with mock.patch.object(git.subprocess, "run", run):
            prs = git.merged_prs(".", 300)
        self.assertEqual(len(calls), 2)
        self.assertEqual([(p["number"], p["state"], p["merge"]) for p in prs], [(1, "MERGED", "m" * 40), (2, "OPEN", None)])
        self.assertEqual(prs[0]["commits"], ["c" * 40])
        self.assertEqual(prs[0]["head"], "feat/1")

    def test_respects_limit(self):
        run, calls = fake_gh([("graphql", page([node(1), node(2)], True, "CUR"))])
        with mock.patch.object(git.subprocess, "run", run):
            self.assertEqual(len(git.merged_prs(".", 2)), 2)
        self.assertIn("n=2", " ".join(calls[0]))


class PrDetail(unittest.TestCase):
    def test_groups_threads_and_drops_empty_reviews(self):
        view = json.dumps({"body": "## Why\nbecause", "comments": [
            {"author": {"login": "ann"}, "createdAt": "2026-01-01T10:00:00Z", "body": "hi", "url": "u1"}],
            "reviews": [
                {"author": {"login": "bob"}, "submittedAt": "2026-01-01T09:00:00Z", "body": "", "state": "COMMENTED"},
                {"author": {"login": "bob"}, "submittedAt": "2026-01-01T12:00:00Z", "body": "", "state": "APPROVED"}]})
        inline = "\n".join(json.dumps(c) for c in [
            {"author": "bob", "date": "2026-01-01T09:00:00Z", "body": "why?", "path": "a.py", "line": 3, "url": "u2", "id": 7, "reply": None},
            {"author": "ann", "date": "2026-01-01T09:30:00Z", "body": "fixed", "path": "a.py", "line": 3, "url": "u3", "id": 8, "reply": 7}])
        run, _ = fake_gh([("pr view 12", view), ("pulls/12/comments", inline)])
        with mock.patch.object(git.subprocess, "run", run):
            d = git.pr_detail(".", "12")
        self.assertEqual(d["body"], "## Why\nbecause")
        self.assertEqual([i["kind"] for i in d["items"]], ["thread", "comment", "review"])  # by date
        self.assertEqual([c["body"] for c in d["items"][0]["comments"]], ["why?", "fixed"])
        self.assertEqual(d["items"][2]["state"], "APPROVED")

    def test_only_numbers_reach_gh(self):
        with self.assertRaises(ValueError):
            git.pr_detail(".", "12; rm -rf /")


if __name__ == "__main__":
    unittest.main()
