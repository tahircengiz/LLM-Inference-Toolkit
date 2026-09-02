#!/usr/bin/env python3

"""
Dokümandaki her örneği gerçekten çalıştırıp çıktısını karşılaştırır.

Deponun sözü şu: "dokümanda yazan her çıktı gerçekten çalıştırılıp
doğrulanmıştır." Bu araç o sözü otomatik kontrol edilebilir hale getirir -
runbook'lardaki komut/çıktı çiftlerini ayıklar, sahte sunucuya karşı koşturur ve
farkları gösterir.

    python3 tests/verify_docs.py            # özet
    python3 tests/verify_docs.py -v         # farkları da göster

Zamanla değişen değerler (gecikme, tok/s, port) karşılaştırmadan önce
normalize edilir: her sayı N'e dönüştürülür. Yani yapı karşılaştırılır, o anki
ölçüm değil.
"""

import argparse
import difflib
import os
import re
import shutil
import subprocess
import sys
import threading

KOK = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(KOK, "examples"))
import mock_server  # noqa: E402

for _akis in (sys.stdout, sys.stderr):
    if hasattr(_akis, "reconfigure"):
        _akis.reconfigure(encoding="utf-8", errors="replace")

# Bu kalıpları içeren örnekler çalıştırılmaz: kurulum adımları, gerçek adres
# isteyenler, sunucu başlatanlar ya da kabuk döngüleri.
ATLA = [
    "git clone", "chmod", "mock_server.py", "10.0.0.10", "SUNUCU", "$MY_KEY",
    "MY_KEY", "for ", "while ", "time ", "mail ", "tests/smoke_test.py",
    "tests/capture_report.py", "tests/verify_docs.py", "export ", "$env:",
    "Unblock-File", "ExecutionPolicy", "netsh", "OutputEncoding", "curl ",
    "prompt.txt", "promptlar.txt", "dokumanlar.txt", "gercek_rag_prompt.txt",
    "sonuc.csv", "ozet.json", "raporlar/", "date +", "alarm_ver", "|| exit 1",
    # Gercek model adlariyla yazilmis ornekler: ciktilari gercek bir sunucudan
    # geliyor, sahte sunucuda uretilemez.
    "BAAI/", "Qwen/", "bge-m3", "bge-reranker", "text-embedding", "qwen3-",
    "meta-llama/", "gpt-4o", "$LLM_MODEL", "$LLM_ENDPOINT", "modeller.csv",
]

SAYI = re.compile(r"\d+(?:[.,]\d+)?")
BOSLUK = re.compile(r"\s+")
# PowerShell tablo başlıklarını renklendirir; dokümanda düz metin var.
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def normalize(satir):
    """ANSI kodlarını atar, sayıları N'e çevirir, boşlukları sadeleştirir."""
    return BOSLUK.sub(" ", SAYI.sub("N", ANSI.sub("", satir))).strip()


def ornekleri_ayikla(yol):
    """(baslik, komut, beklenen_cikti) üçlüleri döndürür."""
    metin = open(yol, encoding="utf-8").read()
    satirlar = metin.split("\n")
    ornekler = []
    baslik = "?"
    i = 0
    while i < len(satirlar):
        s = satirlar[i]
        if s.startswith("###") or s.startswith("##"):
            baslik = s.lstrip("#").strip()
            i += 1
            continue
        if s.startswith("```bash") or s.startswith("```powershell"):
            dil = "powershell" if "powershell" in s else "bash"
            j = i + 1
            komut = []
            while j < len(satirlar) and not satirlar[j].startswith("```"):
                komut.append(satirlar[j])
                j += 1
            # komut bloğunun hemen ardından gelen çıktı bloğunu ara
            k = j + 1
            while k < len(satirlar) and satirlar[k].strip() == "":
                k += 1
            beklenen = None
            if k < len(satirlar) and satirlar[k].startswith("```") \
                    and not satirlar[k].startswith("```bash") \
                    and not satirlar[k].startswith("```powershell"):
                m = k + 1
                govde = []
                while m < len(satirlar) and not satirlar[m].startswith("```"):
                    govde.append(satirlar[m])
                    m += 1
                beklenen = "\n".join(govde)
                k = m
            ornekler.append((baslik, dil, "\n".join(komut), beklenen))
            i = k + 1
            continue
        i += 1
    return ornekler


