#!/usr/bin/env bash
# Tek komutla endpoint saglik kontrolu.
#
#   ./llm-check.sh            # BASIT: erisim, auth, model, chat, UTF-8, streaming
#   ./llm-check.sh --full     # GELISMIS: + model yoklama, embeddings paketi, yuk testi
#   ./llm-check.sh -q         # yalnizca sonuc satiri (cron / CI icin)
#
# Gerekenler: curl ve JSON icin jq (tercih edilir) ya da python3.
# --full modu ayni klasordeki llm-models.sh, ../python/embed-test.py ve
# ../python/chat-loadtest.py betiklerini kullanir; bulunmayanlar atlanir.

set -uo pipefail

ENDPOINT="${LLM_ENDPOINT:-}"
API_KEY="${LLM_API_KEY:-}"
MODEL="${LLM_MODEL:-}"
EMBED_MODEL="${LLM_EMBED_MODEL:-}"
RERANK_MODEL="${LLM_RERANK_MODEL:-}"
FULL=false
QUIET=false
TIMEOUT=60
INSECURE=false

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROBE_PROMPT="Şu kelimeyi aynen tekrar et: çğışöü"

usage() {
    cat <<'EOF'
Kullanım: llm-check.sh [seçenekler]

Endpoint'in çalışıp çalışmadığını tek komutla söyler.

  -e, --endpoint URL     Temel URL, .../v1 (env: LLM_ENDPOINT)
  -k, --api-key KEY      Bearer token (env: LLM_API_KEY)
  -m, --model AD         Model adı (env: LLM_MODEL)
      --embed-model AD   Embedding modeli (env: LLM_EMBED_MODEL), --full için
      --rerank-model AD  Reranker modeli (env: LLM_RERANK_MODEL), --full için
      --full             Gelişmiş kontroller: model yoklama, embeddings ve rerank
                         sağlık paketleri ve kısa bir yük testi de çalıştırılır
      --timeout N        İstek zaman aşımı (saniye), varsayılan 60
  -i, --insecure         TLS doğrulamasını atla (self-signed endpoint)
  -q, --quiet            Yalnızca son satırı yazdır
  -h, --help             Bu metin

Exit: tüm kontroller geçtiyse 0, en az bir FAIL varsa 1. UYARI exit kodunu
değiştirmez.
EOF
}

die() { printf '%s\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        -e|--endpoint)    ENDPOINT="$2"; shift 2 ;;
        -k|--api-key)     API_KEY="$2"; shift 2 ;;
        -m|--model)       MODEL="$2"; shift 2 ;;
        --embed-model)    EMBED_MODEL="$2"; shift 2 ;;
        --rerank-model)   RERANK_MODEL="$2"; shift 2 ;;
        --full)           FULL=true; shift ;;
        --timeout)        TIMEOUT="$2"; shift 2 ;;
        -i|--insecure)    INSECURE=true; shift ;;
        -q|--quiet)       QUIET=true; shift ;;
        -h|--help)        usage; exit 0 ;;
        *)                die "Bilinmeyen seçenek: $1" ;;
    esac
done

command -v curl >/dev/null 2>&1 || die "curl bulunamadı (apt install curl)"
[[ -n "$ENDPOINT" ]] || die "endpoint gerekli (-e ya da \$LLM_ENDPOINT)"
[[ -n "$API_KEY"  ]] || die "api key gerekli (-k ya da \$LLM_API_KEY)"
[[ -n "$MODEL"    ]] || die "model gerekli (-m ya da \$LLM_MODEL)"

HAVE_JQ=false
command -v jq >/dev/null 2>&1 && HAVE_JQ=true
if ! $HAVE_JQ && ! command -v python3 >/dev/null 2>&1; then
    die "JSON için jq ya da python3 gerekli (apt install jq)"
fi

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

# --- endpoint normalizasyonu ------------------------------------------------
base="${ENDPOINT%/}"
case "$base" in
    */chat/completions) base="${base%/chat/completions}" ;;
    */models)           base="${base%/models}" ;;
    */v1)               : ;;
    *)                  base="$base/v1" ;;
esac

curl_common=(--silent --show-error --max-time "$TIMEOUT"
             --header "Authorization: Bearer ${API_KEY}")
$INSECURE && curl_common+=(--insecure)

# --- rapor ------------------------------------------------------------------
FAILED=0
WARNED=0
PASSED=0
# printf '%-16s' ve ${#s} bayt sayar; Türkçe karakterler çok baytlı olduğu için
# sütunlar kayıyordu. UTF-8 devam baytlarını (0x80-0xBF) atarak gerçek karakter
# sayısını buluyoruz - locale'den bağımsız çalışır.
karakter_sayisi() {
    printf '%s' "$1" | LC_ALL=C tr -d '\200-\277' | wc -c | tr -d ' '
}

