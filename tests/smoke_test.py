#!/usr/bin/env python3
"""
End-to-end smoke test: runs every script in this repo against the bundled mock
server (examples/mock_server.py). No GPU, no model, no network.

    python3 tests/smoke_test.py            # run everything available
    python3 tests/smoke_test.py -v         # show each command's output

Runtimes that are not installed are reported as SKIP, not FAIL, so the same
file works on Linux, macOS and Windows. Exit code is non-zero if any check
fails.
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import threading

ROOT = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(ROOT, "examples"))

import mock_server  # noqa: E402  (path is set up above)

IS_WINDOWS = os.name == "nt"
TURKISH_MARKER = "çğışöü"
ASCII_MARKER = "mock yanittir"

results = []
VERBOSE = False


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def record(name, status, detail=""):
    results.append((name, status, detail))
    print("%-5s %-42s %s" % (status, name, detail), flush=True)


def run(name, argv, env, expect=(), expect_soft=(), want_code=0, stdin=None):
    """Run a command, assert exit code and expected substrings in stdout."""
    try:
        proc = subprocess.run(argv, env=env, input=stdin, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=120)
    except FileNotFoundError as e:
        record(name, "SKIP", "runtime not installed (%s)" % e.filename)
        return None
    except subprocess.TimeoutExpired:
        record(name, "FAIL", "timed out after 120s")
        return None

    out = proc.stdout or ""
    if VERBOSE:
        print("  $ %s\n  stdout: %s\n  stderr: %s"
              % (" ".join(argv), out.strip()[:400], (proc.stderr or "").strip()[:400]))

    if proc.returncode != want_code:
        record(name, "FAIL", "exit=%d (want %d): %s"
               % (proc.returncode, want_code, (proc.stderr or out).strip()[:200]))
        return proc

    missing = [s for s in expect if s not in out]
    if missing:
        record(name, "FAIL", "missing %r in output: %s" % (missing, out.strip()[:200]))
        return proc

    soft = [s for s in expect_soft if s not in out]
    if soft:
        record(name, "WARN", "console encoding hid %r (not a script bug on Windows)" % soft)
        return proc

    record(name, "PASS", out.strip().splitlines()[0][:70] if out.strip() else "")
    return proc


def main():
    global VERBOSE
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    VERBOSE = args.verbose

    port = free_port()
    srv = mock_server.build_server(port=port)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % port
    print("mock server on %s/v1\n" % base)

    env = dict(os.environ)
    env.update({
        "LLM_ENDPOINT": base,
        "LLM_API_KEY": "sk-mock",
        "LLM_MODEL": mock_server.MODEL_ID,
        "LLM_EMBED_MODEL": mock_server.MODEL_ID,
        "PYTHONIOENCODING": "utf-8",
    })

    bash_script = os.path.join(ROOT, "bash", "llm-prompt.sh")
    ps_script = os.path.join(ROOT, "powershell", "Invoke-LlmPrompt.ps1")
    embed_script = os.path.join(ROOT, "python", "embed-test.py")
    py = sys.executable

    # ---- bash ------------------------------------------------------------
    # Windows resolves "bash" to the WSL stub or Git Bash, neither of which the
    # script targets - Windows users are pointed at the PowerShell script.
    bash = None if IS_WINDOWS else shutil.which("bash")
    if not bash:
        record("bash/llm-prompt.sh", "SKIP",
               "use the PowerShell script on Windows" if IS_WINDOWS else "bash not found")
    else:
        run("bash: chat (blocking)", [bash, bash_script, "-v", "Merhaba"],
            env, expect=[ASCII_MARKER, TURKISH_MARKER])
        run("bash: chat (streaming)", [bash, bash_script, "--stream", "Merhaba"],
            env, expect=[ASCII_MARKER])
        proc = run("bash: --raw returns JSON", [bash, bash_script, "--raw", "Merhaba"],
                   env, expect=["choices"])
        if proc and proc.returncode == 0:
            try:
                json.loads(proc.stdout)
            except ValueError:
                record("bash: --raw parses as JSON", "FAIL", "not valid JSON")
        run("bash: prompt from stdin", [bash, bash_script], env,
            expect=[ASCII_MARKER], stdin="Merhaba\n")
        run("bash: rejects missing model",
            [bash, bash_script, "-m", "", "Merhaba"], env, want_code=1)
        # endpoint normalization: base, /v1 and the full path must all work
        for suffix in ("/v1", "/v1/chat/completions"):
            e2 = dict(env, LLM_ENDPOINT=base + suffix)
            run("bash: endpoint %s" % suffix, [bash, bash_script, "Merhaba"],
                e2, expect=[ASCII_MARKER])

    # ---- powershell ------------------------------------------------------
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if not pwsh:
        record("powershell/Invoke-LlmPrompt.ps1", "SKIP", "pwsh/powershell not found")
    else:
        # Windows consoles routinely mangle non-ASCII on the way to a pipe;
        # that is a console problem, not a script problem, so keep it soft.
        soft = [TURKISH_MARKER] if IS_WINDOWS else []
        hard = [ASCII_MARKER] + ([] if IS_WINDOWS else [TURKISH_MARKER])
        run("powershell: chat (blocking)",
            [pwsh, "-NoProfile", "-NonInteractive", "-File", ps_script, "Merhaba"],
            env, expect=hard, expect_soft=soft)
        run("powershell: chat (streaming)",
            [pwsh, "-NoProfile", "-NonInteractive", "-File", ps_script, "Merhaba", "-Stream"],
            env, expect=[ASCII_MARKER])
        run("powershell: --raw returns JSON",
            [pwsh, "-NoProfile", "-NonInteractive", "-File", ps_script, "Merhaba", "-Raw"],
            env, expect=["choices"])
        e2 = dict(env, LLM_MODEL="")
        run("powershell: rejects missing model",
            [pwsh, "-NoProfile", "-NonInteractive", "-File", ps_script, "Merhaba"],
            e2, want_code=1)

    # ---- python embeddings ----------------------------------------------
    run("python: embed single text", [py, embed_script, "merhaba dünya"],
        env, expect=["dim=", "|v|="])
    run("python: cosine pair", [py, embed_script, "--pair", "GPU node etiketleme",
                                "GPU sunucu label"], env, expect=["cosine="])
    run("python: sanity suite", [py, embed_script, "--suite"], env,
        expect=["passed"])
    run("python: throughput bench",
        [py, embed_script, "--bench", "16", "--concurrency", "4", "--batch-size", "4"],
        env, expect=["throughput=", "p95="])
    e_bad = dict(env, LLM_ENDPOINT="http://127.0.0.1:%d" % free_port())
    run("python: reports a dead endpoint", [py, embed_script, "merhaba"],
        e_bad, want_code=1)

    srv.shutdown()

    failed = [r for r in results if r[1] == "FAIL"]
    passed = [r for r in results if r[1] == "PASS"]
    skipped = [r for r in results if r[1] in ("SKIP", "WARN")]
    print("\n%d passed, %d failed, %d skipped/warned"
          % (len(passed), len(failed), len(skipped)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
