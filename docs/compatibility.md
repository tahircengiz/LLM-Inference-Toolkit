# Backend compatibility

Everything here speaks plain OpenAI HTTP — bearer auth, `/v1/chat/completions`
and `/v1/embeddings` — so anything implementing that surface should work. This
page collects the per-backend details that trip people up.

> **Verification status.** CI exercises the scripts against the bundled mock
> server on Ubuntu, macOS and Windows. The notes below come from each project's
> API surface, not from an automated matrix against every backend. If a server
> behaves differently for you, please open an issue — that is exactly the kind
> of report this file exists to collect.

## Chat (`/v1/chat/completions`)

| Backend | Typical base URL | `model` value | Auth | Notes |
| --- | --- | --- | --- | --- |
| **vLLM** | `http://host:8000` | HF repo id, or `--served-model-name` | `--api-key` (else any token) | The reference target. `GET /v1/models` lists what is actually served; Prometheus metrics on `/metrics` |
| **SGLang** | `http://host:30000` | served model name | optional | OpenAI-compatible router and server |
| **llama.cpp** (`llama-server`) | `http://host:8080` | any string — it serves one model | `--api-key` | Ignores the `model` field; useful when you want to test the transport, not routing |
| **TGI** (Messages API) | `http://host:8080` | often literally `tgi` | bearer | OpenAI-compatible chat since TGI 1.4; older builds only expose `/generate` |
| **Ollama** | `http://host:11434` | `llama3.1:8b` (tag included) | ignored — send any token | Compatibility layer under `/v1`; the scripts require *some* key, so pass `-k ollama` |
| **LM Studio** | `http://host:1234` | the id shown in the app | ignored | Handy for testing on a laptop |
| **OpenAI** | `https://api.openai.com` | `gpt-4o-mini`, … | real key | See the `max_tokens` caveat below |
| **LiteLLM / gateways** | `https://gw.example.com` | your virtual model alias | virtual key | Path prefixes work: `https://gw.example.com/team-a/v1` |
| **Azure OpenAI** (classic) | `https://x.openai.azure.com/openai/deployments/...` | deployment name | `api-key` **header** | ✗ Not supported: different URL shape and header. Put a gateway in front, or use the newer Azure surface that accepts bearer tokens |

## Embeddings (`/v1/embeddings`)

| Backend | Typical base URL | Notes |
| --- | --- | --- |
| **vLLM** (embedding model) | `http://host:8000` | Serve an embedding model, e.g. `vllm serve BAAI/bge-m3` |
| **TEI** (text-embeddings-inference) | `http://host:8080` | Exposes both its native `/embed` and an OpenAI-compatible `/v1/embeddings` |
| **Infinity** | `http://host:7997` | OpenAI-compatible, supports several models per process |
| **Ollama** | `http://host:11434` | `/v1/embeddings` with an embedding model such as `nomic-embed-text` |
| **OpenAI** | `https://api.openai.com` | `text-embedding-3-small/large`, supports `dimensions` |

## Model listings (`/v1/models`)

| Backend | What the listing contains |
| --- | --- |
| **vLLM** | The served model plus `max_model_len` — the quickest check that `--served-model-name` is what you think |
| **llama.cpp** | The single loaded model; the `model` field is ignored on chat, so the listing is the only honest source |
| **Ollama** | Pulled tags (`llama3.1:8b`). Any bearer token is accepted, but one must be sent |
| **TGI** | Often a single entry named `tgi` |
| **LiteLLM / gateways** | Your virtual aliases, not upstream names. An alias can be listed and still be unrouted — `llm-models.sh --probe` is what catches that |
| **OpenAI** | Everything your key can see; filter before probing |

See [models.md](models.md) for the helper that reads these.

## What "OpenAI-compatible" does not guarantee

These are the differences that actually cause incidents. The scripts in this
repo are built to make each one visible.

1. **`max_tokens` vs `max_completion_tokens`.** OpenAI's newer reasoning models
   reject `max_tokens`. These scripts send `max_tokens`, which every
   self-hosted server listed above accepts — but a call to a recent OpenAI
   reasoning model will fail with a 400 telling you to use
   `max_completion_tokens`. This toolkit targets self-hosted inference first.
2. **`temperature: 0` is not determinism.** Continuous batching means your
   request is computed alongside whatever else arrived at the same time, and
   floating-point reduction order changes with batch composition. Expect
   *nearly* identical, not identical.
3. **Usage in streaming.** Many servers omit `usage` from SSE chunks unless the
   client sends `stream_options: {"include_usage": true}`. Use blocking mode
   for token accounting.
4. **Embeddings may not be normalized.** vLLM, TEI and Infinity normalize for
   most models, but not universally — `--suite` tells you rather than assuming.
5. **Silent truncation.** Past `max-model-len`, some servers truncate and
   return a vector anyway; others 4xx. Both are defensible; the difference
   decides whether your ingestion pipeline needs its own chunking guard.
6. **`model` may be decorative.** Single-model servers ignore the field
   entirely, so a typo that would 404 on a gateway happily returns an answer
   locally. Check `--raw | jq .model` when it matters.
7. **`dimensions` may be ignored.** A server that accepts the parameter and
   returns full-width vectors will quietly break an index built at a smaller
   width.

## Trying it without any backend

[`examples/mock_server.py`](../examples/mock_server.py) implements
`/v1/models`, `/v1/chat/completions` (blocking + SSE) and `/v1/embeddings`
(float + base64) with deterministic pseudo-embeddings — enough to exercise
every code path in this repo, including the sanity suite.

```bash
python3 examples/mock_server.py --port 8899 --delay 0.2 -v
```

`--delay` adds artificial latency (handy for watching the streaming path),
`--no-auth` disables the bearer check, `-v` logs each request.
