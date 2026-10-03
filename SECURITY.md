# Security Policy

## Scope

`contrib-preflight` is a static checker and a process probe. It reads files in the
directory you point it at and, for `mcp-probe`, spawns the exact command you pass.

- It never writes to the scanned tree.
- It sends no telemetry and makes no network requests of its own. The single rule
  that shells out (`npm-git-version-drift`) runs `git tag` locally.
- `mcp-probe` executes the argv you give it. Treat that argv as you would any other
  command you run.

`hardcoded-credential` reports credential-shaped literals in your working tree. It
does not read git history — use gitleaks or trufflehog for that — and its output
should be treated as sensitive if you run it on a real repository.

## Reporting a vulnerability

Open a private security advisory on this repository. Please include a reproduction
and the version. We aim to acknowledge within a few days.

Because this tool's output can contain fragments of real secrets, please do not paste
raw findings into public issues; redact the value and describe the shape.
