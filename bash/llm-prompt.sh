#!/usr/bin/env bash
# OpenAI uyumlu bir /v1/chat/completions endpoint'ine tek prompt gonderir
# (vLLM, llama.cpp server, TGI OpenAI shim, Ollama, OpenAI, gateway'ler).
#
#   ./llm-prompt.sh -e http://10.0.0.10:8000 -k sk-xxx -m Qwen/Qwen2.5-7B-Instruct "Merhaba"
#   LLM_ENDPOINT=... LLM_API_KEY=... LLM_MODEL=... ./llm-prompt.sh --stream "2+2 kac?"
#
# Gerekenler: curl ve JSON icin jq (tercih edilir) ya da python3.
# GNU/Linux, macOS ve WSL uzerinde calisir - GNU'ya ozel parametre kullanmaz.

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
Kullanım: llm-prompt.sh [seçenekler] "prompt"

  -e, --endpoint URL     Temel URL, .../v1 ya da tam .../v1/chat/completions
                         (env: LLM_ENDPOINT)
  -k, --api-key KEY      Bearer token (env: LLM_API_KEY)
  -m, --model AD         Model adı (env: LLM_MODEL)
  -s, --system METİN     System prompt
  -t, --temperature N    Varsayılan 0.0
  -n, --max-tokens N     Varsayılan 512
      --timeout N        Toplam istek zaman aşımı (saniye), varsayılan 300
      --stream           Token'ları geldikçe yazdır (SSE)
      --raw              Tam JSON yanıtını yazdır
  -i, --insecure         TLS doğrulamasını atla (self-signed endpoint)
  -v, --verbose          Token kullanımı, gecikme ve tok/s bilgisini stderr'e yaz
  -h, --help             Bu metin

Prompt pipe ile de verilebilir:  echo "..." | llm-prompt.sh -m foo
EOF
}

die() { printf '%s\n' "$*" >&2; exit 1; }

# Epoch'tan beri gecen milisaniye. GNU date %N anlar, BSD/macOS date anlamaz;
# once bash 5'in $EPOCHREALTIME'i, sonra python3, en sonda tam saniye kullanilir.
now_ms() {
    if [[ -n "${EPOCHREALTIME:-}" ]]; then
        local t="${EPOCHREALTIME/,/.}"   # bazi locale'ler virgul kullanir
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
        -*)               die "Bilinmeyen seçenek: $1" ;;
        *)                USER_PROMPT="$1"; shift ;;
    esac
done

# Parametre verilmediyse ve stdin bir tty degilse prompt'u stdin'den al
if [[ -z "$USER_PROMPT" && ! -t 0 ]]; then
    USER_PROMPT="$(cat)"
fi

command -v curl >/dev/null 2>&1 || die "curl bulunamadı (apt install curl)"
[[ -n "$ENDPOINT"    ]] || die "endpoint gerekli (-e ya da \$LLM_ENDPOINT)"
[[ -n "$API_KEY"     ]] || die "api key gerekli (-k ya da \$LLM_API_KEY)"
[[ -n "$MODEL"       ]] || die "model gerekli (-m ya da \$LLM_MODEL)"
[[ -n "$USER_PROMPT" ]] || die "prompt gerekli (parametre ya da stdin)"

HAVE_JQ=false
command -v jq >/dev/null 2>&1 && HAVE_JQ=true
if ! $HAVE_JQ && ! command -v python3 >/dev/null 2>&1; then
    die "JSON için jq ya da python3 gerekli (apt install jq)"
fi

# --- endpoint normalizasyonu ------------------------------------------------
url="${ENDPOINT%/}"
case "$url" in
    */chat/completions) : ;;
    */v1)               url="$url/chat/completions" ;;
    *)                  url="$url/v1/chat/completions" ;;
esac

# --- istek govdesi ----------------------------------------------------------
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

# --- streaming yolu ---------------------------------------------------------
# "grep --line-buffered | sed -u" yerine awk: bu GNU parametreleri macOS/BSD'de
# yok, awk ile pipeline orada da satir satir akiyor.
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

# --- streaming olmayan yol --------------------------------------------------
start_ms="$(now_ms)"
# HTTP status'u en sona ayri bir satir olarak ekle, sonra ayirip okuyalim.
resp="$(printf '%s' "$body" | curl "${curl_opts[@]}" --write-out $'\n%{http_code}' "$url")" || {
    die "curl başarısız (exit $?): $url"
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
        printf 'Beklenmeyen yanıt gövdesi:\n%s\n' "$payload" >&2; exit 1; }
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
    sys.stderr.write("Beklenmeyen yanıt gövdesi:\n" + os.environ["RESP_JSON"] + "\n")
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
