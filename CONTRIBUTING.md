# Contributing

## Repository topology

This project lives on **two platforms**:

| Role | URL | Purpose |
|---|---|---|
| **Primary** | `gitlab.lan:7080/gq/ha-skywatch` (private, self-hosted) | Source-of-truth. CI runs here. Merges land here first. |
| **Public mirror** | [`github.com/gregoryquesnel/ha-skywatch`](https://github.com/gregoryquesnel/ha-skywatch) | Read-mostly. HACS discovery, releases, issues, Dependabot, GitHub Actions (Hassfest + HACS validation). |

A push-mirror on the GitLab side pushes every commit on every branch to
the GitHub mirror automatically (~5 min cycle). GitHub Actions run on the
mirror to validate Hassfest + HACS requirements.

## Where to send contributions

Both surfaces accept pull requests / merge requests. There's a small
operational tradeoff:

### Opening a PR on GitHub (easier path for first-time contributors)

1. Fork `gregoryquesnel/ha-skywatch` on GitHub.
2. Open a PR against `main`.
3. The maintainer will pull your PR, replay the commits onto a branch in
   the GitLab source-of-truth, merge there, and the merge will mirror back
   to GitHub. Your PR will then be closed with a reference to the GitLab MR.
4. Original commit attribution is preserved — your name + email stay on
   the merged commits.

**Tradeoff**: there's a ~5 min window after a GitHub merge where the
GitLab mirror cycle would otherwise overwrite the PR's merge commit.
Maintainer mitigates by replaying through GitLab before re-mirroring.

### Opening an MR on GitLab (faster merge path)

If you have access to the GitLab instance (`gitlab.lan:7080`) — usually
only the maintainer — open the MR directly there. CI runs immediately and
merge ships directly. Push-mirror sends to GitHub within 5 min.

## Development setup

```bash
git clone https://github.com/gregoryquesnel/ha-skywatch.git
cd ha-skywatch
python3 -m venv .venv
source .venv/bin/activate
pip install ruff pytest pytest-asyncio
pytest tests/unit -v
ruff check custom_components tests
ruff format --check custom_components tests
```

## CI surfaces

| Where | Tool | Triggered by |
|---|---|---|
| GitLab CI (`.gitlab-ci.yml`) | Ruff lint + format, Pytest | every MR, every push to `main`, every tag |
| GitHub Actions (`.github/workflows/validate.yml`) | Hassfest, HACS, Ruff, Pytest | every push from the GitLab mirror, every GitHub PR |

Hassfest + HACS run only on GitHub because they're Docker actions and
running them on GitLab would require docker-in-docker. The GitHub mirror
sees every change, so the gates still apply.

## Release process

1. Bump version in `custom_components/skywatch/manifest.json`.
2. Add a `## [vX.Y.Z]` heading in `CHANGELOG.md` with the changes since
   the previous release.
3. Land via MR to GitLab `main`.
4. Tag `vX.Y.Z` and push to GitLab.
5. GitLab CI's `github-release` job pushes the tag to GitHub and creates
   a matching GitHub release. HACS users see the new release in their store.

Manual fallback if the CI release job is misconfigured:

```bash
git push github vX.Y.Z
gh release create vX.Y.Z --repo gregoryquesnel/ha-skywatch \
  --title "vX.Y.Z" --notes "See CHANGELOG.md"
```
