---
description: "Bumps the semver git tag from conventional commits and releases"
allowed-tools:
  - "Bash(git tag:*)"
  - "Bash(git describe:*)"
  - "Bash(git log:*)"
  - "Bash(git status:*)"
  - "Bash(git rev-parse:*)"
  - "Bash(git branch:*)"
  - "Bash(git fetch:*)"
  - "Bash(git push:*)"
  - "Bash(git config:*)"
---
# /release Command

Determines the next [semantic version](https://semver.org) from the Conventional Commits since the last release tag, creates an annotated tag, and pushes it.

## Usage

```
/release [major|minor|patch|<explicit-version>]
```

- With no argument, the bump is inferred from the commits since the last tag (see Steps).
- With `major`, `minor`, or `patch`, force that bump level.
- With an explicit version (e.g. `1.4.0` or `v1.4.0`), use it verbatim.

## Context
- Current branch: !`git branch --show-current`
- Status (must be clean): !`git status --porcelain`
- All tags (newest first): !`git tag --sort=-v:refname`

## Steps
1. **Gather state.** Run these as normal Bash calls (they use shell syntax that cannot be pre-evaluated in Context):
   - Latest tag: `git describe --tags --abbrev=0` (no tags yet if it errors).
   - Commits since the latest tag: `git log --no-merges --pretty=format:'%s' <latest-tag>..HEAD`. If there is no tag, use `git log --no-merges --pretty=format:'%s'` for the whole history.
   - Upstream tracking ref: `git rev-parse --abbrev-ref --symbolic-full-name @{u}` (no upstream if it errors).
2. **Preflight.** Abort and report if any of these hold:
   - The working tree is not clean (`git status --porcelain` is non-empty) — ask the user to commit or stash first.
   - `HEAD` is not on a branch, or the branch is behind/ahead of its upstream in a way that means unpushed/unpulled commits. Run `git fetch` first; if local and upstream have diverged, stop and explain.
   - There are no new commits since the latest tag — nothing to release.
3. **Determine the current version.**
   - Parse the latest tag matching `v?MAJOR.MINOR.PATCH`. Preserve whether the existing tags use a `v` prefix; if there are no tags, start from `0.0.0` with a `v` prefix and treat the first release as `v0.1.0`.
4. **Determine the bump** (skip if an explicit version or level was passed as an argument):
   - Inspect every commit subject (and body for footers) since the last tag.
   - `major`: any commit with a `!` after the type/scope (e.g. `feat!:`) or a `BREAKING CHANGE:` / `BREAKING-CHANGE:` footer. (While the current major version is `0`, a breaking change bumps `minor` instead, per semver's initial-development clause — confirm with the user.)
   - `minor`: any `feat` commit and no breaking change.
   - `patch`: only `fix`, `perf`, or other non-feature changes (`refactor`, `docs`, `chore`, etc.) with no `feat` and no breaking change.
   - If there are only `chore`/`docs`/`style`/`test`/`ci` commits and no `fix`/`feat`, tell the user the change set looks non-releasable and ask whether to proceed with a `patch` bump anyway.
5. **Compute the next version** by applying the bump to the current version (reset lower components: a `minor` bump zeroes `patch`; a `major` bump zeroes `minor` and `patch`). Reapply the prefix convention from step 3.
6. **Draft release notes.** Group the commits since the last tag by type (Features, Fixes, Performance, Other) into a short changelog.
7. **Confirm.** Show the user:
   - Current version → next version, and the reason for the chosen bump.
   - The branch the tag will point at and the remote it will be pushed to.
   - The drafted release notes that will become the annotated tag message.
   Then ask the user to confirm before proceeding.
8. **Tag.** On confirmation, create an annotated tag at `HEAD`:
   `git tag -a <version> -m "<release notes>"`
9. **Push.** Push the branch and the tag:
   - `git push` (the branch, if it has unpushed commits)
   - `git push origin <version>` (the tag)
10. **Report** the created tag, the commit it points at, and the remote it was pushed to. If the remote is GitHub and the user wants a GitHub Release, mention they can run `gh release create <version>` (only run it if they ask).

## Constraints
- Never create or move a tag that already exists — if the computed version tag exists, stop and report.
- Never use `git push --force` or `git tag -f`.
- Use annotated tags (`-a`), not lightweight tags.
- Tag only a clean working tree at a commit that exists on the remote-tracked branch.
- No Claude co-authorship footer in the tag message.
