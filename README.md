# contrib-preflight

**Integrity preflight for repositories and MCP backends.** Zero runtime dependencies.

Before you merge someone else's PR, cut a release, or boot an agent backend, run one
command. It answers three questions that CI usually answers too late:

1. **Is my supply chain pinned?** Mutable action tags, drifted release versions, literal credentials.
2. **Will this actually run?** Bind mounts that don't exist, resources closed without a failure check, artifacts nobody verifies.
3. **Is this backend alive?** Classify a dead stdio MCP server in milliseconds instead of waiting out the handshake.

```
$ cpreflight scan .

ERROR actions-unpinned-ref         .github/workflows/ci.yml:12
      `actions/checkout` is pinned to the mutable ref `@v4`. Anyone who moves
      that tag changes your CI without a commit.
      fix: Pin the 40-char commit SHA and keep the readable version as a comment.

scanned 3112 file(s): 114 error(s), 3 warning(s)
```

---

## Why these eight rules

Every rule here was written after hitting the failure for real, not from a checklist.
Each one has a regression test that reproduces the original defect class.

| Rule | Severity | What it catches |
|---|---|---|
| `actions-unpinned-ref` | error | `uses: owner/action@v4` — a tag anyone can move. Deduplicated per action per file. |
| `dependabot-major-only-ignore` | error/warn | An `ignore:` block that only excludes majors, so minors slip back into a grouped PR. |
| `npm-git-version-drift` | error | `package.json` version disagrees with the newest git tag — you are about to publish a mismatched release. |
| `unbound-resource-close` | warn | A handle opened, then closed/deferred with no visible failure check. |
| `transposed-identifier` | warn | `envict` for `evict`, `seperate` for `separate`. Ignores string literals and vendored code. |
| `compose-bind-source-missing` | error | A bind mount pointing at a path that does not exist, so `compose up` dies creating the container. |
| `artifact-unverified` | warn | An artifact that is uploaded and never checked. |
| `hardcoded-credential` | error | Credential-shaped literals in source. Skips test trees and dummy values. |

### MCP backend liveness

A stdio MCP server that cannot start is expensive: hosts commonly publish their tool
list only after *every* backend handshakes, so one dead backend costs a full timeout
on each boot and its tools silently never appear.

```
$ cpreflight mcp-probe -- npx -y @some/server mcp-server
NOT ready  (105 ms)  subcommand-removed
  hint: The installed CLI no longer exposes this subcommand. Check the server's
        current --help and update the argv, or upgrade/downgrade the CLI.
```

Recognised verdicts: `subcommand-removed`, `requires-tty`, `binary-missing`,
`port-in-use`, `upstream-refused`, `crashed`, `handshake-timeout`, `no-response`,
`initialized`.

---

## Install

```bash
pip install contrib-preflight        # from a release
pip install -e ".[dev]"              # from a checkout, with tests
```

Python 3.9+. No runtime dependencies. Without installing:

```bash
PYTHONPATH=src python -m cpreflight scan .
```

## Usage

```bash
cpreflight scan [PATH]                  # default: current directory
cpreflight scan --list-rules
cpreflight scan --format json           # machine-readable
cpreflight scan --fail-on warn          # stricter gate (default: error)
cpreflight scan --no-git                # skip the one rule that shells out to git
cpreflight scan --rule actions-unpinned-ref   # run a subset

cpreflight mcp-probe --timeout 5 -- <server argv...>
```

Exit codes — `scan`: `0` clean, `1` findings at or above `--fail-on`, `2` bad usage.
`mcp-probe`: `0` backend answered, `1` it did not, `2` bad usage.

A path that does not exist is a **usage error (exit 2)**, never a silent pass, and
scanning a tree that yields zero files warns on stderr — a green result that checked
nothing is worse than a red one.

## Suppressing a finding

Put a `.cpreflightignore` in the repo root:

```
# <rule-id>          -> silence that rule everywhere
# <rule-id>:<glob>   -> silence it for matching paths only
dependabot-major-only-ignore:.github/dependabot.yml
```

This repository uses that mechanism on itself, with the reasoning written out in the
file, rather than weakening a rule to make its own CI green.

## Use it in CI

```yaml
- run: pip install contrib-preflight
- run: cpreflight scan . --fail-on error
```

This repo goes further: a `selfcheck` job runs `cpreflight scan .` on its own source
on every push, so a rule change that starts flagging the project cannot land quietly.

## Validation

Measured on real repositories, not fixtures. Reproduce it with:

```bash
gh repo clone OWNER/REPO /tmp/repo -- --depth 1
cpreflight scan /tmp/repo --format json
```

Three repositories of 2 000–3 100 files each were scanned during development. Two
notable results:

- One repository produced a single hit that was a **true positive**: the rule
  located a misspelled identifier at four exact line numbers that the project's
  own issue report had cited by hand. The generic rule and the human report
  agreed.
- Findings were dominated by mutable action references — real, actionable
  supply-chain debt rather than false positives.

Tuning came from these runs, not from theory. An earlier revision of the
credential rule produced **18 false positives, all inside `__tests__/` fixtures**;
an earlier transposition rule produced **7, all inside `third_party/`**. Both
path classes are now excluded and covered by tests. A repository with no
action workflows and no credential-shaped strings reports clean.

## Limitations

- Heuristics, not a compiler. `unbound-resource-close` and `artifact-unverified`
  deliberately err toward silence; both are warnings.
- `transposed-identifier` matches whole words only, so camelCase compounds
  (`envictEntry`) are not caught.
- No YAML parsing: Dependabot and Compose are read line-wise. Exotic formatting may
  be missed.
- `npm-git-version-drift` needs a git checkout with tags; use `--no-git` to skip it.
- Not a secret scanner. For history-wide credential hunting use gitleaks or trufflehog;
  this rule only looks at the working tree.

## License

MIT — see [LICENSE](LICENSE).