dolgu() {   # $1=metin $2=genislik
    local i
    printf '%s' "$1"
    i="$(karakter_sayisi "$1")"
    while [ "$i" -lt "$2" ]; do printf ' '; i=$(( i + 1 )); done
}

satir() {   # $1=durum $2=ad $3=detay
    case "$1" in
        PASS) PASSED=$(( PASSED + 1 )) ;;
        FAIL) FAILED=$(( FAILED + 1 )) ;;
        UYARI) WARNED=$(( WARNED + 1 )) ;;
    esac
    $QUIET || { dolgu "$1" 6; dolgu "$2" 18; printf '%s\n' "$3"; }
}

json_field() {   # $1=JSON $2=jq ifadesi $3=python ifadesi
    if $HAVE_JQ; then
        printf '%s' "$1" | jq -r "$2" 2>/dev/null
    else
        RESP_JSON="$1" python3 -c "
import json, os, sys
try:
    d = json.loads(os.environ['RESP_JSON'])
except ValueError:
    print(''); sys.exit()
$3" 2>/dev/null
    fi
}

hata_mesaji() {
    json_field "$1" '(.error.message // .message // "") | tostring' \
        "e = d.get('error');
print((e.get('message') if isinstance(e, dict) else e) or d.get('message') or '')"
}

$QUIET || {
    printf 'Endpoint  %s\n' "$base"
    printf 'Model     %s\n\n' "$MODEL"
}

baslangic="$(now_ms)"

# --- 1/2/3: erişim, kimlik doğrulama, model listede mi ----------------------
models_resp="$(curl "${curl_common[@]}" --header "Accept: application/json" \
                    --write-out $'\n%{http_code}' "$base/models" 2>/dev/null)"
models_code="${models_resp##*$'\n'}"
models_body="${models_resp%$'\n'*}"
[[ "$models_code" =~ ^[0-9]+$ ]] || models_code="000"

model_listesi=""
case "$models_code" in
    2*)
        model_listesi="$(json_field "$models_body" '[.data[]?.id] | join("\n")' \
            "print('\n'.join(str(m.get('id','')) for m in (d.get('data') or [])))")"
        adet="$(printf '%s' "$model_listesi" | grep -c . || true)"
        satir PASS "erişim" "HTTP 200 · $adet model listeleniyor"
        satir PASS "kimlik doğrulama" "bearer token kabul edildi"
        ;;
    401|403)
        satir FAIL "erişim" "HTTP $models_code"
        satir FAIL "kimlik doğrulama" "$(hata_mesaji "$models_body")"
        ;;
    404)
        satir UYARI "erişim" "/v1/models yok (tek modelli sunucu olabilir)"
        satir UYARI "kimlik doğrulama" "chat isteğinden anlaşılacak"
        ;;
    000)
        satir FAIL "erişim" "bağlantı kurulamadı: $base"
        $QUIET || printf '\n'
        printf 'Sonuç: endpoint erişilemiyor · %s\n' "$base"
        exit 1
        ;;
    *)
        satir UYARI "erişim" "HTTP $models_code · $(hata_mesaji "$models_body")"
        ;;
esac

if [[ -n "$model_listesi" ]]; then
    if printf '%s\n' "$model_listesi" | grep -Fxq -- "$MODEL"; then
        satir PASS "model" "listede var"
    else
        satir FAIL "model" "'$MODEL' listede yok"
    fi
else
    satir UYARI "model" "liste alınamadı, chat isteğiyle denenecek"
fi

# --- 4/5: chat yanıtı ve UTF-8 ----------------------------------------------
istek_govdesi() {   # $1=stream (true/false)
    if $HAVE_JQ; then
        jq -nc --arg model "$MODEL" --arg prompt "$PROBE_PROMPT" --argjson stream "$1" \
            '{model:$model, messages:[{role:"user",content:$prompt}],
              max_tokens:32, temperature:0, stream:$stream}'
    else
        M="$MODEL" P="$PROBE_PROMPT" S="$1" python3 -c '
import json, os
print(json.dumps({"model": os.environ["M"],
                  "messages": [{"role": "user", "content": os.environ["P"]}],
                  "max_tokens": 32, "temperature": 0,
                  "stream": os.environ["S"] == "true"}))'
    fi
}

