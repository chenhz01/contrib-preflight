# Contributing

Thanks for looking. Two expectations hold this project together.

## 1. Every rule needs a real regression

A rule lands with a test that reproduces the defect class it was built for — a
before case that fires and an after case that stays quiet. If you cannot write the
"quiet" case, the rule is too noisy to ship.

## 2. The tool must pass on itself

```bash
python -m pytest          # all green
cpreflight scan .         # zero errors, zero warnings
```

Both run in CI on every push. If a new rule flags this repository, you have three
honest options, in order of preference:

1. **Fix the code** the rule found.
2. **Narrow the rule** so it stops matching legitimate code.
3. **Suppress it in `.cpreflightignore` with a written reason.**

Never weaken a rule globally just to make CI green, and never leave a suppression
without a comment explaining why the finding is acceptable.

## Validation

Before claiming a rule is useful, run it against real repositories and record the
numbers. Tuning decisions in this project came from exactly that:

```bash
gh repo clone OWNER/REPO /tmp/repo -- --depth 1
cpreflight scan /tmp/repo --no-git --format json
```

That exercise is what turned "18 credential false positives in `__tests__/`" and
"7 transposition hits in `third_party/`" into excluded path classes with tests.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
cpreflight scan . --format json
```

Project layout:

```
src/cpreflight/
  model.py       Finding / Severity / Result
  util.py        file walking, SHA and line helpers
  rules.py       the rule set — pure functions, no I/O beyond the file given
  scanner.py     tree walk, ignore-file handling
  mcp_probe.py   stdio backend liveness probe
  cli.py         argument parsing and exit codes
```

Adding a rule: write the function, register it in `RULES`, add tests. Rules receive
`(path, text, root)` and return findings; keep them free of network calls.

## Reporting a false positive

Open an issue with the repo, the path, the finding, and what the code actually does.
False positives are bugs here, and the fix is as welcome as a new rule.
