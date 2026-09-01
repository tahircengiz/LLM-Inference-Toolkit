#!/usr/bin/env python3
"""
Uçtan uca smoke test: bu depodaki her betiği, birlikte gelen sahte sunucuya
(examples/mock_server.py) karşı çalıştırır. GPU yok, model yok, ağ yok.

    python3 tests/smoke_test.py            # kurulu olan her şeyi çalıştır
    python3 tests/smoke_test.py -v         # her komutun çıktısını da göster

Kurulu olmayan çalışma ortamları FAIL değil SKIP olarak raporlanır; böylece aynı
dosya Linux, macOS ve Windows'ta çalışır. Herhangi bir kontrol başarısız olursa
exit kodu sıfırdan farklıdır.
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import threading

ROOT = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(ROOT, "examples"))

import mock_server  # noqa: E402  (path is set up above)

IS_WINDOWS = os.name == "nt"
TURKISH_MARKER = "çğışöü"
ASCII_MARKER = "mock yanittir"

results = []
VERBOSE = False

# Windows konsolu varsayılan olarak cp1252 kullanır ve betiklerin döndürdüğü
# Türkçe metni yazdıramaz. Bu, test edilen betiklerin değil bu koşum aracının
# kendi stdout'unun sınırı; o yüzden UTF-8'e sabitliyoruz.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def record(name, status, detail=""):
    results.append((name, status, detail))
    print("%-5s %-42s %s" % (status, name, detail), flush=True)


def run(name, argv, env, expect=(), expect_soft=(), reject=(), want_code=0, stdin=None):
    """Komutu çalıştırır; exit kodunu ve stdout'ta beklenen/yasak altdizileri doğrular."""
    try:
        proc = subprocess.run(argv, env=env, input=stdin, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=120)
    except FileNotFoundError as e:
        record(name, "SKIP", "çalışma ortamı kurulu değil (%s)" % e.filename)
        return None
    except subprocess.TimeoutExpired:
        record(name, "FAIL", "120s sonunda zaman aşımı")
        return None

    out = proc.stdout or ""
    if VERBOSE:
        print("  $ %s\n  stdout: %s\n  stderr: %s"
              % (" ".join(argv), out.strip()[:400], (proc.stderr or "").strip()[:400]))

    if proc.returncode != want_code:
        record(name, "FAIL", "exit=%d (beklenen %d): %s"
               % (proc.returncode, want_code, (proc.stderr or out).strip()[:200]))
        return proc

    missing = [s for s in expect if s not in out]
    if missing:
        record(name, "FAIL", "çıktıda %r yok: %s" % (missing, out.strip()[:200]))
        return proc

    present = [s for s in reject if s in out]
    if present:
        record(name, "FAIL", "çıktıda olmaması gereken %r var" % present)
        return proc

    soft = [s for s in expect_soft if s not in out]
    if soft:
        record(name, "WARN", "konsol kodlaması %r kısmını gizledi (betik hatası değil)" % soft)
        return proc

    record(name, "PASS", out.strip().splitlines()[0][:70] if out.strip() else "")
    return proc


