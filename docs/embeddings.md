# Embeddings

[`python/embed-test.py`](../python/embed-test.py) talks to an OpenAI-compatible
`/v1/embeddings` endpoint using **only the Python standard library** — no
`requests`, no `numpy`, nothing to install. The same file runs on Linux, macOS
and Windows (`python3` / `py -3`).

```
./embed-test.py [text ...] [-e URL] [-k KEY] [-m MODEL]
                [-f FILE] [--pair A B] [--suite] [--bench N]
                [--concurrency C] [--batch-size B]
                [--dimensions D] [--encoding-format float|base64]
                [--timeout S] [-i] [-v]
```

Model name resolution: `-m` → `$LLM_EMBED_MODEL` → `$LLM_MODEL`. That way a
shell configured for a chat model still works when you point it at an embedding
service with one extra variable.

---

## Modes

### Default — inspect vectors

```bash
./embed-test.py -m BAAI/bge-m3 "Kubernetes GPU node etiketleme"
```

```
[0] Kubernetes GPU node etiketleme                     dim=1024  |v|=1.000000  min=-0.0731 max=+0.0645
     head=[+0.0121, -0.0304, +0.0088, -0.0155, +0.0210, ...]
latency=48ms  texts=1  prompt_tokens=9  total_tokens=9
```

`|v|` is the L2 norm — if it is not ~1.0, you must normalize before using dot
product as cosine similarity. Input can also come from `-f file.txt` (one text
per line) or stdin.

### `--pair` — how close are two texts?

```bash
./embed-test.py --pair "GPU node nasıl etiketlenir?" "K8s'te GPU sunucuya label"
# cosine=0.741215  dim=1024  latency=52ms
```

Useful for calibrating a retrieval threshold with real examples from your
corpus before you wire the model into a RAG pipeline.

### `--suite` — is this model wired up correctly?

Seven checks, run in one pass. Exits non-zero if any of them fail, so it works
as a deployment gate.

| Check | Catches |
| --- | --- |
| **dim consistent across batch** | A server that silently switches models or truncates a batch |
| **vectors L2-normalized** | Cosine-vs-dot-product mismatches — the #1 cause of "the ranking looks random" |
| **deterministic across calls** | Non-deterministic pooling, or a load balancer fanning out to differently-configured replicas |
| **cos(paraphrase) > cos(unrelated)** | A model that loaded but is not the model you think — or one that was never trained for retrieval |
| **cos(identical) ≈ 1.0** | Broken normalization or a per-request random seed |
| **batch position does not change vector** | Padding/pooling bugs: a text embedded differently depending on the other texts in the batch. This one bites in production, because you index in large batches and query with a single text |
| **long input handled** | Whether the server silently truncates past `max-model-len` or returns 4xx. Both are fine — but you need to know which |

```
PASS  dim consistent across batch            dim=1024
PASS  vectors L2-normalized                  norms=1.000000, 1.000000, 1.000000
PASS  deterministic across calls             max|delta|=0.000e+00 cos=1.00000000
PASS  cos(paraphrase) > cos(unrelated)       para=0.7412 unrelated=0.2688 margin=0.4724
PASS  cos(identical) ~= 1.0                  cos=1.00000000
PASS  batch position does not change vector  cos(pos0)=1.00000000 cos(pos3)=1.00000000
PASS  long input (~264000 chars) handled     truncated silently, prompt_tokens=8192

7/7 passed  (dim=1024, first call 61ms, prompt_tokens=36)
```

The probe texts are Turkish on purpose (a paraphrase pair plus an unrelated
sentence) — many multilingual embedding models score noticeably worse outside
English, and a thin margin here is a signal worth having before you build an
index on top. Edit `IDENT` / `PARA` / `UNREL` near the top of the file to use
sentences from your own domain.

### `--bench` — throughput and latency

```bash
./embed-test.py --bench 200 --concurrency 16 --batch-size 8
```

```
requests=25  batch_size=8  concurrency=16  texts=200
wall=1.84s  throughput=108.7 texts/s  13.6 req/s
latency ms: mean=1043 p50=1010 p95=1580 p99=1720 max=1733
```

`--bench N` is a **text** count: it issues `N ÷ batch-size` requests through a
thread pool of `--concurrency` workers.

How to read it:

- **`throughput`** is what capacity planning cares about. Raise `--batch-size`
  until it stops improving — that is your server's batching sweet spot.
- **`p95` / `p99`** are what your users feel. If p99 is several times p50, the
  server is queueing: lower concurrency or add a replica.
- Latency is measured **client-side**, so it includes network round-trip. Run
  it from a host near the server, and treat it as a comparison tool between
  configurations rather than an absolute figure.
- The load generator is a Python thread pool. Threads are fine here because the
  work is I/O-bound, but at very high concurrency the client itself can become
  the bottleneck — if `throughput` plateaus while the GPU is idle, suspect the
  client first.

---

## Options worth knowing

**`--dimensions D`** — Matryoshka truncation. Only some models support it
(`text-embedding-3-*`, `bge-m3` in certain deployments). When set, the suite
adds an eighth check verifying the server actually honoured it instead of
silently returning full-width vectors.

**`--encoding-format base64`** — asks for little-endian float32 blobs instead of
JSON number arrays. Roughly 3–4× less bytes on the wire for large batches; the
script decodes them transparently, so output is identical. A good way to verify
your server implements the format before switching a client library to it.

**`-i` / `--insecure`** — skip TLS verification for self-signed internal
endpoints.

**`-v`** — echo the outgoing request (with input elided) to stderr.

---

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success (or: all suite checks passed) |
| `1` | At least one suite check failed |
| `2` | Argument error (argparse) |
| `1` | Transport failure, non-2xx status, or a response without a `data` array |

Because `--suite` exits non-zero on failure, this works as-is in a pipeline:

```bash
python3 python/embed-test.py --suite || { echo "embedding endpoint is not healthy"; exit 1; }
```
