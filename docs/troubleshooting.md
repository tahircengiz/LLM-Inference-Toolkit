# Troubleshooting

Symptom → cause → fix. Every script prints the server's own error body to
stderr on a non-2xx response, so start by reading that.

## HTTP errors

| What you see | Likely cause | Fix |
| --- | --- | --- |
| `HTTP 404` with an HTML body | Wrong path. Your endpoint is behind a prefix, or the server is not the one you think | Try the base URL, `.../v1`, and the full path — the scripts normalize all three. `curl -s $BASE/v1/models` to see what is really there |
| `HTTP 401` / `authentication_error` | Missing or wrong bearer token | `-k` / `-ApiKey`, or `LLM_API_KEY`. Note Ollama ignores the value but the scripts still require one — pass `-k ollama` |
| `HTTP 400` `model ... does not exist` | Model name is not what the server serves | `curl -s -H "Authorization: Bearer $LLM_API_KEY" $BASE/v1/models \| jq -r '.data[].id'` |
| `HTTP 400` about `max_tokens` | A recent OpenAI reasoning model that wants `max_completion_tokens` | Use a self-hosted endpoint, or call that model with an SDK. See [compatibility](compatibility.md#what-openai-compatible-does-not-guarantee) |
| `HTTP 422` from an embeddings server | Input longer than `max-model-len`, or an unsupported `dimensions` value | Chunk the input; drop `--dimensions` |
| `HTTP 429` | Rate limit or a full request queue | Lower `--concurrency`; retry |
| `HTTP 500` after a long wait | The model is still loading, or OOM'd on a long prompt | Check server logs. Raise `--timeout` for a cold start |

## TLS

| What you see | Fix |
| --- | --- |
| `curl: (60) SSL certificate problem: self signed certificate` | Add the internal CA to the trust store, or use `-i` for a throwaway check |
| PowerShell: *Could not create SSL/TLS secure channel* | The script already forces TLS 1.2 on 5.1. If it persists, the endpoint likely requires TLS 1.3 (use PowerShell 7) or a client certificate |
| PowerShell: *The remote certificate is invalid* | `-Insecure`, or install the CA under `Cert:\LocalMachine\Root` |

`-i` / `-Insecure` disables verification completely. Fine for a lab endpoint,
never for anything reachable from the internet.

## Encoding

| What you see | Cause | Fix |
| --- | --- | --- |
| `TÃ¼rkÃ§e` instead of `Türkçe` | The server omitted `charset=utf-8` and the client assumed ISO-8859-1 | Both scripts here handle it explicitly. If you see it with your own tooling, decode the raw bytes as UTF-8 rather than trusting the header |
| Turkish characters look right in the terminal but wrong in a redirected file | Console code page, not the response | On Windows: `[Console]::OutputEncoding = [Text.Encoding]::UTF8` before running, or use `-Raw` and parse the JSON downstream |
| Mojibake only in streaming mode | A multi-byte character split across two SSE chunks | The scripts decode the stream as UTF-8 end to end; if you built your own splitter, buffer bytes rather than characters |

## Streaming prints nothing

1. The server ignored `stream: true` and returned one JSON blob — run the same
   call with `--raw` to see.
2. A reverse proxy is buffering. On nginx: `proxy_buffering off;` and
   `proxy_read_timeout` high enough for the whole generation.
3. You are on Bash but piping through something that buffers. The script
   already uses `awk` + `fflush()` and `jq --unbuffered`; adding another `grep`
   or `sed` downstream can re-introduce buffering.

## Environment

| Problem | Fix |
| --- | --- |
| `jq: command not found` | Not fatal — the Bash script falls back to `python3`. Install `jq` for slightly faster JSON handling |
| `curl: command not found` | Required by the Bash script. On Windows, use the PowerShell script instead — it needs no `curl.exe` |
| `.\Invoke-LlmPrompt.ps1 cannot be loaded because running scripts is disabled` | `powershell -ExecutionPolicy Bypass -File .\Invoke-LlmPrompt.ps1 ...`, or `Unblock-File .\Invoke-LlmPrompt.ps1` |
| `Permission denied` running `llm-prompt.sh` | `chmod +x bash/llm-prompt.sh`, or invoke it as `bash bash/llm-prompt.sh` |
| Works locally, hangs from a jump host | Proxy variables. `curl` honours `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY`; .NET honours the system proxy. Add the endpoint to `NO_PROXY` for internal hosts |
| Everything times out on the first call, then is fast | Cold start — weights loading, CUDA graph capture. Raise `--timeout` / `-TimeoutSec` |

## Results that look wrong

| Observation | What it usually means |
| --- | --- |
| `finish=length` and a truncated answer | Hit `max_tokens`. Raise `-n` / `-MaxTokens` |
| tok/s far below expectations | The number includes queueing and network. Check the server's own metrics, run from a closer host, and compare like with like |
| `--suite`: **vectors L2-normalized FAIL** | The model returns unnormalized vectors. Normalize client-side before using dot product as cosine, or your ranking will be dominated by vector magnitude |
| `--suite`: **batch position does not change vector FAIL** | A pooling/padding bug on the server. Documents indexed in batches will not match queries embedded alone — treat this as a blocker |
| `--suite`: **cos(paraphrase) > cos(unrelated) FAIL** | Either the wrong model is loaded, or it is not a retrieval model. Try your own domain sentences before concluding |
| `--bench` throughput plateaus while the GPU is idle | The client is the bottleneck, not the server. Run from a bigger host or several in parallel |

## Still stuck?

Reproduce it against the mock server first:

```bash
python3 examples/mock_server.py --port 8899 -v
python3 tests/smoke_test.py -v
```

If the smoke test passes but your endpoint fails, the difference is on the
server side — and the `-v` output of both is a good thing to attach to an issue.