chat_resp="$(istek_govdesi false | curl "${curl_common[@]}" \
    --header "Content-Type: application/json" --header "Accept: application/json" \
    --data-binary @- --write-out $'\n%{http_code}' "$base/chat/completions" 2>/dev/null)"
chat_code="${chat_resp##*$'\n'}"
chat_body="${chat_resp%$'\n'*}"
[[ "$chat_code" =~ ^[0-9]+$ ]] || chat_code="000"

if [[ "$chat_code" =~ ^2 ]]; then
    ozet="$(json_field "$chat_body" \
        '[(.choices[0].message.content // ""), (.choices[0].finish_reason // "?"), ((.usage.completion_tokens // 0) | tostring)] | @tsv' \
        "c = (d.get('choices') or [{}])[0]
m = (c.get('message') or {}).get('content') or ''
u = d.get('usage') or {}
print('\t'.join([m.replace('\t',' ').replace('\n',' '), str(c.get('finish_reason') or '?'), str(u.get('completion_tokens') or 0)]))")"
    icerik="${ozet%%$'\t'*}"
    kalan="${ozet#*$'\t'}"
    finish="${kalan%%$'\t'*}"
    tokenlar="${kalan##*$'\t'}"

    if [[ -n "$icerik" ]]; then
        satir PASS "chat" "yanıt geldi · ${tokenlar} token · finish=${finish}"
    else
        satir FAIL "chat" "HTTP 200 ama içerik boş"
    fi

    if [[ "$icerik" == *"�"* ]]; then
        satir FAIL "UTF-8" "yanıtta bozuk karakter (U+FFFD) var"
    elif [[ -n "$icerik" ]]; then
        onizleme="$(printf '%s' "$icerik" | cut -c1-42)"
        satir PASS "UTF-8" "geçerli · \"${onizleme}\""
    else
        satir UYARI "UTF-8" "içerik boş olduğu için kontrol edilemedi"
    fi
else
    satir FAIL "chat" "HTTP $chat_code · $(hata_mesaji "$chat_body")"
    satir UYARI "UTF-8" "chat başarısız olduğu için kontrol edilemedi"
fi

# --- 6: streaming -----------------------------------------------------------
stream_basla="$(now_ms)"
stream_cikti="$(istek_govdesi true | curl "${curl_common[@]}" --no-buffer \
    --header "Content-Type: application/json" --header "Accept: text/event-stream" \
    --data-binary @- "$base/chat/completions" 2>/dev/null \
    | awk 'substr($0,1,6) == "data: " { p = substr($0,7); if (p == "[DONE]") exit; print p; fflush() }' \
    | head -c 200000)"
stream_sure=$(( $(now_ms) - stream_basla ))

if [[ -n "$stream_cikti" ]]; then
    chunk_adet="$(printf '%s\n' "$stream_cikti" | grep -c '"delta"' || true)"
    if [[ "${chunk_adet:-0}" -gt 0 ]]; then
        satir PASS "streaming" "${chunk_adet} chunk · ${stream_sure}ms"
    else
        satir UYARI "streaming" "SSE geldi ama delta yok"
    fi
elif [[ "$chat_code" =~ ^2 ]]; then
    satir UYARI "streaming" "sunucu stream isteğini yok saymış olabilir"
else
    satir FAIL "streaming" "yanıt alınamadı"
fi

