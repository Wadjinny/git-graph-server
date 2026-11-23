"""The web page's script must at least parse (most of the UI logic lives there)."""

import re
import shutil
import subprocess
import tempfile
import unittest
from importlib.resources import files
from pathlib import Path


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class PageScript(unittest.TestCase):
    def test_inline_script_parses(self):
        html = files("git_graph_server").joinpath("static/index.html").read_text(encoding="utf-8")
        scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
        self.assertEqual(len(scripts), 1)
        with tempfile.TemporaryDirectory() as d:
            js = Path(d, "page.js")
            js.write_text(scripts[0], encoding="utf-8")
            r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
