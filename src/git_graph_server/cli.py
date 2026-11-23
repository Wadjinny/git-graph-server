"""git-graph-server: serve a SourceGit-like branch graph of the git repo in the current directory."""

import argparse
import json
import subprocess
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import git

INDEX = files("git_graph_server").joinpath("static/index.html").read_bytes()


def make_handler(repo, limit, rebase_default, prs_limit):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if url.path == "/":
                    return self.send(200, INDEX, "text/html; charset=utf-8")
                if url.path == "/api/graph":
                    n = min(int(q.get("limit", limit)), 50_000)
                    commit_list = git.commits(repo, n)
                    links = git.rebase_links(commit_list, git.patch_ids(repo, n))
                    return self.send(200, {"repo": Path(repo).name, "rebaseDefault": rebase_default,
                                           "commits": commit_list, "links": links, **git.refs(repo)})
                if url.path == "/api/prs":
                    if not prs_limit:
                        return self.send(200, {"prs": [], "error": "disabled with --no-prs"})
                    try:
                        return self.send(200, {"prs": git.merged_prs(repo, prs_limit)})
                    except (OSError, subprocess.SubprocessError, ValueError) as e:
                        # no gh, not logged in, not a GitHub repo...: the graph works without PRs
                        return self.send(200, {"prs": [], "error": (getattr(e, "stderr", None) or str(e)).strip()})
                if url.path == "/api/pr":
                    try:
                        return self.send(200, git.pr_detail(repo, q.get("number", "")))
                    except (OSError, subprocess.SubprocessError) as e:
                        return self.send(502, {"error": (getattr(e, "stderr", None) or str(e)).strip()})
                if url.path == "/api/commit":
                    return self.send(200, git.commit_detail(repo, q.get("sha", "")))
                if url.path == "/api/diff":
                    return self.send(200, {"diff": git.file_diff(repo, q.get("sha", ""), q.get("path", ""))})
                self.send(404, {"error": "not found"})
            except (ValueError, subprocess.CalledProcessError) as e:
                self.send(400, {"error": getattr(e, "stderr", None) or str(e)})

    return Handler


def main():
    p = argparse.ArgumentParser(prog="git-graph-server", description=__doc__)
    p.add_argument("path", nargs="?", default=".", help="repo path (default: current directory)")
    p.add_argument("--port", type=int, default=7420)
    p.add_argument("--limit", type=int, default=3000, help="max commits to load")
    p.add_argument("--rebase", action="store_true", help="start with rebase links shown as merges")
    p.add_argument("--no-open", action="store_true", help="don't open the browser")
    p.add_argument("--prs", type=int, default=300, help="merged and open GitHub PRs to load with gh (default 300)")
    p.add_argument("--no-prs", action="store_true", help="don't call gh for PR info")
    args = p.parse_args()

    try:
        repo = git.repo_root(args.path)
    except (subprocess.CalledProcessError, FileNotFoundError):
        sys.exit(f"git-graph-server: {Path(args.path).resolve()} is not a git repository")

    # localhost only: the API exposes the repo's contents
    handler = make_handler(repo, args.limit, args.rebase, 0 if args.no_prs else args.prs)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    except OSError:  # port taken (e.g. another repo open): let the OS pick one
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"git-graph-server: {repo} -> {url}  (Ctrl+C to stop)", flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
