#!/usr/bin/env bash
# Discover what an OpenAI-compatible endpoint actually serves: list /v1/models,
# filter it, assert a model is present, and optionally probe each one with a
# one-token request to see which are really usable.
#
#   ./llm-models.sh                                  # ids, one per line
#   ./llm-models.sh -l                               # id, owner, created, context
#   ./llm-models.sh qwen                             # filter (case-insensitive)
#   ./llm-models.sh --has Qwen/Qwen2.5-7B-Instruct   # exit 0 only if served
#   ./llm-models.sh --probe                          # which ones actually answer
#
# Requires: curl, and one of jq (preferred) or python3 for JSON handling.
# Portable across GNU/Linux, macOS and WSL - no GNU-only flags.

set -euo pipefail

ENDPOINT="${LLM_ENDPOINT:-}"
API_KEY="${LLM_API_KEY:-}"
PATTERN=""
LONG=false
JSON=false
PROBE=false
HAS=""
TIMEOUT=60
INSECURE=false
VERBOSE=false

usage() {
    cat <<'EOF'
Usage: llm-models.sh [options] [pattern]

  pattern                Case-insensitive substring filter on the model id

  -e, --endpoint URL     Base URL, .../v1 or full .../v1/models
                         (env: LLM_ENDPOINT)
  -k, --api-key KEY      Bearer token (env: LLM_API_KEY)
  -l, --long             Table: id, owned_by, created, context length
      --json             Print the raw JSON response
      --has MODEL        Exit 0 only if MODEL is served exactly (quiet, like grep -q)
      --probe            Send a 1-token chat request to every listed model and
                         report which ones answer. Exits 1 if any fail
      --timeout N        Request timeout in seconds, default 60
  -i, --insecure         Skip TLS verification (self-signed endpoints)
  -v, --verbose          Print the request URL to stderr
  -h, --help             This text
EOF
}

die() { printf '%s\n' "$*" >&2; exit 1; }

now_ms() {
    if [[ -n "${EPOCHREALTIME:-}" ]]; then
        local t="${EPOCHREALTIME/,/.}"
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
        -e|--endpoint) ENDPOINT="$2"; shift 2 ;;
        -k|--api-key)  API_KEY="$2"; shift 2 ;;
        -l|--long)     LONG=true; shift ;;
        --json)        JSON=true; shift ;;
        --has)         HAS="$2"; shift 2 ;;
        --probe)       PROBE=true; shift ;;
        --timeout)     TIMEOUT="$2"; shift 2 ;;
        -i|--insecure) INSECURE=true; shift ;;
        -v|--verbose)  VERBOSE=true; shift ;;
        -h|--help)     usage; exit 0 ;;
        --)            shift; PATTERN="${1:-}"; break ;;
        -*)            die "Unknown option: $1" ;;
        *)             PATTERN="$1"; shift ;;
    esac
done

command -v curl >/dev/null 2>&1 || die "curl not found (apt install curl)"
[[ -n "$ENDPOINT" ]] || die "endpoint required (-e or \$LLM_ENDPOINT)"
[[ -n "$API_KEY"  ]] || die "api key required (-k or \$LLM_API_KEY)"

HAVE_JQ=false
command -v jq >/dev/null 2>&1 && HAVE_JQ=true
if ! $HAVE_JQ && ! command -v python3 >/dev/null 2>&1; then
    die "need jq or python3 for JSON handling (apt install jq)"
fi

# --- endpoint normalization -------------------------------------------------
base="${ENDPOINT%/}"
case "$base" in
    */models)           models_url="$base"; base="${base%/models}" ;;
    */v1)               models_url="$base/models" ;;
    */chat/completions) base="${base%/chat/completions}"; models_url="$base/models" ;;
    *)                  base="$base/v1"; models_url="$base/models" ;;
esac
chat_url="$base/chat/completions"

curl_common=(
    --silent --show-error
    --max-time "$TIMEOUT"
    --header "Authorization: Bearer ${API_KEY}"
    --header "Accept: application/json"
)
$INSECURE && curl_common+=(--insecure)

$VERBOSE && printf 'GET %s\n' "$models_url" >&2

# --- fetch ------------------------------------------------------------------
resp="$(curl "${curl_common[@]}" --write-out $'\n%{http_code}' "$models_url")" \
    || die "curl failed (exit $?) for $models_url"
code="${resp##*$'\n'}"
payload="${resp%$'\n'*}"

if [[ ! "$code" =~ ^2 ]]; then
    printf 'HTTP %s from %s\n%s\n' "$code" "$models_url" "$payload" >&2
    exit 1
fi

if $JSON; then
    printf '%s\n' "$payload"
    exit 0
fi

