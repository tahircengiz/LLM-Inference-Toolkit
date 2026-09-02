#!/usr/bin/env python3

"""
Bir reranker endpoint'ini test eder (/v1/rerank - Cohere/Jina biçimi; vLLM, TEI,
Infinity, Jina, Voyage, gateway'ler). Sadece standart kütüphane.

Linux, macOS ve Windows'ta aynı şekilde çalışır: python3 / py -3.

Modlar:
  varsayılan  yerleşik örnek soru + 4 doküman ile sıralamayı gösterir
  "sorgu" d1 d2 ...  kendi sorgunuz ve dokümanlarınızla sıralama
  --suite     sağlık paketi (sıralama, determinizm, doküman sırası, top_n,
              truncation) - hata varsa exit 1
  --bench     C eşzamanlılıkla N istek atarak throughput ölçer

Örnekler:
  ./rerank-test.py
  ./rerank-test.py "GPU node nasıl etiketlenir?" "kubectl label ..." "balık tarifi"
  ./rerank-test.py --suite
  ./rerank-test.py --bench 100 --concurrency 8 --docs 20
"""

import argparse
import http.client
import json
import math
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# Windows konsolu varsayılan olarak cp1252 kullanır ve Türkçe karakterlerde
# UnicodeEncodeError verir. Çıktı akışlarını UTF-8'e sabitliyoruz.
for _akis in (sys.stdout, sys.stderr):
    if hasattr(_akis, "reconfigure"):
        _akis.reconfigure(encoding="utf-8", errors="replace")


# --------------------------------------------------------------------------
# yerleşik sondaj seti: bir soru, bir doğru cevap, iki alakasız, bir kısmen ilgili
# --------------------------------------------------------------------------

SORGU = "Kubernetes'te GPU node nasıl etiketlenir?"
DOKUMANLAR = [
    "Sahilde balık ızgara yapmanın püf noktaları.",
    "GPU node etiketlemek için kubectl label komutu kullanılır.",   # doğru cevap
    "Prometheus ile disk doluluk alarmı kurma adımları.",
    "Kubernetes cluster'ında pod'lara kaynak limiti tanımlama.",     # kısmen ilgili
]
DOGRU_INDEX = 1
UZUN_BIRIM = "GPU scheduling ve MIG partitioning konusunda kapasite planlaması. "


# --------------------------------------------------------------------------
# taşıma katmanı
# --------------------------------------------------------------------------

def resolve_url(base):
    u = base.rstrip("/")
    if u.endswith("/rerank"):
        return u
    if u.endswith("/v1"):
        return u + "/rerank"
    return u + "/v1/rerank"


class RerankClient(object):
    def __init__(self, url, api_key, model, timeout=300, insecure=False, verbose=False):
        self.url = url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.verbose = verbose
        self.ctx = None
        if insecure:
            self.ctx = ssl.create_default_context()
            self.ctx.check_hostname = False
            self.ctx.verify_mode = ssl.CERT_NONE

    def rerank(self, query, documents, top_n=None):
        """(sıralı [(index, skor)], usage, geçen saniye) döndürür."""
        payload = {"model": self.model, "query": query, "documents": documents}
        if top_n:
            payload["top_n"] = top_n

        req = urllib.request.Request(
            self.url, data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Authorization": "Bearer %s" % self.api_key,
                     "Content-Type": "application/json",
                     "Accept": "application/json"})
        if self.verbose:
            print("POST %s  (query=%d karakter, %d doküman)"
                  % (self.url, len(query), len(documents)), file=sys.stderr)

        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as resp:
                ham = resp.read()
        except urllib.error.HTTPError as e:
            detay = e.read().decode("utf-8", "replace")
            raise SystemExit("HTTP %s from %s\n%s" % (e.code, self.url, detay))
        except urllib.error.URLError as e:
            raise SystemExit("bağlantı kurulamadı %s: %s" % (self.url, e.reason))
        except (OSError, http.client.HTTPException) as e:
            # Yük altında sunucu bağlantıyı ortada kapatabilir; bu bir hata
            # mesajı olmalı, traceback değil.
            raise SystemExit("bağlantı koptu %s: %s" % (self.url, e))
        gecen = time.perf_counter() - t0

        try:
            veri = json.loads(ham.decode("utf-8"))
        except ValueError:
            raise SystemExit("JSON olmayan yanıt:\n" + ham.decode("utf-8", "replace"))

        return cozumle(veri), (veri.get("usage") or {}) if isinstance(veri, dict) else {}, gecen


