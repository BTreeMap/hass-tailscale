# Contributing

When contributing to this repository, please first discuss the change you wish
to make via issue, email, or any other method with the owners of this repository
before making a change.

Please note we have a code of conduct, please follow it in all your interactions
with the project.

## Issues and feature requests

You've found a bug in the source code, a mistake in the documentation or maybe
you'd like a new feature? You can help us by submitting an issue to our
[GitHub Repository][github]. Before you create an issue, make sure you search
the archive, maybe your question was already answered.

Even better: You could submit a pull request with a fix / new feature!

## Pull request process

1. Search our repository for open or closed [pull requests][prs] that relates
   to your submission. You don't want to duplicate effort.

1. You may merge the pull request in once you have the sign-off of two other
   developers, or if you do not have permission to do that, you may request
   the second reviewer to merge it for you.

## Maintainer release process

Stable releases use `tailscale/config.yaml` as the only version source:

1. Bump its `version` value to the next stable semantic version (`X.Y.Z`) in a
   pull request and merge it into the default branch.

No separate release operation is needed. After CI passes on the resulting `main`
commit, the Release workflow detects that the configured version is newer than
the highest stable tag. It creates `vX.Y.Z`, generates release notes, and marks
the GitHub release as latest, then builds and publishes the versioned and
`stable` container images.

The stable deployment is invoked directly by the Release workflow. This avoids
GitHub's security rule that prevents a release created with `GITHUB_TOKEN` from
triggering another workflow. The workflow also repairs a missing or stale
`stable` image when the corresponding release already exists.

The workflow ignores ordinary commits and versions that are already released.
It rejects invalid or non-increasing version changes and divergent tag history,
and it skips stale CI runs so only the current tip of the default branch can be
released.

## Workflow security policy

- Actions maintained under `actions/`, `docker/`, and `astral-sh/` are trusted
  and use explicit version tags. Actions from other publishers must be pinned to
  a full commit SHA.
- Workflows and jobs receive only the GitHub token permissions they require.
  Release detection is read-only; only release publication receives
  `contents: write`, and only image publishing receives `packages: write`.
- Checkouts must use `persist-credentials: false`. CI checks report formatting
  failures but never modify or push repository content.
- Unused secrets must not be passed to reusable workflows.

[github]: https://github.com/BTreeMap/hass-tailscale/issues
[prs]: https://github.com/BTreeMap/hass-tailscale/pulls
