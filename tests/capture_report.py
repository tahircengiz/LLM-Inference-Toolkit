#!/usr/bin/env python3

"""
Bir hedef endpoint'e karşı tüm test bataryasını çalıştırır ve sonuçları
markdown rapor olarak yazar. Amaç: yarın tek tek çalıştırıp elle kopyalamak
yerine, her hedefte tek komut çalıştırıp çıktıyı gözden geçirmek.

    python3 tests/capture_report.py \\
        --label "llama.cpp Qwen3-30B" \\
        -e http://10.0.0.10:8084 -k dummy -m qwen3-30b-a3b-gguf \\
        --embed-model qwen3-embed --embed-endpoint http://10.0.0.10:8085 \\
        -o raporlar/llamacpp.md

Rapor her komutun kendisini, exit kodunu ve tam çıktısını içerir. API anahtarı
çıktıda maskelenir. Araç hüküm vermez - kaydeder; değerlendirme insana aittir.
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time

KOK = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))

for _akis in (sys.stdout, sys.stderr):
    if hasattr(_akis, "reconfigure"):
        _akis.reconfigure(encoding="utf-8", errors="replace")


class Adim(object):
    def __init__(self, baslik, argv, env, aciklama="", beklenen=""):
        self.baslik = baslik
        self.argv = argv
        self.env = env
        self.aciklama = aciklama
        self.beklenen = beklenen
        self.cikti = ""
        self.kod = None
        self.sure = 0.0
        self.atlandi = None


def maskele(metin, anahtar):
    if anahtar and len(anahtar) > 3:
        metin = metin.replace(anahtar, "***")
    return metin


def calistir(adim, anahtar, timeout=600):
    t0 = time.perf_counter()
    try:
        p = subprocess.run(adim.argv, env=adim.env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        adim.kod = p.returncode
        adim.cikti = maskele((p.stdout or "") + (p.stderr or ""), anahtar).strip()
    except FileNotFoundError as e:
        adim.atlandi = "çalışma ortamı yok (%s)" % e.filename
    except subprocess.TimeoutExpired:
        adim.kod = -1
        adim.cikti = "(%ds zaman aşımı)" % timeout
    adim.sure = time.perf_counter() - t0
    return adim


def main():
    p = argparse.ArgumentParser(description="Gerçek bir endpoint'e karşı test raporu üretir")
    p.add_argument("--label", required=True, help="hedefin adı, ör. 'llama.cpp Qwen3-30B'")
    p.add_argument("-e", "--endpoint", default=os.environ.get("LLM_ENDPOINT"))
    p.add_argument("-k", "--api-key", default=os.environ.get("LLM_API_KEY"))
    p.add_argument("-m", "--model", default=os.environ.get("LLM_MODEL"))
    p.add_argument("--embed-model", default=os.environ.get("LLM_EMBED_MODEL"))
    p.add_argument("--embed-endpoint", help="embedding farklı bir adresteyse")
    p.add_argument("--rerank-model", default=os.environ.get("LLM_RERANK_MODEL"))
    p.add_argument("--rerank-endpoint", help="rerank farklı bir adresteyse")
    p.add_argument("--load-requests", type=int, default=10, help="yük testi istek sayısı")
    p.add_argument("--load-concurrency", type=int, default=2)
    p.add_argument("-o", "--out", help="rapor dosyası (verilmezse stdout)")
    args = p.parse_args()

    eksik = [a for a, d in (("endpoint", args.endpoint), ("api-key", args.api_key),
                            ("model", args.model)) if not d]
    if eksik:
        p.error("eksik: %s" % ", ".join(eksik))

    py = sys.executable
    bash = None if os.name == "nt" else shutil.which("bash")
    pwsh = shutil.which("pwsh") or shutil.which("powershell")

    ortak = dict(os.environ)
    ortak.update({"LLM_ENDPOINT": args.endpoint, "LLM_API_KEY": args.api_key,
                  "LLM_MODEL": args.model, "PYTHONIOENCODING": "utf-8"})
    if args.embed_model:
        ortak["LLM_EMBED_MODEL"] = args.embed_model
    if args.rerank_model:
        ortak["LLM_RERANK_MODEL"] = args.rerank_model

    embed_env = dict(ortak)
    if args.embed_endpoint:
        embed_env["LLM_ENDPOINT"] = args.embed_endpoint
    rerank_env = dict(ortak)
    if args.rerank_endpoint:
        rerank_env["LLM_ENDPOINT"] = args.rerank_endpoint

    yol = lambda *p: os.path.join(KOK, *p)
    adimlar = []

    def ekle(baslik, argv, env=None, aciklama="", beklenen=""):
        adimlar.append(Adim(baslik, argv, env or ortak, aciklama, beklenen))

    # --- 1. sağlık kontrolü ---------------------------------------------
    if bash:
        ekle("Sağlık kontrolü — basit", [bash, yol("bash", "llm-check.sh")],
             beklenen="6/6 geçti · exit 0")
        ekle("Sağlık kontrolü — gelişmiş", [bash, yol("bash", "llm-check.sh"), "--full"],
             beklenen="hiç FAIL olmaması · exit 0")
    if pwsh:
        ekle("Sağlık kontrolü — PowerShell",
             [pwsh, "-NoProfile", "-NonInteractive", "-File",
              yol("powershell", "Test-LlmEndpoint.ps1")],
             beklenen="Bash sürümüyle satır satır aynı sonuç")

    # --- 2. model keşfi --------------------------------------------------
    if bash:
        ekle("Model listesi", [bash, yol("bash", "llm-models.sh"), "-l"],
             aciklama="CONTEXT sütunu doluysa sunucu max_model_len yayınlıyor demektir",
             beklenen="model listede · exit 0")
        ekle("Model yoklama", [bash, yol("bash", "llm-models.sh"), "--probe"],
             aciklama="chat dışı modeller (embedding/rerank) 400 dönebilir, bu normaldir")
        ekle("Model doğrulama (--has)",
             [bash, yol("bash", "llm-models.sh"), "--has", args.model],
             beklenen="sessiz · exit 0")

    # --- 3. chat ---------------------------------------------------------
    if bash:
        ekle("Chat — bloklayan + tanılama",
             [bash, yol("bash", "llm-prompt.sh"), "-v", "-n", "64",
              "Türkiye'nin başkenti neresi? Tek cümle."],
             beklenen="doğru yanıt · finish=stop · Türkçe karakterler sağlam")
        ekle("Chat — streaming",
             [bash, yol("bash", "llm-prompt.sh"), "--stream", "-n", "64",
              "Üç maddede KV cache nedir?"],
             aciklama="parça parça mı geliyor, yoksa tek seferde mi?")
        ekle("Chat — system prompt ve sampling",
             [bash, yol("bash", "llm-prompt.sh"), "-v", "-s",
              "Yalnızca tek kelimeyle cevap ver.", "-t", "0.2", "-n", "16",
              "Fransa'nın başkenti?"],
             beklenen="gövdede system mesajı, temperature 0.2, max_tokens 16")
        ekle("Chat — endpoint normalizasyonu (/v1)",
             [bash, yol("bash", "llm-prompt.sh"), "-e",
              args.endpoint.rstrip("/") + "/v1", "-n", "8", "ping"],
             beklenen="temel URL ile aynı sonuç")
    if pwsh:
        ekle("Chat — PowerShell bloklayan",
             [pwsh, "-NoProfile", "-NonInteractive", "-File",
              yol("powershell", "Invoke-LlmPrompt.ps1"),
              "Türkiye'nin başkenti neresi? Tek cümle.", "-MaxTokens", "64", "-Verbose"],
             beklenen="Bash ile aynı yanıt · Türkçe karakterler sağlam")
        ekle("Chat — PowerShell streaming",
             [pwsh, "-NoProfile", "-NonInteractive", "-File",
              yol("powershell", "Invoke-LlmPrompt.ps1"),
              "Üç maddede KV cache nedir?", "-MaxTokens", "64", "-Stream"])

    # --- 4. yük testi ----------------------------------------------------
    ekle("Yük testi — TTFT / ITL / throughput",
         [py, yol("python", "chat-loadtest.py"), "-n", str(args.load_requests),
          "-c", str(args.load_concurrency), "--max-tokens", "64"],
         aciklama="TTFT p95 kullanıcı deneyiminin bütçesi; ITL okuma hızını belirler",
         beklenen="0 hata · TTFT ve ITL satırları dolu")
    ekle("Yük testi — bloklayan (karşılaştırma)",
         [py, yol("python", "chat-loadtest.py"), "-n", "5", "-c", "1",
          "--max-tokens", "64", "--no-stream"],
         beklenen="TTFT ölçülmedi (--no-stream) · E2E dolu")

    # --- 5. embeddings ---------------------------------------------------
    if args.embed_model:
        ekle("Embeddings — sağlık paketi",
             [py, yol("python", "embed-test.py"), "--suite"], embed_env,
             aciklama="UYARI exit kodunu etkilemez; FAIL eder",
             beklenen="7/7 ya da UYARI'lı geçiş · exit 0")
        ekle("Embeddings — benchmark",
             [py, yol("python", "embed-test.py"), "--bench", "32",
              "--concurrency", "4", "--batch-size", "8"], embed_env)
        ekle("Embeddings — base64 ve dimensions",
             [py, yol("python", "embed-test.py"), "--encoding-format", "base64",
              "--dimensions", "256", "merhaba dünya"], embed_env,
             aciklama="dim 256 dönmüyorsa sunucu dimensions parametresini yok sayıyor")
    else:
        adimlar.append(Adim("Embeddings", [], ortak))
        adimlar[-1].atlandi = "--embed-model verilmedi"

    # --- 6. rerank -------------------------------------------------------
    if args.rerank_model:
        ekle("Rerank — basit sıralama",
             [py, yol("python", "rerank-test.py")], rerank_env,
             beklenen="ilgili doküman 1. sırada · Yorum satırı")
        ekle("Rerank — sağlık paketi",
             [py, yol("python", "rerank-test.py"), "--suite"], rerank_env,
             beklenen="8/8 ya da UYARI'lı geçiş · exit 0")
        ekle("Rerank — benchmark",
             [py, yol("python", "rerank-test.py"), "--bench", "16",
              "--concurrency", "4", "--docs", "8"], rerank_env)
    else:
        adimlar.append(Adim("Rerank", [], ortak))
        adimlar[-1].atlandi = "--rerank-model verilmedi"

    # --- 7. hata yolları -------------------------------------------------
    if bash:
        ekle("Hata — var olmayan model",
             [bash, yol("bash", "llm-prompt.sh"), "-m", "kesinlikle-yok-boyle-model",
              "-n", "8", "test"],
             aciklama="tek modelli sunucular model alanını yok sayıp yanıt verebilir",
             beklenen="HTTP 404/400 ve exit 1, YA DA sunucu model alanını yok sayıyor")
        ekle("Hata — yanlış anahtar",
             [bash, yol("bash", "llm-prompt.sh"), "-k", "kesinlikle-yanlis-anahtar",
              "-n", "8", "test"],
             beklenen="HTTP 401 ve exit 1, YA DA sunucu anahtar doğrulamıyor")
        ekle("Hata — kapalı port",
             [bash, yol("bash", "llm-check.sh"), "-e", "http://127.0.0.1:9", "-q"],
             beklenen="'endpoint erişilemiyor' · exit 1")

    # --- çalıştır --------------------------------------------------------
    print("Hedef: %s\n" % args.label)
    for i, adim in enumerate(adimlar, 1):
        if adim.atlandi:
            print("%2d/%d  ATLANDI  %s (%s)" % (i, len(adimlar), adim.baslik, adim.atlandi))
            continue
        print("%2d/%d  %s ..." % (i, len(adimlar), adim.baslik), end="", flush=True)
        calistir(adim, args.api_key)
        print(" exit=%s (%.1fs)" % (adim.kod, adim.sure))

    # --- rapor -----------------------------------------------------------
    satirlar = []
    ek = satirlar.append
    ek("# Test raporu — %s" % args.label)
    ek("")
    ek("| | |")
    ek("| --- | --- |")
    ek("| Endpoint | `%s` |" % args.endpoint)
    ek("| Model | `%s` |" % args.model)
    if args.embed_model:
        ek("| Embedding modeli | `%s`%s |" % (args.embed_model,
           (" (`%s`)" % args.embed_endpoint) if args.embed_endpoint else ""))
    if args.rerank_model:
        ek("| Rerank modeli | `%s`%s |" % (args.rerank_model,
           (" (`%s`)" % args.rerank_endpoint) if args.rerank_endpoint else ""))
    ek("| Çalıştıran | %s %s, Python %s |"
       % (platform.system(), platform.release(), platform.python_version()))
    ek("")
    ek("> Bu rapor `tests/capture_report.py` ile üretildi. Her bölüm komutun")
    ek("> kendisini, exit kodunu ve tam çıktısını içerir. API anahtarı maskelidir.")
    ek("")
    ek("## Özet")
    ek("")
    ek("| # | Adım | Exit | Süre | Değerlendirme |")
    ek("| --- | --- | --- | --- | --- |")
    for i, adim in enumerate(adimlar, 1):
        if adim.atlandi:
            ek("| %d | %s | — | — | atlandı: %s |" % (i, adim.baslik, adim.atlandi))
        else:
            ek("| %d | %s | `%s` | %.1fs | ☐ |" % (i, adim.baslik, adim.kod, adim.sure))
    ek("")
    ek("Değerlendirme sütununu elle doldurun: ✅ beklendiği gibi · ⚠️ not düşülecek · ❌ sorun.")
    ek("")
    for i, adim in enumerate(adimlar, 1):
        ek("## %d. %s" % (i, adim.baslik))
        ek("")
        if adim.atlandi:
            ek("_Atlandı: %s_" % adim.atlandi)
            ek("")
            continue
        if adim.aciklama:
            ek("%s" % adim.aciklama)
            ek("")
        ek("```")
        ek(" ".join(maskele(a, args.api_key) for a in adim.argv))
        ek("```")
        ek("")
        if adim.beklenen:
            ek("**Beklenen:** %s" % adim.beklenen)
            ek("")
        ek("**exit=%s** (%.1fs)" % (adim.kod, adim.sure))
        ek("")
        ek("```")
        ek(adim.cikti if adim.cikti else "(çıktı yok)")
        ek("```")
        ek("")

    rapor = "\n".join(satirlar)
    if args.out:
        klasor = os.path.dirname(os.path.abspath(args.out))
        if klasor and not os.path.isdir(klasor):
            os.makedirs(klasor)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(rapor + "\n")
        print("\nRapor yazıldı: %s (%d adım)" % (args.out, len(adimlar)))
    else:
        print()
        print(rapor)
    return 0


if __name__ == "__main__":
    sys.exit(main())
