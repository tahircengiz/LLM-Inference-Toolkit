# Test runbook — Linux / macOS / WSL

Every test below has been **run and verified**: the command is exactly what you
type, and the expected output is copied verbatim from a real run against the
bundled mock server. Anything that legitimately varies between runs (latency,
tok/s) is called out per test.

Windows users: see [runbook-windows.md](runbook-windows.md) instead.

## Verified environments

| Environment | Shell | Python | curl / jq | Result |
| --- | --- | --- | --- | --- |
| macOS 26.5.2 (local) | Bash 3.2.57 | 3.9.6 | curl 8.7.1 / jq 1.7.1 | ✅ 19/19 |
| `ubuntu-latest` (CI) | Bash 5.x | 3.14.7 | curl 8.5.0 / jq 1.7 | ✅ 19/19 |
| `macos-latest` (CI) | Bash 3.2.57 | 3.14.6 | curl 8.7.1 / jq 1.8.2 | ✅ 19/19 |

Bash 3.2 is deliberate: it is what macOS ships, so anything that works there
works on every modern Linux too.

## Setup

```bash
git clone https://github.com/tahircengiz/LLM-Inference-Toolkit.git
cd LLM-Inference-Toolkit
chmod +x bash/llm-prompt.sh python/embed-test.py

# Terminal 1 - the mock server that produces the expected values below
python3 examples/mock_server.py --port 8899

# Terminal 2
export LLM_ENDPOINT=http://127.0.0.1:8899
export LLM_API_KEY=sk-mock
export LLM_MODEL=mock-model
export LLM_EMBED_MODEL=mock-model
```

To run every test at once instead of one by one:

```bash
python3 tests/smoke_test.py          # expect: 19 passed, 0 failed
```

---

## Chat completions

### L01 — Blocking request with diagnostics

```bash
bash/llm-prompt.sh -v "Merhaba, kendini tanıt"
```

```
POST http://127.0.0.1:8899/v1/chat/completions
{"model":"mock-model","messages":[{"role":"user","content":"Merhaba, kendini tanıt"}],"temperature":0.0,"max_tokens":512,"stream":false}
Merhaba! Bu bir mock yanittir - Türkçe karakter testi: çğışöüÇĞİŞÖÜ
prompt=5 completion=16 total=21 | 0.01s | 1333.3 tok/s | finish=stop
```

**Pass:** exit `0` · the answer on stdout · `finish=stop` · Turkish characters
intact (`çğışöüÇĞİŞÖÜ`, not `Ã§ÄŸ`) · the request line and usage line on stderr.
**Varies:** the `0.01s` and `1333.3 tok/s` figures.

### L02 — Streaming (SSE)

```bash
bash/llm-prompt.sh --stream "Merhaba"
```

```
Merhaba! Bu bir mock yanittir - Türkçe karakter testi: çğışöüÇĞİŞÖÜ
```

**Pass:** exit `0` · text appears **incrementally**, word by word (use
`--delay 0.2` on the mock to see it clearly) · no `data:` prefixes or JSON in
the output · no `usage` line — servers omit it while streaming.

### L03 — Raw JSON passthrough

```bash
bash/llm-prompt.sh --raw "Merhaba" | jq -c '{model, finish: .choices[0].finish_reason, usage}'
```

```json
{"model":"mock-model","finish":"stop","usage":{"prompt_tokens":1,"completion_tokens":16,"total_tokens":17}}
```

**Pass:** exit `0` · valid JSON · `model` is what you asked for — this is how
you catch a gateway that silently routes elsewhere.

### L04 — Prompt from stdin

```bash
echo "Merhaba" | bash/llm-prompt.sh
```

```
Merhaba! Bu bir mock yanittir - Türkçe karakter testi: çğışöüÇĞİŞÖÜ
```

**Pass:** exit `0` · identical to passing the prompt as an argument. Works with
`bash/llm-prompt.sh < prompt.txt` too.