# --- parse into id \t owner \t created \t context ---------------------------
parse_models() {
    if $HAVE_JQ; then
        printf '%s' "$payload" | jq -r '
            .data[]? | [
                .id,
                (.owned_by // "-"),
                (if (.created // 0) > 0 then (.created | todate) else "-" end),
                ((.max_model_len // .context_length // .max_input_tokens // "-") | tostring)
            ] | @tsv'
    else
        RESP_JSON="$payload" python3 -c '
import datetime, json, os, sys
try:
    data = json.loads(os.environ["RESP_JSON"])
except ValueError:
    sys.stderr.write("non-JSON response:\n" + os.environ["RESP_JSON"] + "\n")
    sys.exit(1)
for m in data.get("data") or []:
    created = m.get("created") or 0
    iso = (datetime.datetime.fromtimestamp(created, datetime.timezone.utc)
           .strftime("%Y-%m-%dT%H:%M:%SZ")) if created else "-"
    ctx = (m.get("max_model_len") or m.get("context_length")
           or m.get("max_input_tokens") or "-")
    print("\t".join([str(m.get("id", "-")), str(m.get("owned_by") or "-"), iso, str(ctx)]))
'
    fi
}

rows="$(parse_models)" || exit 1
if [[ -z "$rows" ]]; then
    printf 'no models in response from %s\n%s\n' "$models_url" "$payload" >&2
    exit 1
fi

if [[ -n "$PATTERN" ]]; then
    rows="$(printf '%s\n' "$rows" | awk -F'\t' -v pat="$PATTERN" '
        BEGIN { pat = tolower(pat) }
        index(tolower($1), pat) > 0')"
fi

# --- --has ------------------------------------------------------------------
if [[ -n "$HAS" ]]; then
    if printf '%s\n' "$rows" | awk -F'\t' -v want="$HAS" '$1 == want { found = 1 }
                                                          END { exit found ? 0 : 1 }'; then
        exit 0
    fi
    printf "model '%s' is not served by %s\n" "$HAS" "$models_url" >&2
    exit 1
fi

if [[ -z "$rows" ]]; then
    printf 'no model matches %s\n' "$PATTERN" >&2
    exit 1
fi

# --- --probe ----------------------------------------------------------------
if $PROBE; then
    probe_body() {
        if $HAVE_JQ; then
            jq -nc --arg model "$1" \
                '{model:$model, messages:[{role:"user",content:"ping"}],
                  max_tokens:1, temperature:0}'
        else
            PROBE_MODEL="$1" python3 -c '
import json, os
print(json.dumps({"model": os.environ["PROBE_MODEL"],
                  "messages": [{"role": "user", "content": "ping"}],
                  "max_tokens": 1, "temperature": 0}))'
        fi
    }
    error_message() {
        if $HAVE_JQ; then
            printf '%s' "$1" | jq -r '(.error.message // .message // "") | tostring' 2>/dev/null
        else
            ERR_JSON="$1" python3 -c '
import json, os
try:
    d = json.loads(os.environ["ERR_JSON"])
except ValueError:
    print(""); raise SystemExit
e = d.get("error")
print((e.get("message") if isinstance(e, dict) else e) or d.get("message") or "")'
        fi
    }

    width=$(printf '%s\n' "$rows" | awk -F'\t' '{ if (length($1) > w) w = length($1) } END { print (w < 5 ? 5 : w) }')
    printf '%-*s  %-6s  %9s  %s\n' "$width" "MODEL" "STATUS" "LATENCY" "NOTE"
    failed=0
    total=0
    while IFS=$'\t' read -r id _owner _created _ctx; do
        [[ -n "$id" ]] || continue
        total=$(( total + 1 ))
        body="$(probe_body "$id")"
        start="$(now_ms)"
        if presp="$(printf '%s' "$body" | curl "${curl_common[@]}" \
                        --header "Content-Type: application/json" --data-binary @- \
                        --write-out $'\n%{http_code}' "$chat_url")"; then
            ms=$(( $(now_ms) - start ))
            pcode="${presp##*$'\n'}"
            pbody="${presp%$'\n'*}"
            if [[ "$pcode" =~ ^2 ]]; then
                printf '%-*s  %-6s  %7sms\n' "$width" "$id" "ok" "$ms"
            else
                failed=$(( failed + 1 ))
                printf '%-*s  %-6s  %7sms  %s\n' "$width" "$id" "$pcode" "$ms" \
                    "$(error_message "$pbody")"
            fi
        else
            failed=$(( failed + 1 ))
            printf '%-*s  %-6s  %9s  %s\n' "$width" "$id" "-" "-" "connection failed"
        fi
    done <<EOF
$rows
EOF
    printf '\n%d/%d models answered\n' "$(( total - failed ))" "$total"
    [[ $failed -eq 0 ]] || exit 1
    exit 0
fi

# --- list -------------------------------------------------------------------
if $LONG; then
    printf '%s\n' "$rows" | awk -F'\t' '
        { id[NR] = $1; own[NR] = $2; cre[NR] = $3; ctx[NR] = $4
          if (length($1) > w1) w1 = length($1)
          if (length($2) > w2) w2 = length($2) }
        END {
            if (w1 < 5) w1 = 5
            if (w2 < 5) w2 = 5
            printf "%-*s  %-*s  %-20s  %s\n", w1, "MODEL", w2, "OWNER", "CREATED", "CONTEXT"
            for (i = 1; i <= NR; i++)
                printf "%-*s  %-*s  %-20s  %s\n", w1, id[i], w2, own[i], cre[i], ctx[i]
            printf "\n%d model(s)\n", NR
        }'
else
    printf '%s\n' "$rows" | awk -F'\t' '{ print $1 }'
fi
