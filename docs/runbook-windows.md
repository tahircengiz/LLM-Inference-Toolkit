# Test runbook — Windows / PowerShell

Every test below has been **run and verified**: the command is exactly what you
type, and the expected output is copied verbatim from a real run against the
bundled mock server. Anything that legitimately varies between runs (latency,
tok/s) is called out per test.

Linux / macOS / WSL users: see [runbook-linux.md](runbook-linux.md) instead.

## Verified environments

| Environment | PowerShell | Python | Result |
| --- | --- | --- | --- |
| `windows-latest` (CI, Windows Server) | 7.6.5 | 3.14.7 | ✅ 17/17 (Bash tests skipped by design) |
| PowerShell 7.6.3 on macOS (local) | 7.6.3 | 3.9.6 | ✅ |
| Windows PowerShell 5.1 | 5.1 | — | ⚠️ supported, not yet covered by CI — reports welcome |

CI confirms the one thing Windows usually gets wrong: the response comes back
as clean UTF-8, so `çğışöüÇĞİŞÖÜ` survives the round trip.

## Setup

```powershell
git clone https://github.com/tahircengiz/LLM-Inference-Toolkit.git
cd LLM-Inference-Toolkit

# Window 1 - the mock server that produces the expected values below
python examples\mock_server.py --port 8899

# Window 2
$env:LLM_ENDPOINT    = 'http://127.0.0.1:8899'
$env:LLM_API_KEY     = 'sk-mock'
$env:LLM_MODEL       = 'mock-model'
$env:LLM_EMBED_MODEL = 'mock-model'
```

If the script will not start:

```powershell
Unblock-File .\powershell\Invoke-LlmPrompt.ps1
# or, per invocation:
powershell -ExecutionPolicy Bypass -File .\powershell\Invoke-LlmPrompt.ps1 "Merhaba"
```

To run every test at once instead of one by one:

```powershell
python tests\smoke_test.py     # expect: 17 passed, 0 failed, 1 skipped
```

The skip is the Bash script — on Windows, use the PowerShell one.

---

## Chat completions

### W01 — Blocking request with diagnostics

```powershell
.\powershell\Invoke-LlmPrompt.ps1 "Merhaba, kendini tanıt" -Verbose
```

```
VERBOSE: POST http://127.0.0.1:8899/v1/chat/completions
VERBOSE: Body: {"model":"mock-model","messages":[{"role":"user","content":"Merhaba, kendini tanıt"}],"temperature":0.0,"max_tokens":512,"stream":false}
Merhaba! Bu bir mock yanittir - Türkçe karakter testi: çğışöüÇĞİŞÖÜ
VERBOSE: prompt=5 completion=16 total=21 | 0.02s | 1004.7 tok/s | finish=stop
```

**Pass:** exit `0` · the answer on stdout · `finish=stop` · Turkish characters
intact. The usage line always uses `.` as the decimal separator, even on a
Turkish-locale machine — it is formatted with `InvariantCulture` so the output
stays parseable.
**Varies:** the `0.02s` and `1004.7 tok/s` figures.

> `$LASTEXITCODE` is only set for external programs. To check the exit code of
> this script, run it as `pwsh -NoProfile -File .\powershell\Invoke-LlmPrompt.ps1 ...`
> and then read `$LASTEXITCODE`.

### W02 — Streaming (SSE)

```powershell
.\powershell\Invoke-LlmPrompt.ps1 "Merhaba" -Stream
```

```
Merhaba! Bu bir mock yanittir - Türkçe karakter testi: çğışöüÇĞİŞÖÜ
```

**Pass:** exit `0` · text appears **incrementally**, word by word (start the
mock with `--delay 0.2` to see it clearly) · no `data:` prefixes · no usage
line — servers omit it while streaming.

Streaming uses `HttpClient` rather than `Invoke-WebRequest`, which buffers the
whole response. Verified on PowerShell 7 in CI on all three OSes; on 5.1 the
script loads `System.Net.Http` on demand.

### W03 — Raw JSON passthrough

```powershell
.\powershell\Invoke-LlmPrompt.ps1 "Merhaba" -Raw | ConvertFrom-Json |
    Select-Object model, @{n='finish';e={$_.choices[0].finish_reason}}, @{n='total';e={$_.usage.total_tokens}}
```

