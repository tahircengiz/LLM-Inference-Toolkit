# Model discovery — `/v1/models`

`GET /v1/models` is the cheapest question you can ask an inference endpoint,
and the answer settles most "why doesn't this work" tickets before they start:
*is the thing I am about to call actually there, and does it answer?*

| | Linux / macOS / WSL | Windows |
| --- | --- | --- |
| Script | [`bash/llm-models.sh`](../bash/llm-models.sh) | [`powershell/Get-LlmModels.ps1`](../powershell/Get-LlmModels.ps1) |
| Needs | `curl` + (`jq` or `python3`) | nothing beyond PowerShell 5.1 |

Both take the same endpoint forms as the chat scripts, share `LLM_ENDPOINT` /
`LLM_API_KEY`, and **exit with the same codes** for the same conditions.

---

## `bash/llm-models.sh`

```
Usage: llm-models.sh [options] [pattern]

  pattern                Case-insensitive substring filter on the model id

  -e, --endpoint URL     Base URL, .../v1 or full .../v1/models
  -k, --api-key KEY      Bearer token
  -l, --long             Table: id, owned_by, created, context length
      --json             Print the raw JSON response
      --has MODEL        Exit 0 only if MODEL is served exactly (quiet, like grep -q)
      --probe            Send a 1-token chat request to every listed model and
                         report which ones answer. Exits 1 if any fail
      --timeout N        Request timeout in seconds, default 60
  -i, --insecure         Skip TLS verification
  -v, --verbose          Print the request URL to stderr
  -h, --help             This text
```

## `powershell/Get-LlmModels.ps1`

```powershell
.\Get-LlmModels.ps1 [[-Pattern] <string>]
                    [-Endpoint <string>] [-ApiKey <string>]
                    [-Long] [-Json] [-Has <string>] [-Probe]
                    [-TimeoutSec <int>] [-Insecure] [-Verbose]
```

The PowerShell version emits **objects**, not text, so discovery composes with
the rest of the shell:

```powershell
.\powershell\Get-LlmModels.ps1 -Long | Where-Object { $_.Context -ne '-' -and [int]$_.Context -ge 1024 }
.\powershell\Get-LlmModels.ps1 -Long | Export-Csv models.csv -NoTypeInformation
```

---

## The four things it answers

### 1. What is served?

```bash
llm-models.sh          # ids, one per line - pipeable
llm-models.sh -l       # id, owner, created, context length
```

The context column reads `max_model_len` (vLLM), then `context_length`, then
`max_input_tokens`, and shows `-` when the server publishes none of them.
Knowing it up front is what stops a 400 halfway through an ingestion run.

### 2. Is *my* model served? (deployment gate)

```bash
llm-models.sh --has "Qwen/Qwen2.5-7B-Instruct" || {
    echo "model missing on $LLM_ENDPOINT"; exit 1
}
```

Quiet on success, one line to stderr and exit 1 on failure — the same shape as
`grep -q`, so it drops straight into CI. Matching is **exact and
case-sensitive**, because that is how the server matches it too.

### 3. Which of them actually answer?

```bash
llm-models.sh --probe
```

```
MODEL       STATUS    LATENCY  NOTE
mock-model  ok           16ms
mock-embed  400          17ms  this model does not support chat completions
error-503   503          17ms  injected error for model 'error-503'

1/3 models answered
```

A listing is a claim, not a guarantee. Gateways routinely advertise models that
are unrouted, mis-keyed, or not chat models at all. `--probe` sends one
`max_tokens: 1` request per model and prints what came back — exiting 1 if any
of them failed, so it works as a post-deploy check.

Two things to keep in mind:

- **It costs tokens.** One tiny request per model, but against a paid gateway
  with 50 aliases that is 50 billable calls. Filter first: `llm-models.sh --probe qwen`.
- **A 400 is not always a fault.** Embedding and reranker models legitimately
  reject chat requests; the NOTE column carries the server's own explanation so
  you can tell the two apart.

### 4. What does the raw payload look like?

```bash
llm-models.sh --json | jq '.data[0]'
```

Useful when a server publishes extra fields — vLLM adds `max_model_len` and
`permission`, some gateways add routing metadata.

---

## Exit codes

Identical in both scripts:

| Code | Meaning |
| --- | --- |
| `0` | Listed successfully · `--has` found the model · `--probe` and every model answered |
| `1` | Missing arguments, transport failure, non-2xx status, unparsable body, no model matched the filter, `--has` miss, or `--probe` with at least one failure |

---

## Backend notes

| Backend | What `/v1/models` returns |
| --- | --- |
| **vLLM** | The served model with `max_model_len` — the fastest way to confirm `--served-model-name` |
| **llama.cpp** (`llama-server`) | Its single loaded model. Chat ignores the `model` field entirely, so `--has` is more informative than a chat call |
| **Ollama** | The pulled tags (`llama3.1:8b`). Any bearer token is accepted, but one must be sent |
| **TGI** | Often a single entry named `tgi` |
| **LiteLLM / gateways** | Your virtual aliases, not the upstream model names. `--probe` is worth running here: an alias can exist in the list and still be unrouted |
| **OpenAI** | The full catalogue your key can see — expect a long list, so filter |

Verified command-and-output pairs live in the runbooks:
[Linux](runbook-linux.md#model-discovery) · [Windows](runbook-windows.md#model-discovery).