def main():
    global VERBOSE
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    VERBOSE = args.verbose

    port = free_port()
    srv = mock_server.build_server(port=port)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % port

    # Yalnızca doğru anahtarı kabul eden ikinci bir sunucu: 401 yolunu test eder.
    auth_port = free_port()
    auth_srv = mock_server.build_server(port=auth_port, key="sk-dogru")
    threading.Thread(target=auth_srv.serve_forever, daemon=True).start()
    auth_base = "http://127.0.0.1:%d" % auth_port

    print("sahte sunucu: %s/v1\n" % base)

    env = dict(os.environ)
    env.update({
        "LLM_ENDPOINT": base,
        "LLM_API_KEY": "sk-mock",
        "LLM_MODEL": mock_server.MODEL_ID,
        "LLM_EMBED_MODEL": mock_server.MODEL_ID,
        "PYTHONIOENCODING": "utf-8",
    })

    bash_script = os.path.join(ROOT, "bash", "llm-prompt.sh")
    ps_script = os.path.join(ROOT, "powershell", "Invoke-LlmPrompt.ps1")
    embed_script = os.path.join(ROOT, "python", "embed-test.py")
    py = sys.executable

    # ---- bash ------------------------------------------------------------
    # Windows'ta "bash" WSL stub'ına ya da Git Bash'e çözülür; betik ikisini de
    # hedeflemiyor - Windows kullanıcıları PowerShell betiğine yönlendiriliyor.
    bash = None if IS_WINDOWS else shutil.which("bash")
    if not bash:
        record("bash/llm-prompt.sh", "SKIP",
               "Windows'ta PowerShell betiğini kullanın" if IS_WINDOWS else "bash bulunamadı")
    else:
        run("bash: chat (bloklayan)", [bash, bash_script, "-v", "Merhaba"],
            env, expect=[ASCII_MARKER, TURKISH_MARKER])
        run("bash: chat (streaming)", [bash, bash_script, "--stream", "Merhaba"],
            env, expect=[ASCII_MARKER])
        proc = run("bash: --raw JSON döndürüyor", [bash, bash_script, "--raw", "Merhaba"],
                   env, expect=["choices"])
        if proc and proc.returncode == 0:
            try:
                json.loads(proc.stdout)
            except ValueError:
                record("bash: --raw geçerli JSON", "FAIL", "not valid JSON")
        run("bash: stdin'den prompt", [bash, bash_script], env,
            expect=[ASCII_MARKER], stdin="Merhaba\n")
        run("bash: eksik model reddediliyor",
            [bash, bash_script, "-m", "", "Merhaba"], env, want_code=1)
        run("bash: HTTP hatasını gösteriyor",
            [bash, bash_script, "-m", "error-404", "Merhaba"], env, want_code=1)
        models_script = os.path.join(ROOT, "bash", "llm-models.sh")
        run("bash: model listesi", [bash, models_script], env,
            expect=[mock_server.MODEL_ID, mock_server.EMBED_MODEL_ID])
        run("bash: model tablosu", [bash, models_script, "-l"], env,
            expect=["MODEL", "CONTEXT", "8192", "2025-01-01T00:00:00Z"])
        run("bash: model filtresi", [bash, models_script, "embed"], env,
            expect=[mock_server.EMBED_MODEL_ID], reject=[mock_server.MODEL_ID])
        run("bash: --has var olan model",
            [bash, models_script, "--has", mock_server.MODEL_ID], env)
        run("bash: --has olmayan model",
            [bash, models_script, "--has", "no-such-model"], env, want_code=1)
        run("bash: --probe bozuk modeli yakalıyor",
            [bash, models_script, "--probe"], env,
            expect=["ok", "503", "1/4 model cevap verdi"], want_code=1)

        check_script = os.path.join(ROOT, "bash", "llm-check.sh")
        run("bash: sağlık kontrolü (basit)", [bash, check_script], env,
            expect=["endpoint sağlıklı", "erişim", "chat", "UTF-8", "streaming"])
        run("bash: sağlık kontrolü --full", [bash, check_script, "--full"],
            dict(env, LLM_RERANK_MODEL="mock-rerank"),
            expect=["embeddings", "rerank", "yük", "endpoint sağlıklı"])
        proc = run("bash: sağlık kontrolü -q tek satır", [bash, check_script, "-q"], env,
                   expect=["Sonuç:"])
        if proc and proc.returncode == 0 and len(proc.stdout.strip().splitlines()) != 1:
            record("bash: -q gerçekten tek satır", "FAIL",
                   "%d satır yazıldı" % len(proc.stdout.strip().splitlines()))
        run("bash: sağlık kontrolü yanlış modeli yakalıyor",
            [bash, check_script, "-m", "olmayan-model"], env,
            expect=["SAĞLIKSIZ"], want_code=1)
        run("bash: sağlık kontrolü yanlış anahtarı yakalıyor",
            [bash, check_script, "-e", auth_base, "-k", "sk-yanlis"], env,
            expect=["kimlik doğrulama", "SAĞLIKSIZ"], want_code=1)

        # endpoint normalizasyonu: temel URL, /v1 ve tam path - üçü de çalışmalı
        for suffix in ("/v1", "/v1/chat/completions"):
            e2 = dict(env, LLM_ENDPOINT=base + suffix)
            run("bash: endpoint %s" % suffix, [bash, bash_script, "Merhaba"],
                e2, expect=[ASCII_MARKER])

    # ---- powershell ------------------------------------------------------
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if not pwsh:
        record("powershell/Invoke-LlmPrompt.ps1", "SKIP", "pwsh/powershell bulunamadı")
    else:
        # PowerShell 7 her işletim sisteminde pipe'a UTF-8 yazar; orada Türkçe
        # metin zorunlu bir beklenti. Windows PowerShell 5.1 bunun yerine konsol
        # kod sayfasını kullanır - bu betiğin değil konsolun sınırı, o yüzden
        # yalnızca uyarı veriyoruz.
        utf8_expected = os.path.basename(pwsh).lower().startswith("pwsh") or not IS_WINDOWS
        hard = [ASCII_MARKER] + ([TURKISH_MARKER] if utf8_expected else [])
        soft = [] if utf8_expected else [TURKISH_MARKER]
        run("powershell: chat (bloklayan)",
            [pwsh, "-NoProfile", "-NonInteractive", "-File", ps_script, "Merhaba"],
            env, expect=hard, expect_soft=soft)
        run("powershell: chat (streaming)",
            [pwsh, "-NoProfile", "-NonInteractive", "-File", ps_script, "Merhaba", "-Stream"],
            env, expect=[ASCII_MARKER])
        run("powershell: --raw JSON döndürüyor",
            [pwsh, "-NoProfile", "-NonInteractive", "-File", ps_script, "Merhaba", "-Raw"],
            env, expect=["choices"])
        e2 = dict(env, LLM_MODEL="")
        run("powershell: eksik model reddediliyor",
            [pwsh, "-NoProfile", "-NonInteractive", "-File", ps_script, "Merhaba"],
            e2, want_code=1)
        run("powershell: HTTP hatasını gösteriyor",
            [pwsh, "-NoProfile", "-NonInteractive", "-File", ps_script, "Merhaba",
             "-Model", "error-404"], env, want_code=1)

        ps_models = os.path.join(ROOT, "powershell", "Get-LlmModels.ps1")
        psrun = [pwsh, "-NoProfile", "-NonInteractive", "-File", ps_models]
        run("powershell: model listesi", psrun, env,
            expect=[mock_server.MODEL_ID, mock_server.EMBED_MODEL_ID])
        run("powershell: model tablosu", psrun + ["-Long"], env,
            expect=["Model", "Context", "8192", "2025-01-01T00:00:00Z"])
        run("powershell: model filtresi", psrun + ["mock-embed"], env,
            expect=[mock_server.EMBED_MODEL_ID], reject=[mock_server.MODEL_ID])
        run("powershell: --has var olan model",
            psrun + ["-Has", mock_server.MODEL_ID], env)
        run("powershell: --has olmayan model",
            psrun + ["-Has", "no-such-model"], env, want_code=1)
        run("powershell: --probe bozuk modeli yakalıyor", psrun + ["-Probe"], env,
            expect=["ok", "503"], want_code=1)

        ps_check = os.path.join(ROOT, "powershell", "Test-LlmEndpoint.ps1")
        pscheck = [pwsh, "-NoProfile", "-NonInteractive", "-File", ps_check]
        run("powershell: sağlık kontrolü (basit)", pscheck, env,
            expect=["endpoint sağlıklı", "erişim", "chat", "UTF-8", "streaming"])
        run("powershell: sağlık kontrolü -Full", pscheck + ["-Full"],
            dict(env, LLM_RERANK_MODEL="mock-rerank"),
            expect=["embeddings", "rerank", "yük", "endpoint sağlıklı"])
        run("powershell: sağlık kontrolü -Quiet", pscheck + ["-Quiet"], env,
            expect=["Sonuç:"])
        run("powershell: sağlık kontrolü yanlış modeli yakalıyor",
            pscheck + ["-Model", "olmayan-model"], env,
            expect=["SAĞLIKSIZ"], want_code=1)
        run("powershell: sağlık kontrolü yanlış anahtarı yakalıyor",
            pscheck + ["-Endpoint", auth_base, "-ApiKey", "sk-yanlis"], env,
            expect=["kimlik doğrulama", "SAĞLIKSIZ"], want_code=1)

    # ---- python embeddings ----------------------------------------------
    run("python: tek metin embed", [py, embed_script, "merhaba dünya"],
        env, expect=["dim=", "|v|="])
    run("python: cosine çifti", [py, embed_script, "--pair", "GPU node etiketleme",
                                "GPU sunucu label"], env, expect=["cosine="])
    run("python: sağlık paketi", [py, embed_script, "--suite"], env,
        expect=["geçti"])
    run("python: throughput benchmark",
        [py, embed_script, "--bench", "16", "--concurrency", "4", "--batch-size", "4"],
        env, expect=["throughput=", "p95="])
    run("python: HTTP hatasını gösteriyor", [py, embed_script, "-m", "error-500", "x"],
        env, want_code=1)
    # ---- rerank ----------------------------------------------------------
    rerank_script = os.path.join(ROOT, "python", "rerank-test.py")
    rerank_env = dict(env, LLM_RERANK_MODEL="mock-rerank")
    run("python: rerank basit sıralama", [py, rerank_script], rerank_env,
        expect=["skor", "kubectl label", "Yorum"])
    run("python: rerank sağlık paketi", [py, rerank_script, "--suite"], rerank_env,
        expect=["geçti", "ilgili doküman ilk sırada", "doküman sırası sonucu değiştirmiyor"])
    run("python: rerank kendi verisiyle çalışıyor",
        [py, rerank_script, "disk alarmı nasıl kurulur",
         "Prometheus ile disk doluluk alarmı kurma adımları.", "Balık ızgara tarifi."],
        rerank_env, expect=["Prometheus", "ayrım net"])
    run("python: rerank throughput benchmark",
        [py, rerank_script, "--bench", "8", "--concurrency", "2", "--docs", "4"],
        rerank_env, expect=["throughput=", "p95="])
    run("python: rerank HTTP hatasını gösteriyor",
        [py, rerank_script, "-m", "error-503"], rerank_env, want_code=1)

    # ---- yük testi -------------------------------------------------------
    load_script = os.path.join(ROOT, "python", "chat-loadtest.py")
    proc = run("python: yük testi (TTFT)",
               [py, load_script, "-n", "4", "-c", "2", "--json"], env,
               expect=['"ttft_ms"', '"itl_ms"'])
    if proc and proc.returncode == 0:
        # Sahte sunucu ilk token'dan önce üç chunk gecikmesi bekler, sonra her
        # chunk arasında bir gecikme koyar. Yani TTFT, ITL'den belirgin biçimde
        # büyük olmalı - bu ikisinin ayrı ayrı ve doğru ölçüldüğünü kanıtlar.
        try:
            ozet = json.loads(proc.stdout)
            ttft = ozet["ttft_ms"]["p50"]
            itl = ozet["itl_ms"]["p50"]
            tamam = ttft > 0 and itl > 0 and ttft > itl
            record("python: TTFT, ITL'den ayrı ölçülüyor", "PASS" if tamam else "FAIL",
                   "ttft_p50=%.0fms itl_p50=%.0fms (mock 3 chunk'lık prefill bekler)"
                   % (ttft, itl))
        except (ValueError, KeyError, TypeError) as e:
            record("python: TTFT, ITL'den ayrı ölçülüyor", "FAIL", "özet okunamadı: %s" % e)

    run("python: yük testi --no-stream", [py, load_script, "-n", "2", "-c", "1", "--no-stream"],
        env, expect=["ölçülmedi (--no-stream)", "E2E"])
    run("python: yük testi SLO ihlali",
        [py, load_script, "-n", "2", "-c", "1", "--max-ttft-p95", "1"], env, want_code=1)
    run("python: yük testi hatalı modeli raporluyor",
        [py, load_script, "-n", "2", "-c", "1", "-m", "error-503"], env,
        expect=["HTTP 503"], want_code=1)

    e_bad = dict(env, LLM_ENDPOINT="http://127.0.0.1:%d" % free_port())
    run("python: ölü endpoint'i raporluyor", [py, embed_script, "merhaba"],
        e_bad, want_code=1)

    srv.shutdown()
    auth_srv.shutdown()

    failed = [r for r in results if r[1] == "FAIL"]
    passed = [r for r in results if r[1] == "PASS"]
    skipped = [r for r in results if r[1] in ("SKIP", "WARN")]
    print("\n%d geçti, %d başarısız, %d atlandı/uyarı"
          % (len(passed), len(failed), len(skipped)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