### L05 — System prompt and sampling flags

```bash
bash/llm-prompt.sh -s "Kısa cevap ver" -t 0.2 -n 64 "Merhaba"
```

```
Merhaba! Bu bir mock yanittir - Türkçe karakter testi: çğışöüÇĞİŞÖÜ
```

**Pass:** exit `0`. Confirm the flags actually reached the server with `-v`:
the body must contain the `system` message, `"temperature":0.2` and
`"max_tokens":64`. (The mock ignores sampling; a real model will not.)

### L06 — Endpoint normalization

```bash
bash/llm-prompt.sh -e http://127.0.0.1:8899                      "ping"
bash/llm-prompt.sh -e http://127.0.0.1:8899/v1                   "ping"
bash/llm-prompt.sh -e http://127.0.0.1:8899/v1/chat/completions  "ping"
```

**Pass:** all three print the same answer and exit `0`. A gateway path prefix
(`https://gw.example.com/team-a/v1`) is preserved.

### L07 — HTTP error is surfaced, not swallowed

```bash
bash/llm-prompt.sh -m error-404 "x"; echo "exit=$?"
```

```
HTTP 404 from http://127.0.0.1:8899/v1/chat/completions
{"error": {"message": "injected error for model 'error-404'", "type": "injected_error", "code": null}}
exit=1
```

**Pass:** exit `1` · the server's own error body on **stderr** · nothing on
stdout. Any `error-<status>` model name works (`error-401`, `error-429`,
`error-500`) — use it to rehearse how your pipeline reacts.

### L08 — Missing configuration fails fast

```bash
LLM_MODEL="" bash/llm-prompt.sh "x"; echo "exit=$?"
```

```
model required (-m or $LLM_MODEL)
exit=1
```

**Pass:** exit `1` before any network call. Same for a missing endpoint or key.

---

## Embeddings

### E01 — Inspect a vector

```bash
python3 python/embed-test.py "Kubernetes GPU node etiketleme"
```

```
[0] Kubernetes GPU node etiketleme                     dim=128  |v|=1.000000  min=-0.5466 max=+0.4685
     head=[+0.0000, +0.0000, -0.0781, +0.0000, +0.0000, ...]
latency=7ms  texts=1  prompt_tokens=7  total_tokens=7
```

**Pass:** exit `0` · `dim=128` (mock) · `|v|=1.000000`.
**Varies:** `latency`. Against a real model, `dim` is the model's width
(1024 for bge-m3, 1536 for text-embedding-3-small) and the `head` values are
dense rather than mostly zero.

### E02 — Cosine similarity, paraphrase vs unrelated

```bash
python3 python/embed-test.py --pair \
  "Kubernetes cluster'inda GPU node'u nasil etiketlenir?" \
  "K8s uzerinde GPU'lu sunucuya label eklemenin yolu nedir?"

python3 python/embed-test.py --pair \
  "Kubernetes cluster'inda GPU node'u nasil etiketlenir?" \
  "Dun aksam sahilde balik izgara yaptik."
```

```
cosine=0.263365  dim=128  latency=6ms
cosine=-0.063540  dim=128  latency=6ms
```

**Pass:** the paraphrase pair scores **higher** than the unrelated pair. The
absolute numbers above are the mock's; a real retrieval model typically gives
~0.7–0.9 for the paraphrase and ~0.1–0.4 for the unrelated pair. **The ordering
is the assertion, not the value.**

### E03 — Sanity suite (the main gate)

```bash
python3 python/embed-test.py --suite; echo "exit=$?"
```

```
PASS  dim consistent across batch            dim=128
PASS  vectors L2-normalized                  norms=1.000000, 1.000000, 1.000000
PASS  deterministic across calls             max|delta|=0.000e+00 cos=1.00000000
PASS  cos(paraphrase) > cos(unrelated)       para=0.2634 unrelated=-0.0635 margin=0.3269
PASS  cos(identical) ~= 1.0                  cos=1.00000000
PASS  batch position does not change vector  cos(pos0)=1.00000000 cos(pos3)=1.00000000
PASS  long input (~264000 chars) handled     truncated silently, prompt_tokens=66000

7/7 passed  (dim=128, first call 6ms, prompt_tokens=36)
exit=0
```