```
model      finish total
-----      ------ -----
mock-model stop      17
```

**Pass:** exit `0` · valid JSON · `model` is what you asked for — this is how
you catch a gateway that silently routes elsewhere.

### W04 — System prompt and sampling flags

```powershell
.\powershell\Invoke-LlmPrompt.ps1 "Merhaba" -SystemPrompt "Kısa cevap ver" -Temperature 0.2 -MaxTokens 64
```

```
Merhaba! Bu bir mock yanittir - Türkçe karakter testi: çğışöüÇĞİŞÖÜ
```

**Pass:** exit `0`. Confirm the flags actually reached the server by adding
`-Verbose`: the body must contain the `system` message, `"temperature":0.2` and
`"max_tokens":64`. (The mock ignores sampling; a real model will not.)

### W05 — Endpoint normalization

```powershell
.\powershell\Invoke-LlmPrompt.ps1 "ping" -Endpoint 'http://127.0.0.1:8899'
.\powershell\Invoke-LlmPrompt.ps1 "ping" -Endpoint 'http://127.0.0.1:8899/v1'
.\powershell\Invoke-LlmPrompt.ps1 "ping" -Endpoint 'http://127.0.0.1:8899/v1/chat/completions'
```

**Pass:** all three print the same answer and exit `0`. A gateway path prefix
(`https://gw.example.com/team-a/v1`) is preserved.

### W06 — HTTP error is surfaced, not swallowed

```powershell
pwsh -NoProfile -File .\powershell\Invoke-LlmPrompt.ps1 "x" -Model error-404
$LASTEXITCODE
```

```
HTTP 404 from http://127.0.0.1:8899/v1/chat/completions
{
  "error": {
    "message": "injected error for model 'error-404'",
    "type": "injected_error",
    "code": null
  }
}
1
```

**Pass:** exit `1` · the server's own error body on **stderr** · nothing on
stdout. The first line matches the Bash script character for character; the body
below it is pretty-printed by PowerShell 7. Any `error-<status>` model name
works (`error-401`, `error-429`, `error-500`).

### W07 — Missing configuration fails fast

```powershell
$env:LLM_MODEL = ''
pwsh -NoProfile -File .\powershell\Invoke-LlmPrompt.ps1 "x"
$LASTEXITCODE
$env:LLM_MODEL = 'mock-model'   # restore
```

```
-Model is required (or set $env:LLM_MODEL).
1
```

**Pass:** exit `1` before any network call, with a single clean stderr line —
no PowerShell exception block. Same for a missing endpoint or key.

---

## Model discovery

### W08 — List what the endpoint serves

```powershell
.\powershell\Get-LlmModels.ps1
```

```
mock-model
mock-embed
error-503
```

**Pass:** exit `0` · one id per line, in the server's own order. The mock
deliberately advertises three models, one of which does not work — that is what
makes W11 reproducible.

### W09 — Metadata table

```powershell
.\powershell\Get-LlmModels.ps1 -Long
```

```
Model      Owner Created              Context
-----      ----- -------              -------
mock-model mock  2025-01-01T00:00:00Z 8192
mock-embed mock  2025-03-01T00:00:00Z 512
error-503  mock  -                    -
```

**Pass:** exit `0` · timestamps in UTC ISO-8601, formatted with
`InvariantCulture` so a tr-TR host prints the same string · `-` wherever the
server publishes nothing.
**Varies:** nothing. This output is byte-identical on every machine.

`-Long` emits **objects**, so discovery composes with the rest of PowerShell:

```powershell
.\powershell\Get-LlmModels.ps1 -Long |
    Where-Object { $_.Context -ne '-' -and [int]$_.Context -ge 1024 } |
    Select-Object Model, Context
```

```
Model      Context
-----      -------
mock-model 8192
```

### W10 — Filter by substring

```powershell
.\powershell\Get-LlmModels.ps1 mock-embed
```

```
mock-embed
```

**Pass:** exit `0` · case-insensitive match on the id · exit `1` with
`no model matches <pattern>` when nothing matches.

### W11 — Probe: which models actually answer?

