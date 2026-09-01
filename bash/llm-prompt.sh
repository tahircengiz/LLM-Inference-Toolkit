#!/usr/bin/env bash
# Send a single prompt to an OpenAI-compatible /v1/chat/completions endpoint
# (vLLM, llama.cpp server, TGI OpenAI shim, Ollama, OpenAI, gateways).
#
#   ./llm-prompt.sh -e http://10.0.0.10:8000 -k sk-xxx -m Qwen/Qwen2.5-7B-Instruct "Merhaba"
#   LLM_ENDPOINT=... LLM_API_KEY=... LLM_MODEL=... ./llm-prompt.sh --stream "2+2 kac?"
#
# Requires: curl, and one of jq (preferred) or python3 for JSON handling.
# Portable across GNU/Linux, macOS and WSL - no GNU-only flags.

set -euo pipefail

ENDPOINT="${LLM_ENDPOINT:-}"
API_KEY="${LLM_API_KEY:-}"
MODEL="${LLM_MODEL:-}"
SYSTEM_PROMPT=""
TEMPERATURE=0.0
MAX_TOKENS=512
TIMEOUT=300
STREAM=false
RAW=false
INSECURE=false
VERBOSE=false
USER_PROMPT=""

usage() {
    cat <<'EOF'
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

Prompt can also be piped:  echo "..." | llm-prompt.sh -m foo
EOF
}

die() { printf '%s\n' "$*" >&2; exit 1; }

# Milliseconds since the epoch. GNU date understands %N, BSD/macOS date does
# not, so fall back to bash 5's $EPOCHREALTIME, then python3, then whole seconds.
now_ms() {
    if [[ -n "${EPOCHREALTIME:-}" ]]; then
        local t="${EPOCHREALTIME/,/.}"   # some locales format with a comma
        printf '%s' "$(( ${t%%.*} * 1000 + 10#${t#*.} / 1000 ))"
        return
    fi
    local ns
    ns="$(date +%s%N 2>/dev/null || true)"
    if [[ "$ns" =~ ^[0-9]{16,}$ ]]; then
        printf '%s' "$(( ns / 1000000 ))"
    elif command -v python3 >/dev/null 2>&1; then
        python3 -c 'import time; print(int(time.time() * 1000))'
    else
        printf '%s' "$(( $(date +%s) * 1000 ))"
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -e|--endpoint)    ENDPOINT="$2"; shift 2 ;;
        -k|--api-key)     API_KEY="$2"; shift 2 ;;
        -m|--model)       MODEL="$2"; shift 2 ;;
        -s|--system)      SYSTEM_PROMPT="$2"; shift 2 ;;
        -t|--temperature) TEMPERATURE="$2"; shift 2 ;;
        -n|--max-tokens)  MAX_TOKENS="$2"; shift 2 ;;
        --timeout)        TIMEOUT="$2"; shift 2 ;;
        --stream)         STREAM=true; shift ;;
        --raw)            RAW=true; shift ;;
        -i|--insecure)    INSECURE=true; shift ;;
        -v|--verbose)     VERBOSE=true; shift ;;
        -h|--help)        usage; exit 0 ;;
        --)               shift; USER_PROMPT="$*"; break ;;
        -*)               die "Unknown option: $1" ;;
        *)                USER_PROMPT="$1"; shift ;;
    esac
done

# Prompt from stdin when not given as an argument and stdin is not a tty
if [[ -z "$USER_PROMPT" && ! -t 0 ]]; then
    USER_PROMPT="$(cat)"
fi

command -v curl >/dev/null 2>&1 || die "curl not found (apt install curl)"
[[ -n "$ENDPOINT"    ]] || die "endpoint required (-e or \$LLM_ENDPOINT)"
[[ -n "$API_KEY"     ]] || die "api key required (-k or \$LLM_API_KEY)"
[[ -n "$MODEL"       ]] || die "model required (-m or \$LLM_MODEL)"
[[ -n "$USER_PROMPT" ]] || die "prompt required (argument or stdin)"

HAVE_JQ=false
command -v jq >/dev/null 2>&1 && HAVE_JQ=true
if ! $HAVE_JQ && ! command -v python3 >/dev/null 2>&1; then
    die "need jq or python3 for JSON handling (apt install jq)"
fi

# --- endpoint normalization -------------------------------------------------
url="${ENDPOINT%/}"
case "$url" in
    */chat/completions) : ;;
    */v1)               url="$url/chat/completions" ;;
    *)                  url="$url/v1/chat/completions" ;;
esac

# --- request body -----------------------------------------------------------
build_body() {
    if $HAVE_JQ; then
        jq -nc \
            --arg model "$MODEL" \
            --arg prompt "$USER_PROMPT" \
            --arg sys "$SYSTEM_PROMPT" \
            --argjson temp "$TEMPERATURE" \
            --argjson max "$MAX_TOKENS" \
            --argjson stream "$STREAM" \
            '{
                model: $model,
                messages: (if $sys == "" then [] else [{role:"system",content:$sys}] end
                           + [{role:"user",content:$prompt}]),
                temperature: $temp,
                max_tokens: $max,
                stream: $stream
             }'
    else
        MODEL="$MODEL" USER_PROMPT="$USER_PROMPT" SYSTEM_PROMPT="$SYSTEM_PROMPT" \
        TEMPERATURE="$TEMPERATURE" MAX_TOKENS="$MAX_TOKENS" STREAM="$STREAM" \
        python3 -c '
