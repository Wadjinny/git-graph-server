# Changelog

## 0.1.0 (2026-11-23)

First release.

- SourceGit-style branch graph of the git repo in the current directory, served locally.
- **Rebase as merge**: links each rebased or cherry-picked commit to its previous version, found by patch-id or by author, author date and subject.
- GitHub PRs through `gh` (optional): PR numbers on commits, links confirmed or added from merged PR data, open and draft PRs, PR description and comments rendered as Markdown.
- Filters: authors, branches (lineage focus), dates (relative or exact), hide old copies, hide merged branches, hide local-only branches.
- Resizable, collapsible panels; commit details and per-file diffs.
