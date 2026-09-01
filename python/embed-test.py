#!/usr/bin/env python3

"""
OpenAI uyumlu bir /v1/embeddings endpoint'ini test eder (vLLM, TEI-OpenAI shim,
Infinity, OpenAI, gateway'ler). Sadece standart kütüphane - requests ve numpy yok.

Linux, macOS ve Windows (PowerShell) üzerinde aynı şekilde çalışır:
python3 / py -3.

Modlar:
  varsayılan  verilen metin(ler)i embed eder; dim / L2 norm / gecikme yazar
  --pair      iki metin arasındaki cosine benzerliği
  --suite     sağlık paketi (dim, normalizasyon, determinizm, batch pozisyonu,
              benzerlik sıralaması, truncation) - hata varsa exit 1
  --bench     C eşzamanlılıkla N istek atarak throughput ölçer

Örnekler:
  ./embed-test.py -e http://10.0.0.10:8000 -k sk-x -m bge-m3 "merhaba"
  ./embed-test.py --suite -v
  ./embed-test.py --bench 200 --concurrency 16 --batch-size 8
"""

import argparse
import base64
import json
import math
import os
import ssl
import struct
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor


# --------------------------------------------------------------------------
# taşıma katmanı
# --------------------------------------------------------------------------

# Windows konsolu varsayılan olarak cp1252 kullanır ve Türkçe karakterlerde
# UnicodeEncodeError verir. Çıktı akışlarını UTF-8'e sabitliyoruz.
for _akis in (sys.stdout, sys.stderr):
    if hasattr(_akis, "reconfigure"):
        _akis.reconfigure(encoding="utf-8", errors="replace")

def resolve_url(base: str) -> str:
    u = base.rstrip("/")
    if u.endswith("/embeddings"):
        return u
    if u.endswith("/v1"):
        return u + "/embeddings"
    return u + "/v1/embeddings"


class EmbedClient:
    def __init__(self, url, api_key, model, timeout=300, insecure=False,
                 encoding_format="float", dimensions=None, verbose=False):
        self.url = url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.encoding_format = encoding_format
        self.dimensions = dimensions
        self.verbose = verbose
        self.ctx = None
        if insecure:
            self.ctx = ssl.create_default_context()
            self.ctx.check_hostname = False
            self.ctx.verify_mode = ssl.CERT_NONE

    def embed(self, texts):
        """(vektörler, usage sözlüğü, geçen saniye) döndürür."""
        if isinstance(texts, str):
            texts = [texts]
        payload = {
            "model": self.model,
            "input": texts,
            "encoding_format": self.encoding_format,
        }
        if self.dimensions is not None:
            payload["dimensions"] = self.dimensions

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.url,
            data=body,
            method="POST",
            headers={
                "Authorization": "Bearer %s" % self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        if self.verbose:
            preview = json.dumps(
                {**payload, "input": ["<%d text(s)>" % len(texts)]},
                ensure_ascii=False,
            )
            print("POST %s  %s" % (self.url, preview), file=sys.stderr)

        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout,
                                        context=self.ctx) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            raise SystemExit("HTTP %s from %s\n%s" % (e.code, self.url, detail))
        except urllib.error.URLError as e:
            raise SystemExit("bağlantı kurulamadı %s: %s" % (self.url, e.reason))
        elapsed = time.perf_counter() - t0

        try:
            data = json.loads(raw.decode("utf-8"))
        except ValueError:
            raise SystemExit("JSON olmayan yanıt:\n" + raw.decode("utf-8", "replace"))

        items = data.get("data")
        if not items:
            raise SystemExit("yanıtta 'data' yok:\n" + json.dumps(data)[:2000])

        # İstek sırasını koru - sunucunun sıralı dönme zorunluluğu yok.
        items = sorted(items, key=lambda d: d.get("index", 0))
        vectors = [decode_embedding(it["embedding"]) for it in items]
        return vectors, data.get("usage") or {}, elapsed


