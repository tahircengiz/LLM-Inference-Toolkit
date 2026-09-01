# LLM Inference Toolkit

OpenAI uyumlu **her inference endpoint'ini** yoklamak, doğrulamak ve ölçmek için
bağımlılıksız betikler — Linux, macOS ya da Windows'tan.

[![CI](https://github.com/tahircengiz/LLM-Inference-Toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/tahircengiz/LLM-Inference-Toolkit/actions/workflows/ci.yml)
[![Lisans: MIT](https://img.shields.io/badge/lisans-MIT-blue.svg)](LICENSE)
![Bash 3.2+](https://img.shields.io/badge/bash-3.2%2B-green)
![PowerShell 5.1+](https://img.shields.io/badge/powershell-5.1%2B-blue)
![Python 3.8+ stdlib](https://img.shields.io/badge/python-3.8%2B%20stdlib-yellow)

---

## Neden var?

Bir modeli vLLM, TGI, llama.cpp ya da bir gateway'in arkasına koyduğunuzda hep
aynı sorular gelir — ve genellikle `pip install` yapma izniniz olmayan bir
jump host'tan sorulur:

- Endpoint ayakta mı, bearer token gerçekten zorunlu tutuluyor mu?
- Model adı doğru mu, yoksa sunucu sessizce başka bir şey mi servis ediyor?
- Yanıt temiz UTF-8 mi geliyor, yoksa Türkçe karakterler bozuluyor mu?
- İlk token kaç ms'de geliyor (TTFT), yük altında p95 ne oluyor?
- Embedding'ler L2-normalize mi? Deterministik mi? Batch'lemek vektörü değiştiriyor mu?

Buradaki her betik bu sorulardan birini **SDK, virtualenv ve paket kurulumu
olmadan** yanıtlar — sadece `curl` + `jq`, .NET ya da Python standart kütüphanesi.

## Nereden başlamalı — işletim sisteminizi seçin

Her runbook, testleri **komut + üretmesi gereken birebir çıktı** olarak listeler;
hepsi gerçekten çalıştırılıp doğrulanmıştır, hafızadan yazılmamıştır.

| Kullandığınız sistem | Runbook | Chat betiği |
| --- | --- | --- |
| Linux · macOS · WSL | **[docs/runbook-linux.md](docs/runbook-linux.md)** | `bash/llm-prompt.sh` |
| Windows | **[docs/runbook-windows.md](docs/runbook-windows.md)** | `powershell\Invoke-LlmPrompt.ps1` |

Referans dokümanlar:
[chat completions](docs/chat-completions.md) ·
[model keşfi](docs/models.md) ·
[yük testi ve TTFT](docs/loadtest.md) ·
[embeddings](docs/embeddings.md) ·
[backend uyumluluğu](docs/compatibility.md) ·
[sorun giderme](docs/troubleshooting.md)

## İçindekiler

| Betik | Çalışma ortamı | API | Ne yapar |
| --- | --- | --- | --- |
| [`bash/llm-prompt.sh`](bash/llm-prompt.sh) | Bash 3.2+, `curl`, `jq` *ya da* `python3` | `/v1/chat/completions` | Tek prompt, isteğe bağlı SSE streaming, token kullanımı / gecikme / tok-s |
| [`powershell/Invoke-LlmPrompt.ps1`](powershell/Invoke-LlmPrompt.ps1) | PowerShell 5.1 veya 7+ | `/v1/chat/completions` | Aynısı; `curl.exe` gerekmez, Windows'ta TLS 1.2 ve UTF-8 sorunlarını çözer |
| [`bash/llm-models.sh`](bash/llm-models.sh) | Bash 3.2+, `curl`, `jq` *ya da* `python3` | `/v1/models` | Ne servis edildiğini listeler, filtreler, doğrular; her modeli yoklayıp gerçekten cevap vereni bulur |
| [`powershell/Get-LlmModels.ps1`](powershell/Get-LlmModels.ps1) | PowerShell 5.1 veya 7+ | `/v1/models` | Aynısı; nesne döndürür, `Where-Object` / `Export-Csv` ile zincirlenir |
| [`python/chat-loadtest.py`](python/chat-loadtest.py) | Python 3.8+ (yalnızca stdlib) | `/v1/chat/completions` | TTFT, ITL, uçtan uca gecikme ve throughput ölçen yük testi; SLO kapısı olarak da kullanılır |
| [`python/embed-test.py`](python/embed-test.py) | Python 3.8+ (yalnızca stdlib) | `/v1/embeddings` | Embed, cosine çiftleri, 7 kontrollük sağlık paketi ve eşzamanlılık benchmark'ı |
| [`examples/mock_server.py`](examples/mock_server.py) | Python 3.8+ (yalnızca stdlib) | hepsi | GPU'suz denemek için sahte OpenAI uyumlu sunucu — `-m error-404` ile tekrarlanabilir HTTP hataları da üretir |
| [`tests/smoke_test.py`](tests/smoke_test.py) | Python 3.8+ (yalnızca stdlib) | — | Yukarıdaki her betiği sahte sunucuya karşı çalıştırır; kurulu olmayan ortamları atlar |

## Doğrulandığı ortamlar

Her push'ta tüm paket üç işletim sisteminde koşuyor. Bunlar niyet değil, sonuç:

| Ortam | Bash betikleri | PowerShell betikleri | Python betikleri | Sonuç |
| --- | --- | --- | --- | --- |
| `ubuntu-latest` — Bash 5.x, pwsh 7.6.5, Python 3.14 | ✅ | ✅ | ✅ | 36/36 |
| `macos-latest` — Bash 3.2.57, pwsh 7.6.4, Python 3.14 | ✅ | ✅ | ✅ | 36/36 |
| `windows-latest` — pwsh 7.6.5, Python 3.14 | tasarım gereği atlanır | ✅ | ✅ | 22/22 |
| macOS 26.5 yerel — Bash 3.2.57, pwsh 7.6.3, Python 3.9 | ✅ | ✅ | ✅ | 36/36 |

Embedding sağlık paketi **üç platformda da birebir aynı cosine değerlerini**
döndürüyor; runbook'lardaki beklenen değerleri yazmaya değer kılan da bu.

## Gereksinimler

| Platform | Chat / model keşfi | Yük testi ve embeddings |
| --- | --- | --- |
| Linux / WSL | `bash`, `curl` ve `jq` (ya da `python3`) | `python3` |
| macOS | aynısı — GNU coreutils gerekmez | `python3` |
| Windows | PowerShell 5.1 (yerleşik) veya 7+ | `python` / `py -3` |

`jq` tercih edilir ama zorunlu değildir: Bash betikleri JSON işlemek için
`python3`'e düşer, böylece sadeleştirilmiş bir container'da da çalışırlar.

## Hızlı başlangıç

### 1. Sunucusuz deneme

Sahte sunucuyu başlatın, sonra her şeyi ona karşı çalıştırın:

```bash
python3 examples/mock_server.py --port 8899
```

```bash
export LLM_ENDPOINT=http://127.0.0.1:8899
export LLM_API_KEY=sk-mock
export LLM_MODEL=mock-model

bash/llm-models.sh -l                        # ne servis ediliyor?
bash/llm-models.sh --probe                   # hangileri gerçekten cevap veriyor?
bash/llm-prompt.sh "Merhaba, kendini tanıt"
bash/llm-prompt.sh --stream "Bir haiku yaz"
python3 python/chat-loadtest.py -n 20 -c 4   # TTFT / ITL / throughput
python3 python/embed-test.py --suite
```

```powershell
$env:LLM_ENDPOINT = 'http://127.0.0.1:8899'
$env:LLM_API_KEY  = 'sk-mock'
$env:LLM_MODEL    = 'mock-model'

.\powershell\Get-LlmModels.ps1 -Long
.\powershell\Get-LlmModels.ps1 -Probe
.\powershell\Invoke-LlmPrompt.ps1 "Merhaba, kendini tanıt"
.\powershell\Invoke-LlmPrompt.ps1 "Bir haiku yaz" -Stream
python python\chat-loadtest.py -n 20 -c 4
```

### 2. Gerçek bir endpoint'e karşı

```bash
chmod +x bash/llm-prompt.sh bash/llm-models.sh python/embed-test.py python/chat-loadtest.py

# 1. çağıracağınız modelin gerçekten orada olduğunu doğrulayın
bash/llm-models.sh -e http://10.0.0.10:8000 -k "$MY_KEY" --has Qwen/Qwen2.5-7B-Instruct

# 2. çağırın
bash/llm-prompt.sh \
  -e http://10.0.0.10:8000 \
  -k "$MY_KEY" \
  -m Qwen/Qwen2.5-7B-Instruct \
  -v "Merhaba, kendini tanıt"
```

```
Merhaba! Ben bir yapay zeka asistanıyım...
prompt=14 completion=128 total=142 | 2.31s | 55.4 tok/s | finish=stop
```

```bash
# 3. yük altında ne oluyor?
python3 python/chat-loadtest.py -n 100 -c 16 --max-tokens 256
```

```
Sonuç       100 istek · 100 başarılı · 0 hata (%0.0)
Süre        18.42s
Throughput  5.4 istek/s · 1389.2 çıktı token/s

TTFT  (ms)  ort=412 p50=395 p90=520 p95=580 p99=690 maks=712
ITL   (ms)  ort=18.4 p50=17.9 p95=24.1 maks=31.0
E2E   (ms)  ort=2890 p50=2850 p95=3320 p99=3510 maks=3540
```

```bash
# 4. embedding modeli RAG için gerçekten kullanılabilir mi?
python3 python/embed-test.py -e http://10.0.0.10:8001 -k "$MY_KEY" -m BAAI/bge-m3 --suite
```

```
PASS  batch içinde dim tutarlı               dim=1024
PASS  vektörler L2-normalize                 norms=1.000000, 1.000000, 1.000000
PASS  çağrılar arası deterministik           max|delta|=0.000e+00 cos=1.00000000
PASS  cos(paraphrase) > cos(alakasız)        para=0.7412 alakasız=0.2688 fark=0.4724
PASS  cos(aynı metin) ~= 1.0                 cos=1.00000000
PASS  batch pozisyonu vektörü değiştirmiyor  cos(pos0)=1.00000000 cos(pos3)=1.00000000
PASS  uzun girdi (~264000 karakter) işlendi  sessizce truncate edildi, prompt_tokens=8192
```

## Yapılandırma

Bütün betikler aynı ortam değişkenlerini okur; bir kez ayarlayıp parametreleri
bırakabilirsiniz:

| Değişken | Kullanan | Parametre karşılığı |
| --- | --- | --- |
| `LLM_ENDPOINT` | hepsi | `-e` / `-Endpoint` |
| `LLM_API_KEY` | hepsi | `-k` / `-ApiKey` |
| `LLM_MODEL` | hepsi | `-m` / `-Model` |
| `LLM_EMBED_MODEL` | `embed-test.py` | `-m` (`LLM_MODEL`'den önceliklidir) |

Açıkça verilen parametre her zaman ortam değişkenini ezer. `source` edebileceğiniz
bir örnek: [`examples/env.example`](examples/env.example).

**Endpoint URL'leri normalize edilir**, yani şu üçü eşdeğerdir:

```
http://10.0.0.10:8000
http://10.0.0.10:8000/v1
http://10.0.0.10:8000/v1/chat/completions
```

Betikler `/v1/chat/completions` (ya da `/v1/embeddings`, `/v1/models`) sonekini
yalnızca eksikse ekler; böylece API'yi bir path öneki altında servis eden
gateway'ler (`https://gw.example.com/team-a/v1`) olduğu gibi çalışır.

## Özellik matrisi

Chat betikleri:

| | `llm-prompt.sh` | `Invoke-LlmPrompt.ps1` |
| --- | --- | --- |
| Bloklayan istek | ✅ | ✅ |
| SSE streaming | ✅ `--stream` | ✅ `-Stream` |
| System prompt | ✅ `-s` | ✅ `-SystemPrompt` |
| Temperature / max tokens | ✅ | ✅ |
| Ham JSON | ✅ `--raw` | ✅ `-Raw` |
| Token kullanımı + tok/s | ✅ `-v` | ✅ `-Verbose` |
| TLS doğrulamasını atlama | ✅ `-i` | ✅ `-Insecure` |
| stdin / pipe'tan prompt | ✅ | — (parametre olarak verin) |

Model keşif betikleri:

| | `llm-models.sh` | `Get-LlmModels.ps1` |
| --- | --- | --- |
| id listeleme | ✅ | ✅ |
| Metadata tablosu (sahip, oluşturulma, context) | ✅ `-l` | ✅ `-Long` |
| Altdizi filtresi | ✅ | ✅ |
| Model varlığını doğrulama | ✅ `--has` | ✅ `-Has` |
| Her modeli yoklama | ✅ `--probe` | ✅ `-Probe` |
| Ham JSON | ✅ `--json` | ✅ `-Json` |
| Zincirlenebilir nesne çıktısı | — (metin) | ✅ |

## Güvenlik

- **`-k` yerine `LLM_API_KEY` tercih edin.** Paylaşılan bir Linux makinesinde
  parametre olarak verilen anahtar `ps aux` ile herkese görünür ve shell
  geçmişine yazılır.
- `-i` / `-Insecure` sertifika doğrulamasını tamamen kapatır. Self-signed iç
  endpoint'ler için vardır; internete açık hiçbir şeye karşı kullanmayın.
- Betikler diske yazmaz, dışarı veri göndermez, prompt'larınızı loglamaz.
  `--raw` tam yanıt gövdesini basar — ticket'a yapıştırırken dikkat.
- Hiçbir anahtar, hostname ya da iç URL commit'e girmemeli. `.gitignore` zaten
  `.env` ve `*.local.*` dosyalarını kapsıyor.

## Test

```bash
python3 tests/smoke_test.py          # her betik, sahte sunucuya karşı
python3 tests/smoke_test.py -v       # ek olarak her komutun çıktısı
```

```
PASS  bash: chat (bloklayan)                     Merhaba! Bu bir mock yanittir - Türkçe karakter testi: çğışöüÇĞİŞÖÜ
PASS  bash: --probe bozuk modeli yakalıyor       MODEL       STATUS    LATENCY  NOT
PASS  python: TTFT, ITL'den ayrı ölçülüyor       ttft_p50=71ms itl_p50=27ms (mock 3 chunk'lık prefill bekler)
PASS  python: sağlık paketi                      PASS  batch içinde dim tutarlı               dim=128
...
36 geçti, 0 başarısız, 0 atlandı/uyarı
```

Kurulu olmayan çalışma ortamları `FAIL` değil `SKIP` olarak raporlanır, böylece
aynı dosya her yerde çalışır. CI bunu her push'ta Ubuntu, macOS ve Windows'ta
koşuyor — yukarıdaki platform iddiaları test ediliyor, varsayılmıyor.

## Yol haritası

- [x] `/v1/models` keşif yardımcısı — [docs/models.md](docs/models.md)
- [x] Chat için TTFT'li yük testi — [docs/loadtest.md](docs/loadtest.md)
- [ ] Reranker endpoint'i (`/v1/rerank`) sağlık kontrolleri
- [ ] Function calling ve structured output uyumluluk testleri
- [ ] Python'suz Windows makineleri için yerel PowerShell embeddings betiği

## Katkı

Issue ve PR'lar açığa — özellikle
[docs/compatibility.md](docs/compatibility.md) içindekilerden farklı davranan bir
backend gördüyseniz. Kısa kurallar: [CONTRIBUTING.md](CONTRIBUTING.md).

## Lisans

[MIT](LICENSE)