BETIK_KLASORLERI = ("bash", "python", "powershell")


def goreli_yolu_coz(k):
    """"./embed-test.py" gibi yazimlari PATH'ten cozulebilir hale getirir.

    Dokumanlar betigin bulundugu klasorde olundugunu varsayarak yaziyor;
    dogrulayici depo kokunden calisiyor.
    """
    import os as _os
    def _degistir(m):
        ad = m.group(1)
        for klasor in BETIK_KLASORLERI:
            if _os.path.exists(_os.path.join(KOK, klasor, ad)):
                return ad
        return m.group(0)
    return re.sub(r"\./([A-Za-z0-9_.-]+\.(?:sh|py))", _degistir, k)


def komutu_hazirla(komut, dil):
    """Windows yazımını bu makinede çalışacak biçime çevirir.

    PowerShell blokları tek tek kabuk komutu değil, bir PowerShell oturumunda
    yazılan satırlardır ($LASTEXITCODE gibi). Bu yüzden bloğun tamamı `pwsh
    -Command` ile çalıştırılır.
    """
    # Devam eden satirlari (\ ve `) birlestir, gerisini satir satir birak:
    # her satir ayri bir komuttur, bosluklа birlestirmek onlari bozar.
    k = komut.replace("`\n", " ").replace("\\\n", " ")
    k = "\n".join(satir.rstrip() for satir in k.split("\n") if satir.strip())
    if dil == "powershell":
        k = k.replace(".\\powershell\\", "./powershell/")
        k = k.replace(".\\python\\", "./python/")
        k = k.replace("python\\", "python/").replace("powershell\\", "powershell/")
        k = re.sub(r"(?m)^python ", "python3 ", k)
        k = k.replace("pwsh -NoProfile -File ", "pwsh -NoProfile -NonInteractive -File ")
    return goreli_yolu_coz(k)