def decode_embedding(value):
    """float listesi ya da little-endian float32'ın base64 hali."""
    if isinstance(value, list):
        return value
    blob = base64.b64decode(value)
    if len(blob) % 4:
        raise SystemExit("base64 embedding uzunluğu %d, 4'ün katı değil" % len(blob))
    return list(struct.unpack("<%df" % (len(blob) // 4), blob))


# --------------------------------------------------------------------------
# vektör yardımcıları
# --------------------------------------------------------------------------

def l2(v):
    return math.sqrt(sum(x * x for x in v))


def cosine(a, b):
    if len(a) != len(b):
        raise ValueError("dim uyuşmuyor: %d ve %d" % (len(a), len(b)))
    na, nb = l2(a), l2(b)
    if na == 0.0 or nb == 0.0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def max_abs_diff(a, b):
    return max(abs(x - y) for x, y in zip(a, b))


def percentile(sorted_vals, p):
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return sorted_vals[int(k)]
    return sorted_vals[lo] * (hi - k) + sorted_vals[hi] * (k - lo)


# --------------------------------------------------------------------------
# modlar
# --------------------------------------------------------------------------

def mode_embed(client, texts):
    vectors, usage, elapsed = client.embed(texts)
    for i, (text, vec) in enumerate(zip(texts, vectors)):
        head = ", ".join("%+.4f" % x for x in vec[:5])
        label = text if len(text) <= 48 else text[:45] + "..."
        print("[%d] %-50s dim=%d  |v|=%.6f  min=%+.4f max=%+.4f"
              % (i, label, len(vec), l2(vec), min(vec), max(vec)))
        print("     head=[%s, ...]" % head)
    print("gecikme=%.0fms  metin=%d  prompt_tokens=%s  total_tokens=%s"
          % (elapsed * 1000, len(texts),
             usage.get("prompt_tokens", "?"), usage.get("total_tokens", "?")))


def mode_pair(client, a, b):
    vectors, _, elapsed = client.embed([a, b])
    print("cosine=%.6f  dim=%d  gecikme=%.0fms"
          % (cosine(vectors[0], vectors[1]), len(vectors[0]), elapsed * 1000))


IDENT = "Kubernetes cluster'inda GPU node'u nasil etiketlenir?"
PARA = "K8s uzerinde GPU'lu sunucuya label eklemenin yolu nedir?"
UNREL = "Dun aksam sahilde balik izgara yaptik."
LONG_UNIT = "GPU scheduling ve MIG partitioning konusunda kapasite planlamasi. "


def esik(deger, pass_esigi, uyari_esigi):
    """Yüksek daha iyi: PASS / UYARI / FAIL.

    Quantize edilmiş (GGUF) ya da batch'li GPU sunucularında aynı metin bile
    bit-bit aynı vektörü vermez. cos=0.9999 ile cos=0.99988 arasındaki fark
    pratikte hiçbir şeyi değiştirmez; bunu FAIL saymak yanlış alarmdır.
    """
    if deger >= pass_esigi:
        return "PASS"
    if deger >= uyari_esigi:
        return "UYARI"
    return "FAIL"


def mode_suite(client, verbose):
    results = []

    def check(name, durum, detail):
        if durum is True:
            durum = "PASS"
        elif durum is False:
            durum = "FAIL"
        results.append((name, durum, detail))

    # 1. temel embed + dim + normalizasyon
    vecs, usage, elapsed = client.embed([IDENT, PARA, UNREL])
    dim = len(vecs[0])
    check("batch içinde dim tutarlı",
          all(len(v) == dim for v in vecs),
          "dim=%d" % dim)

    norms = [l2(v) for v in vecs]
    normalized = all(abs(n - 1.0) < 1e-3 for n in norms)
    check("vektörler L2-normalize",
          normalized,
          "norms=%s%s" % (", ".join("%.6f" % n for n in norms),
                          "" if normalized else "  (istemci tarafında normalize gerekir)"))

    # 2. determinizm - aynı metin, ikinci çağrı
    vecs2, _, _ = client.embed([IDENT])
    diff = max_abs_diff(vecs[0], vecs2[0])
    cos_det = cosine(vecs[0], vecs2[0])
    durum_det = "PASS" if diff < 1e-4 else esik(cos_det, 0.9999, 0.999)
    check("çağrılar arası deterministik",
          durum_det,
          "max|delta|=%.3e cos=%.8f%s" % (diff, cos_det,
              "  (quantize/batch kaynaklı sapma, pratikte önemsiz)"
              if durum_det == "UYARI" else ""))

    # 3. benzerlik sıralaması: paraphrase, alakasız metni geçmeli
    cos_para = cosine(vecs[0], vecs[1])
    cos_unrel = cosine(vecs[0], vecs[2])
    check("cos(paraphrase) > cos(alakasız)",
          cos_para > cos_unrel,
          "para=%.4f alakasız=%.4f fark=%.4f" % (cos_para, cos_unrel, cos_para - cos_unrel))

    # 4. aynı metnin tek batch içindeki kendine benzerliği
    vsame, _, _ = client.embed([IDENT, IDENT])
    cos_ayni = cosine(vsame[0], vsame[1])
    durum_ayni = esik(cos_ayni, 0.9999, 0.999)
    check("cos(aynı metin) ~= 1.0",
          durum_ayni,
          "cos=%.8f%s" % (cos_ayni,
              "  (quantize/batch kaynaklı sapma, pratikte önemsiz)"
              if durum_ayni == "UYARI" else ""))

    # 5. batch/tekil tutarlılığı - pooling/padding hatalarını yakalar
    padded = client.embed([IDENT, UNREL * 4, PARA * 3, IDENT])[0]
    cos0, cos3 = cosine(vecs[0], padded[0]), cosine(vecs[0], padded[3])
    durum_batch = esik(min(cos0, cos3), 0.9999, 0.999)
    check("batch pozisyonu vektörü değiştirmiyor",
          durum_batch,
          "cos(pos0)=%.8f cos(pos3)=%.8f%s" % (cos0, cos3,
              "  (quantize/batch kaynaklı sapma, pratikte önemsiz)"
              if durum_batch == "UYARI" else ""))

    # 6. max-model-len üzerindeki truncation davranışı
    long_text = LONG_UNIT * 4000
    try:
        lvec, lusage, _ = client.embed([long_text])
        check("uzun girdi (~%d karakter) işlendi" % len(long_text),
              len(lvec[0]) == dim,
              "sessizce truncate edildi, prompt_tokens=%s" % lusage.get("prompt_tokens", "?"))
    except SystemExit as e:
        # Reddetmek de geçerli bir davranış; hangisi olduğunu bilmek yeterli.
        check("uzun girdi (~%d karakter) işlendi" % len(long_text),
              "UYARI",
              "sunucu reddetti (%s) - ingestion tarafında chunk'lama gerekir"
              % str(e).splitlines()[0])

    # 7. opsiyonel: Matryoshka dimensions
    if client.dimensions is not None:
        check("dimensions=%d uygulandı" % client.dimensions,
              dim == client.dimensions,
              "dönen dim=%d" % dim)

    width = max(len(n) for n, _, _ in results)
    hatali = sum(1 for _, d, _ in results if d == "FAIL")
    uyari = sum(1 for _, d, _ in results if d == "UYARI")
    for name, durum, detail in results:
        print("%-5s  %-*s  %s" % (durum, width, name, detail))
    ozet = "\n%d/%d geçti" % (len(results) - hatali - uyari, len(results))
    if uyari:
        ozet += " · %d uyarı" % uyari
    if hatali:
        ozet += " · %d hata" % hatali
    print("%s  (dim=%d, ilk çağrı %.0fms, prompt_tokens=%s)"
          % (ozet, dim, elapsed * 1000, usage.get("prompt_tokens", "?")))
    # UYARI exit kodunu değiştirmez; yalnızca FAIL değiştirir.
    return 1 if hatali else 0


def mode_bench(client, total, concurrency, batch_size):
    text = IDENT
    batch = [text] * batch_size
    n_requests = max(1, total // batch_size)
    latencies = []

    def one(_):
        _, _, el = client.embed(batch)
        return el

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for el in pool.map(one, range(n_requests)):
            latencies.append(el)
    wall = time.perf_counter() - t0

    latencies.sort()
    texts_done = n_requests * batch_size
    print("istek=%d  batch_size=%d  eşzamanlılık=%d  metin=%d"
          % (n_requests, batch_size, concurrency, texts_done))
    print("süre=%.2fs  throughput=%.1f metin/s  %.1f istek/s"
          % (wall, texts_done / wall, n_requests / wall))
    print("gecikme ms: ort=%.0f p50=%.0f p95=%.0f p99=%.0f maks=%.0f"
          % (1000 * sum(latencies) / len(latencies),
             1000 * percentile(latencies, 0.50),
             1000 * percentile(latencies, 0.95),
             1000 * percentile(latencies, 0.99),
             1000 * latencies[-1]))


# --------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        description="OpenAI uyumlu bir embeddings endpoint'ini test eder")
    p.add_argument("text", nargs="*", help="embed edilecek metin(ler)")
    p.add_argument("-e", "--endpoint", default=os.environ.get("LLM_ENDPOINT"))
    p.add_argument("-k", "--api-key", default=os.environ.get("LLM_API_KEY"))
    p.add_argument("-m", "--model", default=os.environ.get("LLM_EMBED_MODEL")
                   or os.environ.get("LLM_MODEL"))
    p.add_argument("-f", "--file", help="satır başına bir metin içeren dosya")
    p.add_argument("--pair", nargs=2, metavar=("A", "B"),
                   help="iki metnin cosine benzerliği")
    p.add_argument("--suite", action="store_true", help="sağlık paketini çalıştır")
    p.add_argument("--bench", type=int, metavar="N", help="toplam N metinle benchmark")
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--dimensions", type=int,
                   help="Matryoshka çıktı boyutu (model desteklemeli)")
    p.add_argument("--encoding-format", choices=["float", "base64"], default="float")
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("-i", "--insecure", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    missing = [n for n, v in (("endpoint", args.endpoint),
                              ("api-key", args.api_key),
                              ("model", args.model)) if not v]
    if missing:
        p.error("eksik: %s (parametre ya da $LLM_ENDPOINT / $LLM_API_KEY / $LLM_EMBED_MODEL)"
                % ", ".join(missing))

    client = EmbedClient(
        url=resolve_url(args.endpoint),
        api_key=args.api_key,
        model=args.model,
        timeout=args.timeout,
        insecure=args.insecure,
        encoding_format=args.encoding_format,
        dimensions=args.dimensions,
        verbose=args.verbose,
    )

    if args.suite:
        return mode_suite(client, args.verbose)
    if args.bench:
        mode_bench(client, args.bench, args.concurrency, args.batch_size)
        return 0
    if args.pair:
        mode_pair(client, args.pair[0], args.pair[1])
        return 0

    texts = list(args.text)
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            texts += [line.rstrip("\n") for line in fh if line.strip()]
    if not texts and not sys.stdin.isatty():
        texts = [line.rstrip("\n") for line in sys.stdin if line.strip()]
    if not texts:
        p.error("metin verilmedi (parametre, --file, stdin ya da --suite / --pair / --bench)")

    mode_embed(client, texts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
