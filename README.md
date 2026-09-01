# LLM Inference Toolkit

Dependency-light scripts that probe, verify and benchmark **any OpenAI-compatible
inference endpoint** — from Linux, macOS or Windows.

[![CI](https://github.com/tahircengiz/LLM-Inference-Toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/tahircengiz/LLM-Inference-Toolkit/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Bash 3.2+](https://img.shields.io/badge/bash-3.2%2B-green)
![PowerShell 5.1+](https://img.shields.io/badge/powershell-5.1%2B-blue)
![Python 3.8+ stdlib](https://img.shields.io/badge/python-3.8%2B%20stdlib-yellow)

---

## Why this exists

You put a model behind vLLM, TGI, llama.cpp or a gateway, and then you need to
answer the same handful of questions — usually from a jump host where you are
not allowed to `pip install` anything:

- Is the endpoint reachable, and is the bearer token actually enforced?
- Is the model name right, or is the server silently serving something else?
- Does it come back as clean UTF-8, or does it mangle Turkish characters?
- How many tokens/s does it really do, and where does latency come from?
- Are the embeddings L2-normalized? Deterministic? Does batching change them?

Every script here answers one of those with **no SDK, no virtualenv, no
package install** — `curl` + `jq`, .NET, or the Python standard library.

## What's inside

| Script | Runtime | API | What it does |
| --- | --- | --- | --- |
| [`bash/llm-prompt.sh`](bash/llm-prompt.sh) | Bash 3.2+, `curl`, `jq` *or* `python3` | `/v1/chat/completions` | Single prompt, optional SSE streaming, token usage / latency / tok-s |
| [`powershell/Invoke-LlmPrompt.ps1`](powershell/Invoke-LlmPrompt.ps1) | PowerShell 5.1 or 7+ | `/v1/chat/completions` | Same, with no `curl.exe` dependency; handles TLS 1.2 and UTF-8 on Windows PowerShell |
| [`python/embed-test.py`](python/embed-test.py) | Python 3.8+ (stdlib only) | `/v1/embeddings` | Embed text, cosine pairs, a 7-check sanity suite, and a concurrency benchmark |
| [`examples/mock_server.py`](examples/mock_server.py) | Python 3.8+ (stdlib only) | both | A fake OpenAI-compatible server so you can try everything with no GPU — including reproducible HTTP errors via `-m error-404` |
| [`tests/smoke_test.py`](tests/smoke_test.py) | Python 3.8+ (stdlib only) | — | Runs every script above against the mock; skips runtimes you don't have |

## Start here — pick your OS

Each runbook lists every test as **a command plus the exact output it should
produce**, verified on a real run rather than written from memory.

| You are on | Runbook | Chat script |
| --- | --- | --- |
| Linux · macOS · WSL | **[docs/runbook-linux.md](docs/runbook-linux.md)** | `bash/llm-prompt.sh` |
| Windows | **[docs/runbook-windows.md](docs/runbook-windows.md)** | `powershell\Invoke-LlmPrompt.ps1` |

Reference material:
[flag reference](docs/chat-completions.md) ·
[embeddings guide](docs/embeddings.md) ·
[backend compatibility](docs/compatibility.md) ·
[troubleshooting](docs/troubleshooting.md)

## Verified on

Every push runs the full suite on three operating systems. These are results,
not intentions:

| Environment | Chat (Bash) | Chat (PowerShell) | Embeddings | Result |
| --- | --- | --- | --- | --- |
| `ubuntu-latest` — Bash 5.x, pwsh 7.6.5, Python 3.14 | ✅ | ✅ | ✅ | 19/19 |
| `macos-latest` — Bash 3.2.57, pwsh 7.6.4, Python 3.14 | ✅ | ✅ | ✅ | 19/19 |
| `windows-latest` — pwsh 7.6.5, Python 3.14 | skipped by design | ✅ | ✅ | 11/11 |
| macOS 26.5 local — Bash 3.2.57, pwsh 7.6.3, Python 3.9 | ✅ | ✅ | ✅ | 19/19 |

The embeddings sanity suite returns **identical cosine values on all three
platforms**, which is what makes the expected values in the runbooks worth
writing down.

## Requirements

| Platform | Chat | Embeddings |
| --- | --- | --- |
| Linux / WSL | `bash`, `curl`, and `jq` (or `python3`) | `python3` |
| macOS | same — no GNU coreutils needed | `python3` |
| Windows | PowerShell 5.1 (built in) or 7+ | `python` / `py -3` |

`jq` is preferred but optional: the Bash script falls back to `python3` for
JSON handling, so it still works on a stripped-down container.

## Quick start

### 1. Without a server

Start the bundled mock, then run anything against it:

```bash
python3 examples/mock_server.py --port 8899
```

```bash
export LLM_ENDPOINT=http://127.0.0.1:8899
export LLM_API_KEY=sk-mock
export LLM_MODEL=mock-model

bash/llm-prompt.sh "Merhaba, kendini tanıt"
bash/llm-prompt.sh --stream "Bir haiku yaz"
python3 python/embed-test.py --suite
```

```powershell
$env:LLM_ENDPOINT = 'http://127.0.0.1:8899'
$env:LLM_API_KEY  = 'sk-mock'
$env:LLM_MODEL    = 'mock-model'

.\powershell\Invoke-LlmPrompt.ps1 "Merhaba, kendini tanıt"
.\powershell\Invoke-LlmPrompt.ps1 "Bir haiku yaz" -Stream
```

### 2. Against a real endpoint

```bash
chmod +x bash/llm-prompt.sh python/embed-test.py

bash/llm-prompt.sh \
  -e http://10.0.0.10:8000 \
  -k "$MY_KEY" \
  -m Qwen/Qwen2.5-7B-Instruct \
  -v "Merhaba, kendini tanıt"
```

```
Merhaba! Ben bir yapay zeka asistanıyım...
prompt=14 completion=128 total=142 | 2.31s | 55.4 tok/s | finish=stop
```

```powershell
.\powershell\Invoke-LlmPrompt.ps1 "Merhaba, kendini tanıt" `
    -Endpoint http://10.0.0.10:8000 `
    -ApiKey $env:MY_KEY `
    -Model Qwen/Qwen2.5-7B-Instruct `
    -Verbose
```

```bash
# Is this embedding model actually usable for RAG?
python3 python/embed-test.py -e http://10.0.0.10:8001 -k "$MY_KEY" -m BAAI/bge-m3 --suite
```

```
PASS  dim consistent across batch            dim=1024
PASS  vectors L2-normalized                  norms=1.000000, 1.000000, 1.000000
PASS  deterministic across calls             max|delta|=0.000e+00 cos=1.00000000
PASS  cos(paraphrase) > cos(unrelated)       para=0.7412 unrelated=0.2688 margin=0.4724
PASS  cos(identical) ~= 1.0                  cos=1.00000000
PASS  batch position does not change vector  cos(pos0)=1.00000000 cos(pos3)=1.00000000
PASS  long input (~264000 chars) handled     truncated silently, prompt_tokens=8192
```

## Configuration

Every script reads the same environment variables, so you set them once per
shell and drop the flags:

| Variable | Used by | Flag equivalent |
| --- | --- | --- |
| `LLM_ENDPOINT` | all | `-e` / `-Endpoint` |
| `LLM_API_KEY` | all | `-k` / `-ApiKey` |
| `LLM_MODEL` | all | `-m` / `-Model` |
| `LLM_EMBED_MODEL` | `embed-test.py` | `-m` (takes precedence over `LLM_MODEL`) |

An explicit flag always wins over the environment variable. See
[`examples/env.example`](examples/env.example) for a file you can `source`.

**Endpoint URLs are normalized**, so all three of these are equivalent:

```
http://10.0.0.10:8000
http://10.0.0.10:8000/v1
http://10.0.0.10:8000/v1/chat/completions
```

The scripts append `/v1/chat/completions` (or `/v1/embeddings`) only when it is
missing, which means a gateway that serves the API under a path prefix
(`https://gw.example.com/team-a/v1`) works unchanged.

## Feature matrix

| | `llm-prompt.sh` | `Invoke-LlmPrompt.ps1` |
| --- | --- | --- |
| Blocking completion | ✅ | ✅ |
| SSE streaming | ✅ `--stream` | ✅ `-Stream` |
| System prompt | ✅ `-s` | ✅ `-SystemPrompt` |
| Temperature / max tokens | ✅ | ✅ |
| Raw JSON passthrough | ✅ `--raw` | ✅ `-Raw` |
| Usage + tok/s | ✅ `-v` | ✅ `-Verbose` |
| Skip TLS verification | ✅ `-i` | ✅ `-Insecure` |
| Prompt from stdin / pipe | ✅ | — (pass as argument) |

## Security

- **Prefer `LLM_API_KEY` over `-k`.** On a shared Linux host, a key passed as a
  command-line flag is visible to anyone running `ps aux`, and it lands in your
  shell history.
- `-i` / `-Insecure` disables certificate verification entirely. It exists for
  self-signed internal endpoints; never point it at anything over the internet.
- Nothing here writes to disk, phones home, or logs your prompts. `--raw`
  prints the full response body — mind what you paste into tickets.
- No key, hostname or internal URL belongs in a commit. `.gitignore` already
  covers `.env` and `*.local.*`.

## Testing

```bash
python3 tests/smoke_test.py          # every script, against the bundled mock
python3 tests/smoke_test.py -v       # plus each command's output
```

```
PASS  bash: chat (blocking)                      Merhaba! Bu bir mock yanittir - Türkçe karakter testi: çğışöüÇĞİŞÖÜ
PASS  bash: chat (streaming)                     ...
PASS  powershell: chat (blocking)                ...
PASS  python: sanity suite                       PASS  dim consistent across batch            dim=128
...
19 passed, 0 failed, 0 skipped/warned
```

Runtimes you do not have are reported as `SKIP`, not `FAIL`, so the same file
works everywhere. CI runs it on Ubuntu, macOS and Windows on every push —
the cross-platform claims above are checked, not asserted.

## Roadmap

- [ ] `/v1/models` discovery helper (list what a gateway actually serves)
- [ ] Reranker endpoint (`/v1/rerank`) sanity checks
- [ ] Concurrency / TTFT load-test mode for chat, not just embeddings
- [ ] Function-calling and structured-output conformance checks
- [ ] Native PowerShell embeddings script for Windows hosts without Python

## Contributing

Issues and PRs welcome — especially reports of a backend that behaves
differently from the ones listed in [docs/compatibility.md](docs/compatibility.md).
See [CONTRIBUTING.md](CONTRIBUTING.md) for the (short) rules.

## License

[MIT](LICENSE)