```powershell
pwsh -NoProfile -File .\powershell\Get-LlmModels.ps1 -Probe
$LASTEXITCODE
```

```
Model      Status Ms Note
-----      ------ -- ----
mock-model ok      3
mock-embed 400     5 this model does not support chat completions
error-503  503     1 injected error for model 'error-503'
1/3 models answered
1
```

**Pass:** exit `1` — because one advertised model fails, which is the point of
the test · every model gets a row · the `Note` column carries the **server's
own** error message · the `n/n models answered` summary goes to stderr, so the
table itself stays clean when redirected.
**Varies:** the `Ms` column.

A `400` on an embedding model is correct behaviour, not a fault. Each probe is a
real `max_tokens: 1` request, so filter first on a paid gateway:
`.\powershell\Get-LlmModels.ps1 -Probe qwen`.

### W12 — Assert a model is served (CI gate)

```powershell
pwsh -NoProfile -File .\powershell\Get-LlmModels.ps1 -Has mock-model
$LASTEXITCODE
pwsh -NoProfile -File .\powershell\Get-LlmModels.ps1 -Has no-such-model
$LASTEXITCODE
```

```
0
model 'no-such-model' is not served by http://127.0.0.1:8899/v1/models
1
```

**Pass:** silent success, one stderr line and exit `1` on a miss. Matching is
exact and case-sensitive — the same way the server matches.

### W13 — Raw JSON

```powershell
.\powershell\Get-LlmModels.ps1 -Json | ConvertFrom-Json | Select-Object -ExpandProperty data | Select-Object -First 1
```

```
id            : mock-model
object        : model
created       : 1735689600
owned_by      : mock
max_model_len : 8192
```

**Pass:** exit `0` · valid JSON straight from the server.

---

## Embeddings

The embeddings script is Python and behaves identically on every OS. Use
`python` (or `py -3`) instead of `python3`:

```powershell
python python\embed-test.py "Kubernetes GPU node etiketleme"
python python\embed-test.py --pair "GPU node nasıl etiketlenir?" "K8s'te GPU sunucuya label"
python python\embed-test.py --suite
python python\embed-test.py --bench 64 --concurrency 8 --batch-size 8
python python\embed-test.py --dimensions 64 --encoding-format base64 "merhaba"
python python\embed-test.py -m error-503 "x"
```

Expected output for each, plus what every check protects you from, is in
[runbook-linux.md § Embeddings](runbook-linux.md#embeddings) — the values are
identical. CI verified that the suite produces the **same cosine values**
(`para=0.2634 unrelated=-0.0635`) on Windows, Ubuntu and macOS.

If Turkish characters look wrong in your console (but fine in a file), set the
console encoding once per session:

```powershell
[Console]::OutputEncoding = [Text.Encoding]::UTF8
```

---

## Against a real endpoint

```powershell
$env:LLM_ENDPOINT    = 'http://10.0.0.10:8000'
$env:LLM_API_KEY     = $env:MY_KEY
$env:LLM_MODEL       = 'Qwen/Qwen2.5-7B-Instruct'
$env:LLM_EMBED_MODEL = 'BAAI/bge-m3'
```

Then re-run W01–W13. Expectations are the same as the Linux runbook's
[real-endpoint table](runbook-linux.md#against-a-real-endpoint).

Windows-specific things to watch for:

| Symptom | Cause | Fix |
| --- | --- | --- |
| *Could not create SSL/TLS secure channel* | Windows PowerShell 5.1 defaulting below TLS 1.2 | The script already forces TLS 1.2. If it persists, the endpoint needs TLS 1.3 → use PowerShell 7 |
| *The remote certificate is invalid* | Internal CA not trusted | `-Insecure` for a lab endpoint, or install the CA under `Cert:\LocalMachine\Root` |
| `TÃ¼rkÃ§e` in output | Console code page, not the response | `[Console]::OutputEncoding = [Text.Encoding]::UTF8` |
| Hangs from a corporate network | Proxy | .NET uses the system proxy — check `netsh winhttp show proxy` and bypass internal hosts |
| Script will not run | Execution policy | `Unblock-File`, or `-ExecutionPolicy Bypass` |
