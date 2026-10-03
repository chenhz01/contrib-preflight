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

### Fixed during development

- The scanner deduplicated file *reads* in a way that stopped later rules from
  analysing a file another rule had already opened.
- A nonexistent scan path exited 0. It is now a usage error, and a scan that reads
  zero files warns on stderr.
- Credential matches inside test trees and dummy values were reported; those path
  classes are now excluded.
- Transposition matches inside string literals and vendored directories were
  reported; both are now excluded.
