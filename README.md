# git-graph-server

A local web UI for the branch graph of the git repo you're in, in the style of SourceGit. It has one extra: it can draw a link from each rebased commit to the commit it was copied from, the way a merge is drawn.

Git keeps no record of which commit a rebase copied. git-graph-server finds the copies itself. Two commits count as copies when either:

- their diffs are the same (`git patch-id --stable`), or
- their author, author date and subject are the same. This catches rebases where you fixed a conflict, which changes the diff.

With **Rebase as merge** on, each copy gets a dashed teal line to its previous version. **Hide old copies** hides the pre-rebase commits (the gray rows) and reconnects whatever was built on them.

### Merged PRs (GitHub)

If the [`gh`](https://cli.github.com/) CLI is installed and logged in, git-graph-server also loads the repo's merged and open PRs (up to 300, `--prs N`, or `--no-prs` to skip). Open PRs get a green `#N` on their commits and next to their branch in the sidebar (grey for drafts). It uses the merged ones to:

- show the PR number on commits: solid `#89` on the commit that landed, faded `#89` on the PR's original commits. The Commit panel shows the title, base branch, how it was merged (squash, rebase, merge commit) and links to GitHub;
- **confirm** detected links: a chain of copies that contains both a PR's original commit and the commit it landed as gets a ✓ PR #N;
- **add** links that content matching misses, such as a squash of several commits. These are drawn in purple.

## Run

You need [uv](https://docs.astral.sh/uv/) and git. From inside any git repo:

```bash
uvx --from git+https://github.com/Wadjinny/git-graph-server git-graph-server
```

It serves on http://127.0.0.1:7420 and opens your browser.

```
git-graph-server [path] [--port 7420] [--limit 3000] [--rebase] [--no-open]
```

- `--rebase`: start with the rebase links shown (the checkbox remembers your last choice)
- `--limit`: how many commits to load, newest first, across all branches

## Develop

`uvx --from <local path>` caches the first build, so it won't pick up your edits. Run from the source instead:

```bash
cd ~/some/repo && uv run --project /path/to/git-graph-server git-graph-server
uv run python -m unittest discover tests
```

There are no runtime dependencies, only the Python standard library.