def cozumle(veri):
    """Farklı sunucuların yanıt biçimlerini [(index, skor)] listesine indirger.

    Cohere/Jina/vLLM : {"results": [{"index": 0, "relevance_score": 0.9}, ...]}
    TEI (yerel)      : [{"index": 0, "score": 0.9}, ...]
    bazı gateway'ler : {"data": [...]}
    """
    if isinstance(veri, list):
        kayitlar = veri
    elif isinstance(veri, dict):
        kayitlar = veri.get("results")
        if kayitlar is None:
            kayitlar = veri.get("data")
        if kayitlar is None:
            raise SystemExit("yanıtta 'results' yok:\n" + json.dumps(veri)[:2000])
    else:
        raise SystemExit("beklenmeyen yanıt tipi: %s" % type(veri).__name__)

    cikti = []
    for k in kayitlar:
        if not isinstance(k, dict):
            raise SystemExit("beklenmeyen sonuç kaydı: %r" % (k,))
        idx = k.get("index")
        skor = k.get("relevance_score")
        if skor is None:
            skor = k.get("score")
        if idx is None or skor is None:
            raise SystemExit("sonuçta 'index' ya da skor alanı yok: %s" % json.dumps(k)[:200])
        cikti.append((int(idx), float(skor)))
    if not cikti:
        raise SystemExit("sunucu boş sonuç listesi döndürdü")
    return cikti