**Pass:** `7/7 passed` and exit `0`. Exit is `1` if any check fails, so this
line works as a deployment gate:

```bash
python3 python/embed-test.py --suite || { echo "embedding endpoint unhealthy"; exit 1; }
```

Identical `cos` values were produced on Ubuntu, macOS and Windows in CI — the
suite is reproducible across platforms. What each check protects you from is
explained in [embeddings.md](embeddings.md#--suite--is-this-model-wired-up-correctly).

### E04 — Throughput benchmark

```bash
python3 python/embed-test.py --bench 64 --concurrency 8 --batch-size 8
```

```
requests=8  batch_size=8  concurrency=8  texts=64
wall=0.11s  throughput=600.7 texts/s  75.1 req/s
latency ms: mean=22 p50=10 p95=72 p99=99 max=105
```

**Pass:** exit `0` · `requests = 64 ÷ 8 = 8` · all latency percentiles present.
**Varies:** every number. Against the mock they measure your loopback and
Python; only real-endpoint numbers mean anything for capacity planning.

### E05 — Matryoshka dimensions and base64 transport

```bash
python3 python/embed-test.py --dimensions 64 --encoding-format base64 "merhaba"
```

```
[0] merhaba                                            dim=64  |v|=1.000000  min=-0.8944 max=+0.1491
     head=[+0.0000, +0.0000, +0.0000, +0.0000, +0.0000, ...]
latency=6ms  texts=1  prompt_tokens=1  total_tokens=1
```

**Pass:** `dim=64` — the server honoured `dimensions`, and the base64 float32
payload decoded correctly. If `dim` comes back at full width, the server
ignored the parameter: do **not** build an index assuming it works.

### E06 — Embeddings error path

```bash
python3 python/embed-test.py -m error-503 "x"; echo "exit=$?"
```

```
HTTP 503 from http://127.0.0.1:8899/v1/embeddings
{"error": {"message": "injected error for model 'error-503'", "type": "injected_error", "code": null}}
exit=1
```

**Pass:** exit `1` with the server's body on stderr.

---

## Against a real endpoint

Swap the three variables and re-run the same tests:

```bash
export LLM_ENDPOINT=http://10.0.0.10:8000
export LLM_API_KEY="$MY_KEY"
export LLM_MODEL=Qwen/Qwen2.5-7B-Instruct
export LLM_EMBED_MODEL=BAAI/bge-m3
```

What to expect instead of the mock's fixed values:

| Test | Expectation against a real server |
| --- | --- |
| L01 | A real answer · `finish=stop` (`length` means you hit `-n`) · tok/s in the tens-to-hundreds for a small model on one GPU |
| L02 | Tokens appear progressively. If the whole answer lands at once, a proxy is buffering — see [troubleshooting](troubleshooting.md#streaming-prints-nothing) |
| L03 | `model` matches what you requested. A different value means the gateway rerouted you |
| L07 | Try a deliberately wrong model name: expect `HTTP 404` or `HTTP 400` with the server's message |
| E01 | `dim` = the model's real width · `\|v\|` = 1.0 for most retrieval models |
| E02 | Paraphrase ≫ unrelated. A thin margin means the model is a poor fit for your language or domain |
| E03 | `7/7 passed`. Any FAIL is explained in [troubleshooting](troubleshooting.md#results-that-look-wrong) — treat *batch position* and *L2-normalized* as blockers |
| E04 | Raise `--batch-size` until throughput stops improving; watch p95/p99 for queueing |

Record your results with the same table shape and open a PR — verified numbers
from real backends are exactly what
[compatibility.md](compatibility.md) is for.