def main():
    p = argparse.ArgumentParser(description="Dokümandaki örnekleri doğrular")
    p.add_argument("-v", "--verbose", action="store_true", help="farkları göster")
    p.add_argument("--dosya", action="append", help="yalnızca bu dokümanı kontrol et")
    args = p.parse_args()

    dosyalar = args.dosya or [
        "docs/runbook-linux.md", "docs/runbook-windows.md",
        "docs/health-check.md", "docs/models.md", "docs/rerank.md",
        "docs/embeddings.md", "docs/chat-completions.md", "docs/loadtest.md",
    ]

    port = 8899
    for aday in range(8899, 8999):
        try:
            srv = mock_server.build_server(port=aday)
            port = aday
            break
        except OSError:
            continue
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % port

    env = dict(os.environ)
    env.update({
        "LLM_ENDPOINT": base, "LLM_API_KEY": "sk-mock",
        "LLM_MODEL": mock_server.MODEL_ID,
        "LLM_EMBED_MODEL": mock_server.EMBED_MODEL_ID,
        "LLM_RERANK_MODEL": mock_server.RERANK_MODEL_ID,
        "PYTHONIOENCODING": "utf-8",
    })
    # Dokumanlar betikleri PATH'te varmis gibi yaziyor (llm-check.sh, embed-test.py);
    # ornekleri oldugu gibi calistirabilmek icin klasorleri PATH'e ekliyoruz.
    env["PATH"] = os.pathsep.join([
        os.path.join(KOK, "bash"), os.path.join(KOK, "python"),
        os.path.join(KOK, "powershell"), env.get("PATH", ""),
    ])

    bash = shutil.which("bash")
    pwsh_var = shutil.which("pwsh") is not None
    eslesen = atlanan = farkli = bayat = 0
    farklar = []

    for dosya in dosyalar:
        yol = os.path.join(KOK, dosya)
        if not os.path.exists(yol):
            continue
        print("\n%s" % dosya)
        for baslik, dil, komut, beklenen in ornekleri_ayikla(yol):
            if beklenen is None or not komut.strip():
                continue
            if any(a in komut for a in ATLA):
                atlanan += 1
                continue
            if dil == "powershell" and not pwsh_var:
                atlanan += 1
                continue
            if dil == "bash" and not bash:
                atlanan += 1
                continue

            calisacak = komutu_hazirla(komut, dil)
            if dil == "powershell":
                argv = ["pwsh", "-NoProfile", "-NonInteractive", "-Command", calisacak]
            else:
                argv = [bash or "sh", "-c", calisacak]
            try:
                # stderr stdout'a katiliyor: dokumandaki cikti terminalde
                # gorulen sirayla yazilmis, ikisini ayirmak sirayi bozar.
                pr = subprocess.run(argv, cwd=KOK, env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8",
                                    errors="replace", timeout=120)
            except subprocess.TimeoutExpired:
                farkli += 1
                farklar.append((dosya, baslik, calisacak, "(zaman aşımı)", beklenen))
                print("  FARK    %-46s zaman aşımı" % baslik[:46])
                continue

            gercek = (pr.stdout or "").strip()
            g_satir = [normalize(x) for x in gercek.split("\n") if x.strip()]
            b_satir = [normalize(x) for x in beklenen.split("\n") if x.strip()]

            # Beklenen her satır gerçek çıktıda bulunmalı. Sıra aranmıyor:
            # stdout ile stderr'in birbirine göre sırası (PowerShell VERBOSE
            # satırları gibi) tamponlamaya bağlı ve koşumdan koşuma değişiyor.
            kalan = list(g_satir)
            eksik = []
            for satir in b_satir:
                if satir in kalan:
                    kalan.remove(satir)
                else:
                    eksik.append(satir)
            if not eksik:
                eslesen += 1
                # Altdizi eslesmesi, dokumanda EKSIK kalan satirlari yakalamaz:
                # ornegin sahte sunucuya model eklendiginde tablo buyur ama
                # dokumandaki eski satirlar hala gecerlidir. Fazladan cikan
                # anlamli satirlari uyari olarak bildiriyoruz.
                onemsiz = ("VERBOSE:", "WARNING:", "$ ", "(yerleşik örnek")
                fazla = [x for x in g_satir
                         if x not in b_satir and x
                         and not any(x.startswith(o) for o in onemsiz)]
                if fazla and len(b_satir) > 2:
                    bayat += 1
                    print("  EŞLEŞTİ %-40s (dokümanda olmayan %d satır)"
                          % (baslik[:40], len(fazla)))
                    if args.verbose:
                        for x in fazla[:6]:
                            print("            + %s" % x[:90])
                else:
                    print("  EŞLEŞTİ %s" % baslik[:60])
            else:
                farkli += 1
                farklar.append((dosya, baslik, calisacak, gercek, beklenen))
                print("  FARK    %-46s %d satır eşleşmedi" % (baslik[:46], len(eksik)))

    srv.shutdown()

    if args.verbose and farklar:
        for dosya, baslik, komut, gercek, beklenen in farklar:
            print("\n" + "=" * 72)
            print("%s → %s" % (dosya, baslik))
            print("$ %s" % komut)
            print("-" * 72)
            for satir in difflib.unified_diff(
                    beklenen.split("\n"), gercek.split("\n"),
                    fromfile="dokümanda yazan", tofile="gerçek çıktı", lineterm=""):
                print(satir)

    print("\n%d eşleşti · %d fark · %d atlandı%s"
          % (eslesen, farkli, atlanan,
             " · %d örnekte dokümanda olmayan satır var" % bayat if bayat else ""))
    if farkli and not args.verbose:
        print("Farkları görmek için: python3 tests/verify_docs.py -v")
    return 1 if farkli else 0


if __name__ == "__main__":
    sys.exit(main())
