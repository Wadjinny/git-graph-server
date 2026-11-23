"""Run with: uv run python -m unittest discover tests"""

import subprocess
import tempfile
import unittest
from pathlib import Path

from git_graph_server import git


def sh(repo, *args):
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "HOME": repo, "PATH": "/usr/bin:/bin"}
    return subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True, text=True).stdout.strip()


def commit(repo, name, text, msg):
    Path(repo, name).write_text(text)
    sh(repo, "add", name)
    sh(repo, "commit", "-qm", msg)
    return sh(repo, "rev-parse", "HEAD")


class RebaseLinks(unittest.TestCase):
    def test_rebase_and_amended_rebase_are_linked(self):
        with tempfile.TemporaryDirectory() as repo:
            sh(repo, "init", "-qb", "main")
            commit(repo, "a", "a", "A")
            sh(repo, "checkout", "-qb", "feature")
            b = commit(repo, "b", "b", "B")
            c = commit(repo, "c", "c", "C")
            sh(repo, "branch", "old-feature")
            sh(repo, "checkout", "-q", "main")
            commit(repo, "d", "d", "D")
            sh(repo, "checkout", "-q", "feature")
            sh(repo, "rebase", "-q", "main")
            b2 = sh(repo, "rev-parse", "HEAD~1")
            # change C's content while keeping author/date/subject, like a conflict fix during rebase
            Path(repo, "c").write_text("c fixed")
            sh(repo, "commit", "-qa", "--amend", "--no-edit")
            c2 = sh(repo, "rev-parse", "HEAD")

            commits = git.commits(repo, 100)
            links = git.rebase_links(commits, git.patch_ids(repo, 100))
            pairs = {(l["old"], l["new"]) for l in links}
            self.assertEqual(pairs, {(b, b2), (c, c2)})

            rows = {x["sha"]: i for i, x in enumerate(commits)}
            for l in links:
                self.assertGreater(rows[l["old"]], rows[l["new"]])

            detail = git.commit_detail(repo, c2)
            self.assertEqual(detail["files"][0]["path"], "c")
            self.assertIn("+c fixed", git.file_diff(repo, c2, "c"))
            with self.assertRaises(ValueError):
                git.commit_detail(repo, "--output=/tmp/x")


if __name__ == "__main__":
    unittest.main()
