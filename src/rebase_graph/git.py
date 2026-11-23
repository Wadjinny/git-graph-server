"""Read commits, refs and rebase links from a git repo by shelling out to git."""

import json
import re
import subprocess
from collections import defaultdict

SHA_RE = re.compile(r"^[0-9a-f]{4,64}$")
SEP = "\x1f"


def run(repo, *args, input=None):
    return subprocess.run(
        ["git", "-C", repo, *args],
        input=input, capture_output=True, text=True, check=True,
        encoding="utf-8", errors="replace",
    ).stdout


def repo_root(path):
    return run(path, "rev-parse", "--show-toplevel").strip()


def refs(repo):
    out = run(repo, "for-each-ref", f"--format=%(refname){SEP}%(objectname){SEP}%(*objectname)",
              "refs/heads", "refs/remotes", "refs/tags")
    head = run(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    try:  # e.g. origin/main; missing when the remote's HEAD was never set
        default = run(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD").strip()
    except subprocess.CalledProcessError:
        default = ""
    result = []
    for line in out.splitlines():
        name, sha, peeled = line.split(SEP)
        if name.endswith("/HEAD"):
            continue
        kind = name.split("/")[1]  # heads | remotes | tags
        short = name.split("/", 2)[2]
        result.append({"name": short, "type": kind, "sha": peeled or sha,
                       "current": kind == "heads" and short == head})
    return {"head": head, "default": default, "refs": result}


def commits(repo, limit):
    fmt = SEP.join(["%H", "%P", "%an", "%ae", "%at", "%ct", "%s"])
    out = run(repo, "log", "--all", "--date-order", f"-n{limit}", f"--format={fmt}")
    result = []
    for line in out.splitlines():
        sha, parents, an, ae, at, ct, subject = line.split(SEP, 6)
        result.append({"sha": sha, "parents": parents.split(), "author": an, "email": ae,
                       "date": int(at), "cdate": int(ct), "subject": subject})
    return result


def patch_ids(repo, limit):
    """sha -> stable patch-id (same diff => same id, whatever the base)."""
    log = run(repo, "log", "--all", "--date-order", f"-n{limit}", "-p", "--no-color",
              "--no-ext-diff", "--format=commit %H")
    out = run(repo, "patch-id", "--stable", input=log)
    return {sha: pid for pid, sha in (line.split() for line in out.splitlines())}


def rebase_links(commit_list, pids):
    """Find rebased/cherry-picked copies and link each copy to the previous version.

    Two commits are copies if they have the same patch-id, or (to survive rebases that
    hit conflicts) the same author, author date and subject. Returns [{old, new}] where
    old sits lower in the list than new, so the link can be drawn like a merge parent.
    """
    row = {c["sha"]: i for i, c in enumerate(commit_list)}
    by_key = defaultdict(set)
    for c in commit_list:
        if len(c["parents"]) > 1:
            continue  # merges carry no own patch
        if c["sha"] in pids:
            by_key[("p", pids[c["sha"]])].add(c["sha"])
        by_key[("a", c["email"], c["date"], c["subject"])].add(c["sha"])

    # union-find so both kinds of match end up in one group
    parent = {}
    def find(x):
        while parent.get(x, x) != x:
            x = parent[x]
        return x
    for group in by_key.values():
        first, *rest = group
        for other in rest:
            parent[find(other)] = find(first)
    groups = defaultdict(list)
    for sha in parent.keys() | {p for p in parent.values()}:
        groups[find(sha)].append(sha)

    links = []
    for members in groups.values():
        members.sort(key=lambda s: row[s], reverse=True)  # bottom (oldest) first
        for old, new in zip(members, members[1:]):
            links.append({"old": old, "new": new})
    return links


def commit_detail(repo, sha):
    if not SHA_RE.match(sha):
        raise ValueError("bad sha")
    meta = run(repo, "show", "-s", f"--format=%H{SEP}%P{SEP}%an{SEP}%ae{SEP}%at{SEP}%cn{SEP}%ct{SEP}%B", sha)
    full, parents, an, ae, at, cn, ct, body = meta.split(SEP, 7)
    files = []
    for line in run(repo, "show", "--format=", "--numstat", "--no-renames", "--first-parent", sha).splitlines():
        add, delete, path = line.split("\t", 2)
        files.append({"path": path, "add": add, "del": delete})
    return {"sha": full, "parents": parents.split(), "author": an, "email": ae, "date": int(at),
            "committer": cn, "cdate": int(ct), "message": body.strip(), "files": files}


PR_QUERY = """query($owner:String!,$repo:String!,$n:Int!,$after:String){repository(owner:$owner,name:$repo){
pullRequests(states:[MERGED,OPEN],first:$n,after:$after,orderBy:{field:UPDATED_AT,direction:DESC}){
pageInfo{hasNextPage endCursor}
nodes{number title url state isDraft headRefName headRefOid baseRefName mergedAt mergeCommit{oid} commits(first:100){nodes{commit{oid}}}}}}}"""


def merged_prs(repo, limit):
    """Merged and open GitHub PRs via the gh CLI: their commits and, once merged, the commit that landed.

    Uses a small GraphQL query: `gh pr list --json commits` also asks for every commit's
    authors and hits GitHub's node limit on busy repos.
    """
    prs, after = [], None
    while len(prs) < limit:
        args = ["gh", "api", "graphql", "-F", "owner={owner}", "-F", "repo={repo}",
                "-F", f"n={min(50, limit - len(prs))}", "-f", f"query={PR_QUERY}"]
        if after:
            args += ["-f", f"after={after}"]
        out = subprocess.run(args, cwd=repo, capture_output=True, text=True, check=True, timeout=60).stdout
        page = json.loads(out)["data"]["repository"]["pullRequests"]
        prs += [{"number": p["number"], "title": p["title"], "url": p["url"], "state": p["state"], "draft": p["isDraft"],
                 "head": p["headRefName"], "headOid": p["headRefOid"], "base": p["baseRefName"],
                 "merge": (p.get("mergeCommit") or {}).get("oid"), "mergedAt": p["mergedAt"],
                 "commits": [n["commit"]["oid"] for n in p["commits"]["nodes"]]}
                for p in page["nodes"]]
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]
    return prs


def pr_detail(repo, number):
    """A PR's description and discussion: conversation comments, reviews and inline code threads."""
    n = int(number)  # trust boundary: only a number reaches gh
    gh = lambda *a: subprocess.run(["gh", *a], cwd=repo, capture_output=True, text=True, check=True, timeout=60).stdout
    view = json.loads(gh("pr", "view", str(n), "--json", "body,comments,reviews"))
    items = [{"kind": "comment", "author": c["author"]["login"], "date": c["createdAt"], "body": c["body"], "url": c.get("url")}
             for c in view["comments"]]
    # empty COMMENTED reviews only wrap inline comments, which come below with their file and line
    items += [{"kind": "review", "state": r["state"], "author": r["author"]["login"], "date": r["submittedAt"], "body": r["body"]}
              for r in view["reviews"] if r["body"].strip() or r["state"] != "COMMENTED"]
    jq = ".[] | {author: .user.login, date: .created_at, body, path, line: (.line // .original_line), url: .html_url, id, reply: .in_reply_to_id}"
    threads = {}
    for line in gh("api", f"repos/{{owner}}/{{repo}}/pulls/{n}/comments", "--paginate", "--jq", jq).splitlines():
        c = json.loads(line)
        threads.setdefault(c["reply"] or c["id"], []).append(c)
    items += [{"kind": "thread", "path": t[0]["path"], "line": t[0]["line"], "date": t[0]["date"], "url": t[0]["url"],
               "comments": [{"author": c["author"], "date": c["date"], "body": c["body"]} for c in t]}
              for t in threads.values()]
    return {"number": n, "body": view["body"], "items": sorted(items, key=lambda i: i["date"] or "")}


def file_diff(repo, sha, path):
    if not SHA_RE.match(sha):
        raise ValueError("bad sha")
    diff = run(repo, "show", "--format=", "--no-color", "--no-renames", "--first-parent", sha, "--", path)
    return diff[:500_000]  # shortcut: huge diffs are cut, add paging if it matters