# --- gelişmiş kontroller ----------------------------------------------------
if $FULL; then
    $QUIET || printf '\n'

    models_betik="$SCRIPT_DIR/llm-models.sh"
    if [[ -x "$models_betik" || -f "$models_betik" ]]; then
        probe_cikti="$(LLM_ENDPOINT="$base" LLM_API_KEY="$API_KEY" \
            bash "$models_betik" --probe 2>/dev/null | tail -1)"
        if [[ "$probe_cikti" == *"model cevap verdi"* ]]; then
            oran="${probe_cikti%% *}"
            if [[ "${oran%%/*}" == "${oran##*/}" ]]; then
                satir PASS "model yoklama" "$probe_cikti"
            else
                satir UYARI "model yoklama" "$probe_cikti (detay: llm-models.sh --probe)"
            fi
        else
            satir UYARI "model yoklama" "çalıştırılamadı"
        fi
    else
        satir UYARI "model yoklama" "llm-models.sh bulunamadı"
    fi

    embed_betik="$SCRIPT_DIR/../python/embed-test.py"
    if [[ -z "$EMBED_MODEL" ]]; then
        satir UYARI "embeddings" "LLM_EMBED_MODEL tanımlı değil, atlandı"
    elif ! command -v python3 >/dev/null 2>&1; then
        satir UYARI "embeddings" "python3 yok, atlandı"
    elif [[ ! -f "$embed_betik" ]]; then
        satir UYARI "embeddings" "embed-test.py bulunamadı"
    else
        embed_cikti="$(LLM_ENDPOINT="$base" LLM_API_KEY="$API_KEY" LLM_EMBED_MODEL="$EMBED_MODEL" \
            python3 "$embed_betik" --suite 2>&1 | tail -1)"
        if [[ "$embed_cikti" == *"geçti"* && "$embed_cikti" != *"0/"* ]]; then
            gecen="${embed_cikti%% *}"
            if [[ "${gecen%%/*}" == "${gecen##*/}" ]]; then
                satir PASS "embeddings" "$embed_cikti"
            else
                satir FAIL "embeddings" "$embed_cikti (detay: embed-test.py --suite)"
            fi
        else
            satir FAIL "embeddings" "sağlık paketi çalışmadı"
        fi
    fi

    rerank_betik="$SCRIPT_DIR/../python/rerank-test.py"
    if [[ -z "$RERANK_MODEL" ]]; then
        satir UYARI "rerank" "LLM_RERANK_MODEL tanımlı değil, atlandı"
    elif ! command -v python3 >/dev/null 2>&1; then
        satir UYARI "rerank" "python3 yok, atlandı"
    elif [[ ! -f "$rerank_betik" ]]; then
        satir UYARI "rerank" "rerank-test.py bulunamadı"
    else
        rerank_cikti="$(LLM_ENDPOINT="$base" LLM_API_KEY="$API_KEY" LLM_RERANK_MODEL="$RERANK_MODEL" \
            python3 "$rerank_betik" --suite 2>&1 | tail -1)"
        if [[ "$rerank_cikti" == *"geçti"* ]]; then
            gecen_r="${rerank_cikti%% *}"
            if [[ "${gecen_r%%/*}" == "${gecen_r##*/}" ]]; then
                satir PASS "rerank" "$rerank_cikti"
            else
                satir FAIL "rerank" "$rerank_cikti (detay: rerank-test.py --suite)"
            fi
        else
            satir FAIL "rerank" "sağlık paketi çalışmadı"
        fi
    fi

    yuk_betik="$SCRIPT_DIR/../python/chat-loadtest.py"
    if ! command -v python3 >/dev/null 2>&1; then
        satir UYARI "yük" "python3 yok, atlandı"
    elif [[ ! -f "$yuk_betik" ]]; then
        satir UYARI "yük" "chat-loadtest.py bulunamadı"
    else
        yuk_json="$(LLM_ENDPOINT="$base" LLM_API_KEY="$API_KEY" LLM_MODEL="$MODEL" \
            python3 "$yuk_betik" -n 10 -c 2 --max-tokens 32 --json 2>/dev/null)"
        yuk_ozet="$(json_field "$yuk_json" \
            '"\(.istek_basarili)/\(.istek_toplam) istek · TTFT p95 \(.ttft_ms.p95 // 0 | round)ms · \(.cikti_token_per_s | round) token/s"' \
            "t = d.get('ttft_ms') or {}
print('%s/%s istek · TTFT p95 %.0fms · %.0f token/s' % (d['istek_basarili'], d['istek_toplam'], t.get('p95', 0), d['cikti_token_per_s']))")"
        if [[ -n "$yuk_ozet" && "$yuk_ozet" != "null" ]]; then
            hatali="$(json_field "$yuk_json" '.istek_hatali' "print(d['istek_hatali'])")"
            if [[ "${hatali:-1}" == "0" ]]; then
                satir PASS "yük" "$yuk_ozet"
            else
                satir FAIL "yük" "$yuk_ozet"
            fi
        else
            satir FAIL "yük" "yük testi çalışmadı"
        fi
    fi
fi

# --- sonuç ------------------------------------------------------------------
sure=$(( $(now_ms) - baslangic ))
toplam=$(( PASSED + FAILED + WARNED ))
$QUIET || printf '\n'
if [[ $FAILED -gt 0 ]]; then
    printf 'Sonuç: %d/%d geçti · %d hata · %d uyarı · %s (%.1fs)\n' \
        "$PASSED" "$toplam" "$FAILED" "$WARNED" "endpoint SAĞLIKSIZ" \
        "$(awk "BEGIN{print $sure/1000}")"
    exit 1
fi
printf 'Sonuç: %d/%d geçti · %d uyarı · %s (%.1fs)\n' \
    "$PASSED" "$toplam" "$WARNED" "endpoint sağlıklı" "$(awk "BEGIN{print $sure/1000}")"
exit 0