def percentile(sirali, p):
    if not sirali:
        return 0.0
    k = (len(sirali) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return sirali[int(k)]
    return sirali[lo] * (hi - k) + sirali[hi] * (k - lo)


def kisalt(metin, n=58):
    metin = " ".join(str(metin).split())
    return metin if len(metin) <= n else metin[:n - 1] + "…"


# --------------------------------------------------------------------------
# modlar
# --------------------------------------------------------------------------

def mod_sirala(client, sorgu, dokumanlar, top_n):
    sonuclar, usage, gecen = client.rerank(sorgu, dokumanlar, top_n)
    print("Sorgu   %s" % kisalt(sorgu, 66))
    print("Model   %s · %d doküman · %.0fms" % (client.model, len(dokumanlar), gecen * 1000))
    print()
    print("  #  skor    doküman")
    for sira, (idx, skor) in enumerate(sonuclar, 1):
        metin = dokumanlar[idx] if 0 <= idx < len(dokumanlar) else "(index %d aralık dışı)" % idx
        print("%3d  %.4f  %s" % (sira, skor, kisalt(metin)))

    if len(sonuclar) >= 2:
        fark = sonuclar[0][1] - sonuclar[1][1]
        if fark >= 0.20:
            yorum = "birinci ile ikinci arasındaki fark %.4f — ayrım net" % fark
        elif fark >= 0.05:
            yorum = ("birinci ile ikinci arasındaki fark %.4f — ayrım orta; "
                     "eşik belirlerken kendi verinizle doğrulayın" % fark)
        else:
            yorum = ("birinci ile ikinci arasındaki fark %.4f — model bu dokümanları "
                     "neredeyse ayırt edemiyor" % fark)
        print()
        print("Yorum   %s" % yorum)
    if usage:
        print("Usage   prompt_tokens=%s total_tokens=%s"
              % (usage.get("prompt_tokens", "?"), usage.get("total_tokens", "?")))
    return 0


def esik(deger, pass_esigi, uyari_esigi):
    """Yüksek daha iyi: PASS / UYARI / FAIL. Quantize edilmiş ya da batch'li
    sunucular bit-bit aynı skoru vermez; küçük sapmayı FAIL saymak yanlış alarm."""
    if deger >= pass_esigi:
        return "PASS"
    if deger >= uyari_esigi:
        return "UYARI"
    return "FAIL"


def mod_suite(client):
    sonuclar_listesi = []

    def kontrol(ad, durum, detay):
        if durum is True:
            durum = "PASS"
        elif durum is False:
            durum = "FAIL"
        sonuclar_listesi.append((ad, durum, detay))

    # 1. temel çağrı: her doküman puanlanıyor mu?
    siralama, usage, gecen = client.rerank(SORGU, DOKUMANLAR)
    kontrol("her doküman puanlandı",
            len(siralama) == len(DOKUMANLAR),
            "%d doküman gönderildi, %d sonuç döndü" % (len(DOKUMANLAR), len(siralama)))

    # 2. index'ler geçerli ve benzersiz
    indexler = [i for i, _ in siralama]
    gecerli = all(0 <= i < len(DOKUMANLAR) for i in indexler)
    kontrol("index'ler geçerli ve benzersiz",
            gecerli and len(set(indexler)) == len(indexler),
            "index'ler=%s" % indexler)

    # 3. sunucu sıralı döndürüyor mu?
    skorlar = [s for _, s in siralama]
    kontrol("sonuçlar skora göre azalan sıralı",
            all(a >= b for a, b in zip(skorlar, skorlar[1:])),
            "skorlar=%s" % ", ".join("%.4f" % s for s in skorlar))

    # 4. asıl kalite sorusu: doğru doküman ilk sırada mı?
    ilk = siralama[0][0]
    fark = skorlar[0] - skorlar[1] if len(skorlar) > 1 else 0.0
    kontrol("ilgili doküman ilk sırada",
            ilk == DOGRU_INDEX,
            "ilk=index %d · fark=%.4f%s" % (ilk, fark,
                                            "" if ilk == DOGRU_INDEX else "  (beklenen index %d)" % DOGRU_INDEX))

    # 5. determinizm
    siralama2, _, _ = client.rerank(SORGU, DOKUMANLAR)
    ayni_sira = [i for i, _ in siralama2] == indexler
    maks_delta = max(abs(a - b) for (_, a), (_, b) in zip(siralama, siralama2)) if ayni_sira else 1.0
    if not ayni_sira:
        durum_det = "FAIL"
    elif maks_delta < 1e-4:
        durum_det = "PASS"
    else:
        durum_det = "UYARI" if maks_delta < 1e-2 else "FAIL"
    kontrol("çağrılar arası deterministik",
            durum_det,
            "sıra aynı=%s max|delta|=%.3e%s"
            % ("evet" if ayni_sira else "hayır", maks_delta,
               "  (quantize/batch kaynaklı sapma, sıralama değişmedi)"
               if durum_det == "UYARI" else ""))

    # 6. doküman sırası bağımsızlığı - batching/pozisyon hatalarını yakalar
    ters = list(reversed(DOKUMANLAR))
    ters_siralama, _, _ = client.rerank(SORGU, ters)
    ters_ilk_metin = ters[ters_siralama[0][0]]
    skor_farki = abs(ters_siralama[0][1] - skorlar[0])
    ayni_ilk = ters_ilk_metin == DOKUMANLAR[DOGRU_INDEX]
    if not ayni_ilk:
        durum_sira = "FAIL"          # sıralama değişiyorsa bu bir blocker
    elif skor_farki < 1e-4:
        durum_sira = "PASS"
    else:
        durum_sira = "UYARI" if skor_farki < 1e-2 else "FAIL"
    kontrol("doküman sırası sonucu değiştirmiyor",
            durum_sira,
            "ters sırada da aynı doküman ilk=%s · skor farkı=%.3e%s"
            % ("evet" if ayni_ilk else "hayır", skor_farki,
               "  (skor biraz oynadı ama sıralama korundu)"
               if durum_sira == "UYARI" else ""))

    # 7. top_n uygulanıyor mu?
    ust2, _, _ = client.rerank(SORGU, DOKUMANLAR, top_n=2)
    kontrol("top_n uygulanıyor",
            len(ust2) == 2,
            "top_n=2 için %d sonuç döndü" % len(ust2))

    # 8. uzun doküman
    uzun = UZUN_BIRIM * 2000
    try:
        uzun_siralama, _, _ = client.rerank(SORGU, [DOKUMANLAR[DOGRU_INDEX], uzun])
        kontrol("uzun doküman (~%d karakter) işlendi" % len(uzun),
                len(uzun_siralama) == 2,
                "sessizce truncate edildi")
    except SystemExit as e:
        # Reddetmek de geçerli bir davranış; hangisi olduğunu bilmek yeterli.
        kontrol("uzun doküman (~%d karakter) işlendi" % len(uzun),
                "UYARI", "sunucu reddetti (%s) - chunk'lama gerekir"
                % str(e).splitlines()[0])

    genislik = max(len(a) for a, _, _ in sonuclar_listesi)
    hatali = sum(1 for _, d, _ in sonuclar_listesi if d == "FAIL")
    uyari = sum(1 for _, d, _ in sonuclar_listesi if d == "UYARI")
    for ad, durum, detay in sonuclar_listesi:
        print("%-5s  %-*s  %s" % (durum, genislik, ad, detay))
    ozet = "\n%d/%d geçti" % (len(sonuclar_listesi) - hatali - uyari, len(sonuclar_listesi))
    if uyari:
        ozet += " · %d uyarı" % uyari
    if hatali:
        ozet += " · %d hata" % hatali
    print("%s  (%d doküman, ilk çağrı %.0fms, prompt_tokens=%s)"
          % (ozet, len(DOKUMANLAR), gecen * 1000, usage.get("prompt_tokens", "?")))
    # UYARI exit kodunu değiştirmez; yalnızca FAIL değiştirir.
    return 1 if hatali else 0


def mod_bench(client, toplam, esZamanlilik, doc_sayisi):
    dokumanlar = [DOKUMANLAR[i % len(DOKUMANLAR)] for i in range(doc_sayisi)]
    gecikmeler = []

    def bir(_):
        return client.rerank(SORGU, dokumanlar)[2]

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=esZamanlilik) as havuz:
        for g in havuz.map(bir, range(toplam)):
            gecikmeler.append(g)
    sure = time.perf_counter() - t0

    gecikmeler.sort()
    print("istek=%d  doküman/istek=%d  eşzamanlılık=%d  toplam doküman=%d"
          % (toplam, doc_sayisi, esZamanlilik, toplam * doc_sayisi))
    print("süre=%.2fs  throughput=%.1f istek/s  %.0f doküman/s"
          % (sure, toplam / sure, toplam * doc_sayisi / sure))
    print("gecikme ms: ort=%.0f p50=%.0f p95=%.0f p99=%.0f maks=%.0f"
          % (1000 * sum(gecikmeler) / len(gecikmeler),
             1000 * percentile(gecikmeler, 0.50),
             1000 * percentile(gecikmeler, 0.95),
             1000 * percentile(gecikmeler, 0.99),
             1000 * gecikmeler[-1]))
    return 0


