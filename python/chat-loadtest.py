#!/usr/bin/env python3

"""
OpenAI uyumlu bir /v1/chat/completions endpoint'ine yük uygular ve TTFT
(time to first token), ITL (inter-token latency), uçtan uca gecikme ve
throughput ölçer. Sadece standart kütüphane - kurulum gerektirmez.

Linux, macOS ve Windows (PowerShell) üzerinde aynı şekilde çalışır:
python3 / py -3.

Örnekler:
  ./chat-loadtest.py -n 50 -c 8
  ./chat-loadtest.py --duration 60 -c 16 --max-tokens 256
  ./chat-loadtest.py -n 100 -c 8 --max-ttft-p95 800     # SLO kapısı
  ./chat-loadtest.py -n 20 --csv sonuc.csv --json
"""

import argparse
import csv
import json
import math
import os
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request

# Windows konsolu varsayılan olarak cp1252 kullanır ve Türkçe karakterlerde
# UnicodeEncodeError verir. Çıktı akışlarını UTF-8'e sabitliyoruz.
for _akis in (sys.stdout, sys.stderr):
    if hasattr(_akis, "reconfigure"):
        _akis.reconfigure(encoding="utf-8", errors="replace")

VARSAYILAN_PROMPT = (
    "Yapay zeka servislerinde KV cache neden kullanilir? "
    "Kisa ve teknik bir sekilde acikla."
)


# --------------------------------------------------------------------------
# yardimcilar
# --------------------------------------------------------------------------

def resolve_url(base):
    u = base.rstrip("/")
    if u.endswith("/chat/completions"):
        return u
    if u.endswith("/v1"):
        return u + "/chat/completions"
    return u + "/v1/chat/completions"


def percentile(sorted_vals, p):
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return sorted_vals[int(k)]
    return sorted_vals[lo] * (hi - k) + sorted_vals[hi] * (k - lo)


class Sonuc(object):
    """Tek bir istegin olcumleri. ttft/itl saniye cinsinden tutulur."""

    def __init__(self, ok, status=None, hata=None, ttft=None, e2e=0.0,
                 gaps=None, tokens=0):
        self.ok = ok
        self.status = status
        self.hata = hata
        self.ttft = ttft
        self.e2e = e2e
        self.gaps = gaps or []
        self.tokens = tokens


# --------------------------------------------------------------------------
# istemci
# --------------------------------------------------------------------------

