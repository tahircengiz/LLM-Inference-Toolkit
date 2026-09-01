# Contributing

Thanks for taking a look. This repo is deliberately small and dependency-light —
the constraints below are what keep it usable on a locked-down jump host.

## Ground rules

1. **No runtime dependencies.** Bash scripts use `curl` plus `jq` *or*
   `python3`. Python scripts use the standard library only. PowerShell scripts
   use .NET only — no `curl.exe`, no modules to install.
2. **Cross-platform or explicitly scoped.** Bash must run on Bash 3.2 (macOS)
   without GNU-only flags. PowerShell must work on 5.1 and 7+. Python must run
   on 3.8+.
3. **Diagnostics on stderr, results on stdout.** Piping a script into a file
   should give clean output even with verbose mode on.
4. **Non-zero exit on failure.** These scripts get used as deployment gates.
5. **No secrets, no internal hostnames** in code, examples or docs. Use
   `10.0.0.10`, `example.com`, `sk-xxx`.

## Before opening a PR

```bash
python3 tests/smoke_test.py       # must be green; add checks for new behaviour
bash -n bash/llm-prompt.sh
python3 -m compileall -q python examples tests
```

If you touch the PowerShell script, run the smoke test with `pwsh` installed so
the PowerShell checks actually execute instead of being skipped.

CI runs the same smoke test on Ubuntu, macOS and Windows, plus ShellCheck and
PSScriptAnalyzer at error severity.

## Adding a script

Put it in the directory for its runtime (`bash/`, `powershell/`, `python/`),
give it `--help`, wire it into `tests/smoke_test.py`, and add it to the table in
`README.md`. If it targets a new API surface, add a page under `docs/`.

## Reporting backend behaviour

The most useful issues are "backend X does Y differently". Include the server
and version, the request (`-v` output), and the response (`--raw`). Those go
into [docs/compatibility.md](docs/compatibility.md).
