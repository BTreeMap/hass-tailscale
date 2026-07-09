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
1. Wait for the CI workflow on that merge commit to pass.
1. Open the **Release** workflow in GitHub Actions, choose **Run workflow** from
   the default branch, and enter that same version without a `v` prefix.

The workflow rejects releases from another branch, stale commits, mismatched or
invalid versions, versions that are not newer than the highest existing stable
tag, duplicate tags or releases, divergent tag history, and commits without a
successful CI run. It then creates `vX.Y.Z`, generates release notes, and marks
the GitHub release as latest. Publishing the release starts the existing Deploy
workflow, which builds and publishes the versioned and `stable` container images.

[github]: https://github.com/BTreeMap/hass-tailscale/issues
[prs]: https://github.com/BTreeMap/hass-tailscale/pulls