import json, os
sysp = os.environ["SYSTEM_PROMPT"]
msgs = ([{"role": "system", "content": sysp}] if sysp else [])
msgs.append({"role": "user", "content": os.environ["USER_PROMPT"]})
print(json.dumps({
    "model": os.environ["MODEL"],
    "messages": msgs,
    "temperature": float(os.environ["TEMPERATURE"]),
    "max_tokens": int(os.environ["MAX_TOKENS"]),
    "stream": os.environ["STREAM"] == "true",
}))'
    fi
}

body="$(build_body)"

curl_opts=(
    --silent --show-error
    --max-time "$TIMEOUT"
    --header "Authorization: Bearer ${API_KEY}"
    --header "Content-Type: application/json"
    --header "Accept: application/json"
    --data-binary @-
)
$INSECURE && curl_opts+=(--insecure)

$VERBOSE && printf 'POST %s\n%s\n' "$url" "$body" >&2

# --- streaming path ---------------------------------------------------------
# awk (not "grep --line-buffered | sed -u") so the pipeline also streams on
# macOS/BSD, where those GNU flags do not exist.
if $STREAM; then
    if $HAVE_JQ; then
        printf '%s' "$body" | curl "${curl_opts[@]}" --no-buffer \
            --header "Accept: text/event-stream" "$url" \
        | awk '
            substr($0, 1, 6) == "data: " {
                payload = substr($0, 7)
                if (payload == "[DONE]") exit
                print payload
                fflush()
            }' \
        | jq -j --unbuffered '.choices[0].delta.content // empty'
    else
        printf '%s' "$body" | curl "${curl_opts[@]}" --no-buffer \
            --header "Accept: text/event-stream" "$url" \
        | python3 -c '
import json, sys
for line in sys.stdin:
    line = line.strip()
    if not line.startswith("data:"):
        continue
    payload = line[5:].strip()
    if payload == "[DONE]":
        break
    try:
        chunk = json.loads(payload)
    except ValueError:
        continue
    for choice in chunk.get("choices", []):
        piece = (choice.get("delta") or {}).get("content")
        if piece:
            sys.stdout.write(piece)
            sys.stdout.flush()
'
    fi
    printf '\n'
    exit 0
fi

# --- non-streaming path -----------------------------------------------------
start_ms="$(now_ms)"
# Append the HTTP status on its own trailing line so it can be split off.
resp="$(printf '%s' "$body" | curl "${curl_opts[@]}" --write-out $'\n%{http_code}' "$url")" || {
    die "curl failed (exit $?) for $url"
}
elapsed_ms=$(( $(now_ms) - start_ms ))

code="${resp##*$'\n'}"
payload="${resp%$'\n'*}"

if [[ ! "$code" =~ ^2 ]]; then
    printf 'HTTP %s from %s\n%s\n' "$code" "$url" "$payload" >&2
    exit 1
fi

if $RAW; then
    printf '%s\n' "$payload"
    exit 0
fi

if $HAVE_JQ; then
    content="$(printf '%s' "$payload" | jq -er '.choices[0].message.content' 2>/dev/null)" || {
        printf 'Unexpected response body:\n%s\n' "$payload" >&2; exit 1; }
    printf '%s\n' "$content"
    if $VERBOSE; then
        printf '%s' "$payload" | jq -r --argjson ms "$elapsed_ms" '
            "prompt=\(.usage.prompt_tokens // "?") " +
            "completion=\(.usage.completion_tokens // "?") " +
            "total=\(.usage.total_tokens // "?") | " +
            "\(($ms / 10 | round) / 100)s | " +
            "\(if (.usage.completion_tokens // 0) > 0 and $ms > 0
               then ((.usage.completion_tokens / ($ms / 1000)) * 10 | round / 10 | tostring)
               else "?" end) tok/s | " +
            "finish=\(.choices[0].finish_reason // "?")"' >&2
    fi
else
    RESP_JSON="$payload" ELAPSED_MS="$elapsed_ms" VERBOSE="$VERBOSE" \
    python3 -c '
import json, os, sys
try:
    data = json.loads(os.environ["RESP_JSON"])
    print(data["choices"][0]["message"]["content"])
except (ValueError, KeyError, IndexError):
    sys.stderr.write("Unexpected response body:\n" + os.environ["RESP_JSON"] + "\n")
    sys.exit(1)
if os.environ["VERBOSE"] == "true":
    u = data.get("usage") or {}
    ms = int(os.environ["ELAPSED_MS"]) or 1
    ct = u.get("completion_tokens") or 0
    sys.stderr.write(
        "prompt=%s completion=%s total=%s | %.2fs | %.1f tok/s | finish=%s\n" % (
            u.get("prompt_tokens", "?"), u.get("completion_tokens", "?"),
            u.get("total_tokens", "?"), ms / 1000.0, ct / (ms / 1000.0),
            (data.get("choices") or [{}])[0].get("finish_reason", "?")))
'
fi
