# Chat completions

Two scripts, one job: send a prompt to `/v1/chat/completions` and show you
exactly what came back.

| | Linux / macOS / WSL | Windows |
| --- | --- | --- |
| Script | [`bash/llm-prompt.sh`](../bash/llm-prompt.sh) | [`powershell/Invoke-LlmPrompt.ps1`](../powershell/Invoke-LlmPrompt.ps1) |
| Needs | `curl` + (`jq` or `python3`) | nothing beyond PowerShell 5.1 |

Both accept the same endpoint forms, read the same environment variables, and
print the assistant message on **stdout** with diagnostics on **stderr** — so
`llm-prompt.sh "..." > answer.txt` gives you a clean file even with `-v` on.

---

## `bash/llm-prompt.sh`

```
Usage: llm-prompt.sh [options] "prompt"

  -e, --endpoint URL     Base URL, .../v1 or full .../v1/chat/completions
                         (env: LLM_ENDPOINT)
  -k, --api-key KEY      Bearer token (env: LLM_API_KEY)
  -m, --model NAME       Model name (env: LLM_MODEL)
  -s, --system TEXT      System prompt
  -t, --temperature N    Default 0.0
  -n, --max-tokens N     Default 512
      --timeout N        Total request timeout in seconds, default 300
      --stream           Stream tokens as they arrive (SSE)
      --raw              Print the full JSON response
  -i, --insecure         Skip TLS verification (self-signed endpoints)
  -v, --verbose          Print token usage, latency and tok/s to stderr
  -h, --help             This text
```

The prompt can come from an argument, a pipe, or a heredoc:

```bash
llm-prompt.sh "Merhaba"
echo "Merhaba" | llm-prompt.sh
llm-prompt.sh < prompt.txt
llm-prompt.sh -- "--this-starts-with-dashes"
```

### Portability

The script targets **Bash 3.2**, which is what ships on macOS, and avoids
GNU-only behaviour so the same file works on a BusyBox container, a BSD box or
WSL:

- Elapsed time comes from `$EPOCHREALTIME` (Bash 5), then GNU `date +%s%N`,
  then `python3`, then whole seconds — never a raw `%N` that BSD `date` leaves
  unexpanded.
- The SSE stream is split with `awk` + `fflush()` rather than
  `grep --line-buffered | sed -u`, which do not exist outside GNU userland.
- `jq` is used when present; otherwise `python3` builds the request body and
  parses the response. You need one of the two, not both.

---

## `powershell/Invoke-LlmPrompt.ps1`

```powershell
.\Invoke-LlmPrompt.ps1 [-Prompt] <string>
                       [-Endpoint <string>] [-ApiKey <string>] [-Model <string>]
                       [-SystemPrompt <string>] [-Temperature <double>]
                       [-MaxTokens <int>] [-TimeoutSec <int>]
                       [-Stream] [-Raw] [-Insecure] [-Verbose]
```

Windows PowerShell 5.1 breaks OpenAI-compatible calls in two specific ways, and
the script handles both:

1. **TLS.** 5.1 negotiates SSL3/TLS1.0 on some hosts. The script ORs TLS 1.2
   into `ServicePointManager.SecurityProtocol` before the first request.
2. **Encoding.** 5.1 sends the body as ISO-8859-1 and decodes a response
   without an explicit `charset` the same way — which turns *Türkçe* into
   *TÃ¼rkÃ§e*. The script sends `[Text.Encoding]::UTF8.GetBytes(...)` and
   decodes `RawContentStream` as UTF-8 explicitly.

`-Insecure` maps to a `ServerCertificateValidationCallback` on 5.1 and to
`-SkipCertificateCheck` (or the HttpClient validator, when streaming) on 7+.

> **Note** — streaming uses `HttpClient` because `Invoke-WebRequest` buffers the
> whole response before returning. It is verified in CI on PowerShell 7
> (Ubuntu, macOS, Windows); 5.1 support is best-effort and loads
> `System.Net.Http` on demand.

---

## Reading `-v` / `-Verbose` output

```
prompt=14 completion=128 total=142 | 2.31s | 55.4 tok/s | finish=stop
```

| Field | Meaning |
| --- | --- |
| `prompt` / `completion` / `total` | Token counts reported by the server in `usage` |
| `2.31s` | **Client-side wall clock**: queueing + prefill + decode + network |
| `55.4 tok/s` | `completion_tokens ÷ wall clock` |
| `finish` | `stop` = model ended on its own · `length` = hit `max_tokens` · `content_filter` = blocked upstream |

Two honest caveats:

- **This is not a benchmark.** The number includes network round-trip and any
  time the request spent queued behind other requests. For real serving
  numbers use the server's own metrics (vLLM exposes `/metrics`) or a load
  generator that reports TTFT and inter-token latency separately.
- **Streaming mode prints no usage.** Most servers omit `usage` from SSE chunks
  unless you ask for `stream_options: {"include_usage": true}`, which these
  scripts do not send. Use blocking mode when you want the token counts.

---

## Recipes

**Compare two models on the same prompt**

```bash
for m in Qwen/Qwen2.5-7B-Instruct meta-llama/Llama-3.1-8B-Instruct; do
  echo "== $m"
  llm-prompt.sh -m "$m" -v "Explain KV cache in one sentence." 2>&1
done
```

**Run a prompt file and keep only the answers**

```bash
while IFS= read -r p; do
  printf '%s\t%s\n' "$p" "$(llm-prompt.sh "$p")"
done < prompts.txt > answers.tsv
```

**Measure cold start after a deploy** (first call loads weights)

```bash
time llm-prompt.sh -n 1 "hi" >/dev/null
```

**Gate a deployment in CI** — non-zero exit on any failure

```bash
llm-prompt.sh -m "$MODEL" -n 8 "ping" | grep -qi . || { echo "empty answer"; exit 1; }
```

**Check what a gateway actually routes to**

```bash
llm-prompt.sh --raw "hi" | jq '{model, id, system_fingerprint}'
```

**Deterministic re-runs** — `-t 0` is the default; note that temperature 0 is
*not* a guarantee of identical output on batched GPU servers (see
[compatibility](compatibility.md#what-openai-compatible-does-not-guarantee)).

---

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success — the assistant message was printed |
| `1` | Missing/invalid arguments, transport failure, non-2xx HTTP status, or an unparsable body |

The full response body is printed to stderr on a non-2xx status, so you see the
server's own error message rather than just the code.
