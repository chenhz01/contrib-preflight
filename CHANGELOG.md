# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-10-04

First release. The rule set and the MCP probe both come from defects hit while
contributing to other repositories.

### Added

- `cpreflight scan` with eight rules: `actions-unpinned-ref`,
  `dependabot-major-only-ignore`, `npm-git-version-drift`, `unbound-resource-close`,
  `transposed-identifier`, `compose-bind-source-missing`, `artifact-unverified`,
  `hardcoded-credential`.
- `cpreflight mcp-probe` classifies how a stdio MCP backend starts and fails fast on
  known error signatures instead of waiting out the handshake.
- `.cpreflightignore` suppression file, scoped per rule and optionally per path.
- `--format json`, `--fail-on`, `--no-git`, `--rule`, `--list-rules`.
- CI that runs the tests, builds the distribution, asserts the artifacts exist, and
  runs `cpreflight scan` against this repository on every push.

### Fixed after the first release candidate

- `py.typed` was missing while the metadata still advertised
  `Typing :: Typed`. Without the PEP 561 marker type checkers silently ignore
  the package's annotations, so the classifier was claiming a capability the
  wheel did not ship. The marker now ships in `src/cpreflight/`, lands in the
  built wheel, and a regression test fails if either half is dropped later.
- CI pinned `actions/download-artifact` to `fa0a91b8…` and labelled it `v4`.
  That commit dates from 2024-07-05 and predates v4; v4 resolves to
  `d3f86a10…` (2025-04-24). The pin now matches the tag it claims.

### Fixed during development

- The scanner deduplicated file *reads* in a way that stopped later rules from
  analysing a file another rule had already opened.
- A nonexistent scan path exited 0. It is now a usage error, and a scan that reads
  zero files warns on stderr.
- Credential matches inside test trees and dummy values were reported; those path
  classes are now excluded.
- Transposition matches inside string literals and vendored directories were
  reported; both are now excluded.