class ChatClient(object):
    def __init__(self, url, api_key, model, prompt, max_tokens, temperature,
                 stream, stream_usage, timeout, insecure, verbose):
        self.url = url
        self.api_key = api_key
        self.model = model
        self.prompt = prompt
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.stream = stream
        self.stream_usage = stream_usage
        self.timeout = timeout
        self.verbose = verbose
        self.ctx = None
        if insecure:
            self.ctx = ssl.create_default_context()
            self.ctx.check_hostname = False
            self.ctx.verify_mode = ssl.CERT_NONE

    def _request(self):
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": self.prompt}],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": self.stream,
        }
        if self.stream and self.stream_usage:
            payload["stream_options"] = {"include_usage": True}
        headers = {
            "Authorization": "Bearer %s" % self.api_key,
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if self.stream else "application/json",
        }
        return urllib.request.Request(
            self.url, data=json.dumps(payload).encode("utf-8"),
            method="POST", headers=headers)

    def cagir(self):
        req = self._request()
        t0 = time.perf_counter()
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx)
        except urllib.error.HTTPError as e:
            govde = e.read().decode("utf-8", "replace")
            return Sonuc(False, status=e.code, hata=kisalt(api_mesaji(govde)),
                         e2e=time.perf_counter() - t0)
        except Exception as e:                       # URLError, socket.timeout, ...
            return Sonuc(False, hata=kisalt(str(getattr(e, "reason", e))),
                         e2e=time.perf_counter() - t0)

        try:
            if self.stream:
                return self._oku_stream(resp, t0)
            return self._oku_blok(resp, t0)
        except Exception as e:
            return Sonuc(False, status=200, hata=kisalt("yanit okunamadi: %s" % e),
                         e2e=time.perf_counter() - t0)
        finally:
            resp.close()

    def _oku_stream(self, resp, t0):
        ttft = None
        zamanlar = []
        usage_tokens = None
        for ham in resp:
            satir = ham.decode("utf-8", "replace").strip()
            if not satir.startswith("data:"):
                continue
            veri = satir[5:].strip()
            if veri == "[DONE]":
                break
            try:
                parca = json.loads(veri)
            except ValueError:
                continue
            kullanim = parca.get("usage")
            if isinstance(kullanim, dict) and kullanim.get("completion_tokens"):
                usage_tokens = kullanim["completion_tokens"]
            for secim in parca.get("choices") or []:
                icerik = (secim.get("delta") or {}).get("content")
                if icerik:
                    simdi = time.perf_counter()
                    if ttft is None:
                        ttft = simdi - t0
                    zamanlar.append(simdi)
        e2e = time.perf_counter() - t0
        if ttft is None:
            return Sonuc(False, status=200, hata="stream'de icerik gelmedi", e2e=e2e)
        gaps = [b - a for a, b in zip(zamanlar, zamanlar[1:])]
        return Sonuc(True, status=200, ttft=ttft, e2e=e2e, gaps=gaps,
                     tokens=usage_tokens or len(zamanlar))

    def _oku_blok(self, resp, t0):
        ham = resp.read()
        e2e = time.perf_counter() - t0
        try:
            veri = json.loads(ham.decode("utf-8"))
        except ValueError:
            return Sonuc(False, status=200, hata="JSON olmayan yanit", e2e=e2e)
        try:
            icerik = veri["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return Sonuc(False, status=200, hata="yanitta 'choices' yok", e2e=e2e)
        kullanim = veri.get("usage") or {}
        tokens = kullanim.get("completion_tokens") or max(1, len(icerik) // 4)
        return Sonuc(True, status=200, e2e=e2e, tokens=tokens)


def api_mesaji(govde):
    try:
        veri = json.loads(govde)
    except ValueError:
        return " ".join(govde.split())
    hata = veri.get("error")
    if isinstance(hata, dict):
        return str(hata.get("message") or hata)
    return str(hata or veri.get("message") or " ".join(govde.split()))


def kisalt(metin, n=60):
    metin = " ".join(str(metin).split())
    return metin if len(metin) <= n else metin[:n - 1] + "…"


# --------------------------------------------------------------------------
# yuk uretici
# --------------------------------------------------------------------------

def yuk_uygula(client, toplam, esZamanlilik, sure):
    """Sonuc listesi ve gecen sureyi (saniye) dondurur."""
    sonuclar = []
    kilit = threading.Lock()
    sayac = {"kalan": toplam}
    bitis = (time.perf_counter() + sure) if sure else None

    def devam():
        if bitis is not None:
            return time.perf_counter() < bitis
        with kilit:
            if sayac["kalan"] <= 0:
                return False
            sayac["kalan"] -= 1
            return True

    def isci():
        while devam():
            s = client.cagir()
            with kilit:
                sonuclar.append(s)

    t0 = time.perf_counter()
    is_parcaciklari = [threading.Thread(target=isci) for _ in range(esZamanlilik)]
    for t in is_parcaciklari:
        t.start()
    for t in is_parcaciklari:
        t.join()
    return sonuclar, time.perf_counter() - t0


# --------------------------------------------------------------------------
# raporlama
# --------------------------------------------------------------------------

def ms(deger):
    return 1000.0 * deger


def ozet_hesapla(sonuclar, wall, stream):
    basarili = [s for s in sonuclar if s.ok]
    hatali = [s for s in sonuclar if not s.ok]
    ttfts = sorted(ms(s.ttft) for s in basarili if s.ttft is not None)
    e2es = sorted(ms(s.e2e) for s in basarili)
    gaps = sorted(ms(g) for s in basarili for g in s.gaps)
    tokens = sum(s.tokens for s in basarili)

    def p(dizi, q):
        return percentile(dizi, q)

    return {
        "istek_toplam": len(sonuclar),
        "istek_basarili": len(basarili),
        "istek_hatali": len(hatali),
        "hata_orani_yuzde": (100.0 * len(hatali) / len(sonuclar)) if sonuclar else 0.0,
        "wall_s": wall,
        "istek_per_s": (len(sonuclar) / wall) if wall > 0 else 0.0,
        "cikti_token_per_s": (tokens / wall) if wall > 0 else 0.0,
        "cikti_token_toplam": tokens,
        "cikti_token_ort": (float(tokens) / len(basarili)) if basarili else 0.0,
        "stream": stream,
        "ttft_ms": {"ort": (sum(ttfts) / len(ttfts)) if ttfts else 0.0,
                    "p50": p(ttfts, 0.50), "p90": p(ttfts, 0.90),
                    "p95": p(ttfts, 0.95), "p99": p(ttfts, 0.99),
                    "maks": ttfts[-1] if ttfts else 0.0} if ttfts else None,
        "itl_ms": {"ort": (sum(gaps) / len(gaps)) if gaps else 0.0,
                   "p50": p(gaps, 0.50), "p95": p(gaps, 0.95),
                   "maks": gaps[-1] if gaps else 0.0} if gaps else None,
        "e2e_ms": {"ort": (sum(e2es) / len(e2es)) if e2es else 0.0,
                   "p50": p(e2es, 0.50), "p95": p(e2es, 0.95),
                   "p99": p(e2es, 0.99), "maks": e2es[-1] if e2es else 0.0} if e2es else None,
    }


def hata_dokumu(sonuclar):
    sayim = {}
    for s in sonuclar:
        if s.ok:
            continue
        etiket = ("HTTP %s" % s.status) if s.status else "baglanti"
        if s.hata:
            etiket = "%s: %s" % (etiket, s.hata)
        sayim[etiket] = sayim.get(etiket, 0) + 1
    return sorted(sayim.items(), key=lambda kv: -kv[1])


def ozet_yazdir(ozet, sonuclar, args):
    print("Yük testi   model=%s · stream=%s · max_tokens=%d"
          % (args.model, "açık" if ozet["stream"] else "kapalı", args.max_tokens))
    if args.duration:
        print("Yük         %ds süre · eşzamanlılık %d · ısınma %d"
              % (args.duration, args.concurrency, args.warmup))
    else:
        print("Yük         %d istek · eşzamanlılık %d · ısınma %d"
              % (args.requests, args.concurrency, args.warmup))
    print()
    print("Sonuç       %d istek · %d başarılı · %d hata (%%%.1f)"
          % (ozet["istek_toplam"], ozet["istek_basarili"], ozet["istek_hatali"],
             ozet["hata_orani_yuzde"]))
    print("Süre        %.2fs" % ozet["wall_s"])
    print("Throughput  %.1f istek/s · %.1f çıktı token/s"
          % (ozet["istek_per_s"], ozet["cikti_token_per_s"]))
    print()
    if ozet["ttft_ms"]:
        t = ozet["ttft_ms"]
        print("TTFT  (ms)  ort=%.0f p50=%.0f p90=%.0f p95=%.0f p99=%.0f maks=%.0f"
              % (t["ort"], t["p50"], t["p90"], t["p95"], t["p99"], t["maks"]))
    elif not ozet["stream"]:
        print("TTFT  (ms)  ölçülmedi (--no-stream)")
    else:
        print("TTFT  (ms)  ölçülemedi (başarılı istek yok)")
    if ozet["itl_ms"]:
        i = ozet["itl_ms"]
        print("ITL   (ms)  ort=%.1f p50=%.1f p95=%.1f maks=%.1f"
              % (i["ort"], i["p50"], i["p95"], i["maks"]))
    if ozet["e2e_ms"]:
        e = ozet["e2e_ms"]
        print("E2E   (ms)  ort=%.0f p50=%.0f p95=%.0f p99=%.0f maks=%.0f"
              % (e["ort"], e["p50"], e["p95"], e["p99"], e["maks"]))
    print("Çıktı token ort=%.1f · toplam=%d"
          % (ozet["cikti_token_ort"], ozet["cikti_token_toplam"]))

    dokum = hata_dokumu(sonuclar)
    if dokum:
        print()
        print("Hatalar     " + " · ".join("%d× %s" % (adet, etiket)
                                          for etiket, adet in dokum))


def csv_yaz(dosya, sonuclar):
    with open(dosya, "w", newline="", encoding="utf-8") as fh:
        yazici = csv.writer(fh)
        yazici.writerow(["index", "ok", "status", "ttft_ms", "e2e_ms",
                         "itl_ort_ms", "cikti_token", "hata"])
        for i, s in enumerate(sonuclar):
            itl = (1000.0 * sum(s.gaps) / len(s.gaps)) if s.gaps else ""
            yazici.writerow([
                i, int(s.ok), s.status or "",
                "%.1f" % ms(s.ttft) if s.ttft is not None else "",
                "%.1f" % ms(s.e2e),
                "%.1f" % itl if itl != "" else "",
                s.tokens, s.hata or ""])


# --------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        description="OpenAI uyumlu bir chat endpoint'ine TTFT ölçen yük testi")
    p.add_argument("-e", "--endpoint", default=os.environ.get("LLM_ENDPOINT"),
                   help="temel URL, .../v1 veya tam .../v1/chat/completions")
    p.add_argument("-k", "--api-key", default=os.environ.get("LLM_API_KEY"))
    p.add_argument("-m", "--model", default=os.environ.get("LLM_MODEL"))
    p.add_argument("-n", "--requests", type=int, default=20,
                   help="toplam istek sayısı (varsayılan 20)")
    p.add_argument("-c", "--concurrency", type=int, default=4,
                   help="eşzamanlı istek sayısı (varsayılan 4)")
    p.add_argument("--duration", type=int, metavar="S",
                   help="istek sayısı yerine S saniye boyunca yük uygula")
    p.add_argument("-p", "--prompt", default=VARSAYILAN_PROMPT)
    p.add_argument("--prompt-file", help="prompt'u dosyadan oku")
    p.add_argument("--max-tokens", type=int, default=128)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--warmup", type=int, default=1,
                   help="ölçüme dahil edilmeyen ısınma isteği (varsayılan 1)")
    p.add_argument("--no-stream", action="store_true",
                   help="stream kapalı: TTFT ölçülemez, sadece uçtan uca süre")
    p.add_argument("--stream-usage", action="store_true",
                   help="stream_options.include_usage gönder (sunucu desteklemeyebilir)")
    p.add_argument("--csv", metavar="DOSYA", help="istek başına satır yaz")
    p.add_argument("--json", action="store_true", help="özeti JSON olarak yazdır")
    p.add_argument("--max-ttft-p95", type=float, metavar="MS",
                   help="SLO: TTFT p95 bu değeri aşarsa exit 1")
    p.add_argument("--max-error-rate", type=float, default=0.0, metavar="YUZDE",
                   help="SLO: hata oranı bu yüzdeyi aşarsa exit 1 (varsayılan 0)")
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("-i", "--insecure", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    eksik = [ad for ad, deger in (("endpoint", args.endpoint),
                                  ("api-key", args.api_key),
                                  ("model", args.model)) if not deger]
    if eksik:
        p.error("eksik: %s (parametre ya da $LLM_ENDPOINT / $LLM_API_KEY / $LLM_MODEL)"
                % ", ".join(eksik))
    if args.concurrency < 1:
        p.error("--concurrency en az 1 olmalı")
    if not args.duration and args.requests < 1:
        p.error("--requests en az 1 olmalı")

    prompt = args.prompt
    if args.prompt_file:
        with open(args.prompt_file, encoding="utf-8") as fh:
            prompt = fh.read().strip()

    client = ChatClient(
        url=resolve_url(args.endpoint), api_key=args.api_key, model=args.model,
        prompt=prompt, max_tokens=args.max_tokens, temperature=args.temperature,
        stream=not args.no_stream, stream_usage=args.stream_usage,
        timeout=args.timeout, insecure=args.insecure, verbose=args.verbose)

    if args.verbose:
        print("POST %s (model=%s, stream=%s)"
              % (client.url, args.model, not args.no_stream), file=sys.stderr)

    for _ in range(max(0, args.warmup)):
        isinma = client.cagir()
        if not isinma.ok and args.verbose:
            print("ısınma isteği başarısız: %s" % isinma.hata, file=sys.stderr)

    sonuclar, wall = yuk_uygula(client, args.requests, args.concurrency, args.duration)
    if not sonuclar:
        print("hiç istek tamamlanmadı", file=sys.stderr)
        return 1

    ozet = ozet_hesapla(sonuclar, wall, not args.no_stream)

    if args.csv:
        csv_yaz(args.csv, sonuclar)
        print("CSV yazıldı: %s (%d satır)" % (args.csv, len(sonuclar)), file=sys.stderr)

    if args.json:
        print(json.dumps(ozet, ensure_ascii=False, indent=2))
    else:
        ozet_yazdir(ozet, sonuclar, args)

    # --- SLO kapıları -----------------------------------------------------
    ihlal = []
    if ozet["hata_orani_yuzde"] > args.max_error_rate:
        ihlal.append("hata oranı %%%.1f > %%%.1f"
                     % (ozet["hata_orani_yuzde"], args.max_error_rate))
    if args.max_ttft_p95 is not None:
        if not ozet["ttft_ms"]:
            ihlal.append("TTFT ölçülemedi (--no-stream ile --max-ttft-p95 birlikte kullanılamaz)")
        elif ozet["ttft_ms"]["p95"] > args.max_ttft_p95:
            ihlal.append("TTFT p95 %.0fms > %.0fms"
                         % (ozet["ttft_ms"]["p95"], args.max_ttft_p95))

    if ihlal:
        for i in ihlal:
            print("SLO ihlali: %s" % i, file=sys.stderr)
        return 1
    if args.max_ttft_p95 is not None and not args.json:
        print("SLO         TTFT p95 %.0fms <= %.0fms ✓"
              % (ozet["ttft_ms"]["p95"], args.max_ttft_p95))
    return 0


if __name__ == "__main__":
    sys.exit(main())