# --------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        description="OpenAI/Cohere uyumlu bir /v1/rerank endpoint'ini test eder")
    p.add_argument("metin", nargs="*",
                   help="ilk değer sorgu, kalanlar doküman; boş bırakılırsa yerleşik örnek kullanılır")
    p.add_argument("-e", "--endpoint", default=os.environ.get("LLM_ENDPOINT"))
    p.add_argument("-k", "--api-key", default=os.environ.get("LLM_API_KEY"))
    p.add_argument("-m", "--model", default=os.environ.get("LLM_RERANK_MODEL")
                   or os.environ.get("LLM_MODEL"))
    p.add_argument("-f", "--documents-file", help="satır başına bir doküman içeren dosya")
    p.add_argument("-q", "--query", help="sorgu (-f ile birlikte kullanışlı)")
    p.add_argument("--top-n", type=int, help="sunucudan yalnızca ilk N sonucu iste")
    p.add_argument("--suite", action="store_true", help="sağlık paketini çalıştır")
    p.add_argument("--bench", type=int, metavar="N", help="N istekle benchmark")
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--docs", type=int, default=8, help="--bench için istek başına doküman")
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("-i", "--insecure", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    eksik = [ad for ad, deger in (("endpoint", args.endpoint),
                                  ("api-key", args.api_key),
                                  ("model", args.model)) if not deger]
    if eksik:
        p.error("eksik: %s (parametre ya da $LLM_ENDPOINT / $LLM_API_KEY / $LLM_RERANK_MODEL)"
                % ", ".join(eksik))

    client = RerankClient(url=resolve_url(args.endpoint), api_key=args.api_key,
                          model=args.model, timeout=args.timeout,
                          insecure=args.insecure, verbose=args.verbose)

    if args.suite:
        return mod_suite(client)
    if args.bench:
        return mod_bench(client, args.bench, args.concurrency, args.docs)

    sorgu = args.query
    dokumanlar = []
    if args.metin:
        if not sorgu:
            sorgu = args.metin[0]
            dokumanlar = list(args.metin[1:])
        else:
            dokumanlar = list(args.metin)
    if args.documents_file:
        with open(args.documents_file, encoding="utf-8") as fh:
            dokumanlar += [s.rstrip("\n") for s in fh if s.strip()]

    if not sorgu and not dokumanlar:
        sorgu, dokumanlar = SORGU, list(DOKUMANLAR)
        print("(yerleşik örnek kullanılıyor - kendi verinizle: "
              "rerank-test.py \"sorgu\" \"doküman 1\" \"doküman 2\" ...)\n")
    elif not sorgu:
        p.error("sorgu verilmedi (-q ya da ilk pozisyonel değer)")
    elif not dokumanlar:
        p.error("doküman verilmedi (pozisyonel değerler ya da -f)")

    return mod_sirala(client, sorgu, dokumanlar, args.top_n)


if __name__ == "__main__":
    sys.exit(main())
