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

## İki seviye: basit ve gelişmiş

**Sadece "çalışıyor mu?" diye soruyorsanız** tek komut yeter:

```bash
bash/llm-check.sh                # Linux · macOS · WSL
```
```powershell
.\powershell\Test-LlmEndpoint.ps1   # Windows
```

```
PASS  erişim            HTTP 200 · 4 model listeleniyor
PASS  kimlik doğrulama  bearer token kabul edildi
PASS  model             listede var
PASS  chat              yanıt geldi · 16 token · finish=stop
PASS  UTF-8             geçerli · "Merhaba! Bu bir mock yanittir - Türkçe k"
PASS  streaming         11 chunk · 322ms

Sonuç: 6/6 geçti · 0 uyarı · endpoint sağlıklı (0.4s)
```

Hepsi geçtiyse exit `0`, en az bir hata varsa `1`. Cron için `-q` / `-Quiet`
yalnızca son satırı yazar.

**Detay istiyorsanız** aynı komuta `--full` ekleyin (model yoklama + embeddings
sağlık paketi + kısa yük testi), ya da doğrudan uzmanlaşmış betiklere geçin:

| Ne öğrenmek istiyorsunuz | Basit | Gelişmiş |
| --- | --- | --- |
| Endpoint ayakta mı? | `llm-check.sh` | `llm-check.sh --full` |
| Ne servis ediliyor? | `llm-models.sh` | `llm-models.sh -l --probe` |
| Model ne cevap veriyor? | `llm-prompt.sh "Merhaba"` | `llm-prompt.sh -v --stream --raw` |
| Ne kadar hızlı? | `chat-loadtest.py -n 10` | `chat-loadtest.py -n 200 -c 16 --csv` |
| Embedding'ler sağlam mı? | `embed-test.py "metin"` | `embed-test.py --suite --bench 200` |
| Reranker doğru sıralıyor mu? | `rerank-test.py` | `rerank-test.py --suite --bench 100` |

Ayrıntı: [docs/health-check.md](docs/health-check.md).

## Çıktıyı nasıl okumalı

Bütün betikler aynı dili konuşur; bir kez öğrenince hepsi tanıdık gelir.

| İşaret | Anlamı | Exit koduna etkisi |
| --- | --- | --- |
| `PASS` | Kontrol geçti | — |
| `FAIL` | Kontrol düştü, düzeltilmesi gerekir | exit `1` |
| `UYARI` | Dikkate değer ama sağlıksız saymayan durum — örneğin `/v1/models` uygulamayan tek modelli bir sunucu | **etkilemez** |
| `SKIP` | Gerekli çalışma ortamı yok (Windows'ta `bash` gibi) | etkilemez |

Üç kural:

1. **Exit kodu `0` ya da `1`'dir.** Her betik doğrudan CI ve cron'da
   kullanılabilir: `llm-check.sh || alarm_ver`.
2. **Sonuç stdout'a, tanılama stderr'e gider.** `llm-prompt.sh "..." > cevap.txt`
   `-v` açıkken bile temiz bir dosya verir.
3. **Zaman değerleri her koşumda değişir, yapı değişmez.** Runbook'lardaki
   beklenen çıktılarda hangi satırın sabit hangisinin değişken olduğu tek tek
   yazılıdır.

Çıktılarda geçen terimler (TTFT, ITL, p95, cosine, L2 norm…) ve **hangi değeri
görünce ne düşünmeniz gerektiği**: [docs/glossary.md](docs/glossary.md).

## Nereden başlamalı — işletim sisteminizi seçin

Her runbook, testleri **komut + üretmesi gereken birebir çıktı** olarak listeler;
hepsi gerçekten çalıştırılıp doğrulanmıştır, hafızadan yazılmamıştır.

| Kullandığınız sistem | Runbook | Chat betiği |
| --- | --- | --- |
| Linux · macOS · WSL | **[docs/runbook-linux.md](docs/runbook-linux.md)** | `bash/llm-prompt.sh` |
| Windows | **[docs/runbook-windows.md](docs/runbook-windows.md)** | `powershell\Invoke-LlmPrompt.ps1` |

Referans dokümanlar:
[sağlık kontrolü](docs/health-check.md) ·
[chat completions](docs/chat-completions.md) ·
[model keşfi](docs/models.md) ·
[yük testi ve TTFT](docs/loadtest.md) ·
[embeddings](docs/embeddings.md) ·
[rerank](docs/rerank.md) ·
[backend uyumluluğu](docs/compatibility.md) ·
[sorun giderme](docs/troubleshooting.md) ·
[sözlük](docs/glossary.md)

## İçindekiler

| Betik | Çalışma ortamı | API | Ne yapar |
| --- | --- | --- | --- |
| [`bash/llm-check.sh`](bash/llm-check.sh) | Bash 3.2+, `curl`, `jq` *ya da* `python3` | hepsi | **Basit giriş noktası:** erişim, auth, model, chat, UTF-8, streaming — `--full` ile derin kontroller |
| [`powershell/Test-LlmEndpoint.ps1`](powershell/Test-LlmEndpoint.ps1) | PowerShell 5.1 veya 7+ | hepsi | Aynısı; `curl.exe` gerekmez |
| [`bash/llm-prompt.sh`](bash/llm-prompt.sh) | Bash 3.2+, `curl`, `jq` *ya da* `python3` | `/v1/chat/completions` | Tek prompt, isteğe bağlı SSE streaming, token kullanımı / gecikme / tok-s |
| [`powershell/Invoke-LlmPrompt.ps1`](powershell/Invoke-LlmPrompt.ps1) | PowerShell 5.1 veya 7+ | `/v1/chat/completions` | Aynısı; `curl.exe` gerekmez, Windows'ta TLS 1.2 ve UTF-8 sorunlarını çözer |
| [`bash/llm-models.sh`](bash/llm-models.sh) | Bash 3.2+, `curl`, `jq` *ya da* `python3` | `/v1/models` | Ne servis edildiğini listeler, filtreler, doğrular; her modeli yoklayıp gerçekten cevap vereni bulur |
| [`powershell/Get-LlmModels.ps1`](powershell/Get-LlmModels.ps1) | PowerShell 5.1 veya 7+ | `/v1/models` | Aynısı; nesne döndürür, `Where-Object` / `Export-Csv` ile zincirlenir |
| [`python/chat-loadtest.py`](python/chat-loadtest.py) | Python 3.8+ (yalnızca stdlib) | `/v1/chat/completions` | TTFT, ITL, uçtan uca gecikme ve throughput ölçen yük testi; SLO kapısı olarak da kullanılır |
| [`python/embed-test.py`](python/embed-test.py) | Python 3.8+ (yalnızca stdlib) | `/v1/embeddings` | Embed, cosine çiftleri, 7 kontrollük sağlık paketi ve eşzamanlılık benchmark'ı |
| [`python/rerank-test.py`](python/rerank-test.py) | Python 3.8+ (yalnızca stdlib) | `/v1/rerank` | Sorgu–doküman sıralaması, 8 kontrollük sağlık paketi ve throughput benchmark'ı |
| [`examples/mock_server.py`](examples/mock_server.py) | Python 3.8+ (yalnızca stdlib) | hepsi | GPU'suz denemek için sahte OpenAI uyumlu sunucu — `-m error-404` ile tekrarlanabilir HTTP hataları da üretir |
| [`tests/capture_report.py`](tests/capture_report.py) | Python 3.8+ (yalnızca stdlib) | hepsi | Gerçek bir endpoint'e karşı tüm bataryayı çalıştırıp markdown rapor üretir (anahtar maskeli) |
| [`tests/smoke_test.py`](tests/smoke_test.py) | Python 3.8+ (yalnızca stdlib) | — | Yukarıdaki her betiği sahte sunucuya karşı çalıştırır; kurulu olmayan ortamları atlar |

## Nerede test ediliyor?

Üç ayrı katman var; hangisinin neyi doğruladığını bilmek önemli:

| Katman | Nerede | Neye karşı | Ne doğrular |
| --- | --- | --- | --- |
| **1. Smoke** | GitHub Actions: `ubuntu-latest`, `macos-latest`, `windows-latest` + Windows PowerShell 5.1 · her push'ta | Birlikte gelen [sahte sunucu](examples/mock_server.py) | Betiklerin kendisi: parametreler, çıktı biçimi, exit kodları, UTF-8, hata yolları. Hızlı ve tekrarlanabilir |
| **2. Lint** | GitHub Actions: `ubuntu-latest` | — | ShellCheck + PSScriptAnalyzer (error seviyesi) + Python derleme |
| **3. Gerçek backend** | Elle, kendi altyapınızda | Gerçek bir inference sunucusu | Sunucunun gerçekten nasıl davrandığı. Sonuçlar [compatibility.md](docs/compatibility.md#doğrulanmış-gerçek-backend-sonuçları) dosyasına yazılır |

**1. ve 2. katman otomatiktir**; sahte sunucu sayesinde GPU, model ya da ağ
gerekmez, bu yüzden her push'ta çalışabilir. **3. katman elle yapılır**, çünkü
her kurulumun endpoint'i farklıdır — ve asıl sürprizlerin çıktığı yer orasıdır:
sağlık paketinin eşikleri, gerçek bir quantize modelde yanlış alarm verdiği
görüldükten sonra kalibre edildi.

Kendi endpoint'inize karşı çalıştırmak için:

```bash
bash/llm-check.sh -e http://SUNUCU:PORT -k ANAHTAR -m MODEL --full
```

Tüm bataryayı çalıştırıp gözden geçirilecek bir markdown rapor üretmek için:

```bash
python3 tests/capture_report.py --label "vLLM prod" \
  -e http://SUNUCU:PORT -k ANAHTAR -m MODEL -o raporlar/vllm.md
```

Neyin doğrulanıp neyin doğrulanmadığı, madde madde:
**[docs/test-checklist.md](docs/test-checklist.md)**.

## Doğrulandığı ortamlar

Her push'ta tüm paket üç işletim sisteminde koşuyor. Bunlar niyet değil, sonuç:

| Ortam | Bash betikleri | PowerShell betikleri | Python betikleri | Sonuç |
| --- | --- | --- | --- | --- |
| `ubuntu-latest` — Bash 5.x, pwsh 7.6.5, Python 3.14 | ✅ | ✅ | ✅ | 53/53 |
| `macos-latest` — Bash 3.2.57, pwsh 7.6.4, Python 3.14 | ✅ | ✅ | ✅ | 53/53 |
| `windows-latest` — pwsh 7.6.5, Python 3.14 | tasarım gereği atlanır | ✅ | ✅ | 34/34 |
| `windows-latest` — **Windows PowerShell 5.1** | tasarım gereği atlanır | ✅ | ✅ | 34/34 |
| macOS 26.5 yerel — Bash 3.2.57, pwsh 7.6.3, Python 3.9 | ✅ | ✅ | ✅ | 53/53 |

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

bash/llm-check.sh                            # çalışıyor mu? (basit)
bash/llm-check.sh --full                     # ne kadar iyi çalışıyor? (gelişmiş)
bash/llm-models.sh -l                        # ne servis ediliyor?
bash/llm-models.sh --probe                   # hangileri gerçekten cevap veriyor?
bash/llm-prompt.sh "Merhaba, kendini tanıt"
bash/llm-prompt.sh --stream "Bir haiku yaz"
python3 python/chat-loadtest.py -n 20 -c 4   # TTFT / ITL / throughput
python3 python/embed-test.py --suite
python3 python/rerank-test.py --suite
```

```powershell
$env:LLM_ENDPOINT = 'http://127.0.0.1:8899'
$env:LLM_API_KEY  = 'sk-mock'
$env:LLM_MODEL    = 'mock-model'

.\powershell\Test-LlmEndpoint.ps1
.\powershell\Test-LlmEndpoint.ps1 -Full
.\powershell\Get-LlmModels.ps1 -Long
.\powershell\Get-LlmModels.ps1 -Probe
.\powershell\Invoke-LlmPrompt.ps1 "Merhaba, kendini tanıt"
.\powershell\Invoke-LlmPrompt.ps1 "Bir haiku yaz" -Stream
python python\chat-loadtest.py -n 20 -c 4
```

### 2. Gerçek bir endpoint'e karşı

```bash
chmod +x bash/*.sh python/*.py

# 1. önce basit kontrol: buradan geçmiyorsa gerisini denemeye gerek yok
bash/llm-check.sh -e http://10.0.0.10:8000 -k "$MY_KEY" -m Qwen/Qwen2.5-7B-Instruct

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
PASS   batch içinde dim tutarlı               dim=1024
PASS   vektörler L2-normalize                 norms=1.000000, 1.000000, 1.000000
PASS   çağrılar arası deterministik           max|delta|=0.000e+00 cos=1.00000000
PASS   cos(paraphrase) > cos(alakasız)        para=0.7412 alakasız=0.2688 fark=0.4724
PASS   cos(aynı metin) ~= 1.0                 cos=1.00000000
PASS   batch pozisyonu vektörü değiştirmiyor  cos(pos0)=1.00000000 cos(pos3)=1.00000000
PASS   uzun girdi (~264000 karakter) işlendi  sessizce truncate edildi, prompt_tokens=8192
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
| `LLM_RERANK_MODEL` | `rerank-test.py` | `-m` (`LLM_MODEL`'den önceliklidir) |

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

Sağlık kontrolü betikleri:

| | `llm-check.sh` | `Test-LlmEndpoint.ps1` |
| --- | --- | --- |
| Basit mod (6 kontrol) | ✅ | ✅ |
| Gelişmiş mod | ✅ `--full` | ✅ `-Full` |
| Tek satır çıktı | ✅ `-q` | ✅ `-Quiet` |
| Hata varsa exit 1 | ✅ | ✅ |

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
PASS  python: TTFT, ITL'den ayrı ölçülüyor       ttft_p50=407ms itl_p50=12ms (sunucu 400ms prefill + 10ms chunk)
PASS  python: sağlık paketi                      PASS   batch içinde dim tutarlı               dim=128
...
53 geçti, 0 başarısız, 0 atlandı/uyarı
```

Kurulu olmayan çalışma ortamları `FAIL` değil `SKIP` olarak raporlanır, böylece
aynı dosya her yerde çalışır. CI bunu her push'ta Ubuntu, macOS ve Windows'ta
koşuyor — yukarıdaki platform iddiaları test ediliyor, varsayılmıyor.

## Yol haritası

- [x] `/v1/models` keşif yardımcısı — [docs/models.md](docs/models.md)
- [x] Chat için TTFT'li yük testi — [docs/loadtest.md](docs/loadtest.md)
- [x] Basit/gelişmiş iki seviyeli sağlık kontrolü — [docs/health-check.md](docs/health-check.md)
- [x] Reranker endpoint'i (`/v1/rerank`) sağlık kontrolleri — [docs/rerank.md](docs/rerank.md)
- [ ] Function calling ve structured output uyumluluk testleri
- [ ] Python'suz Windows makineleri için yerel PowerShell embeddings betiği

## Katkı

Issue ve PR'lar açığa — özellikle
[docs/compatibility.md](docs/compatibility.md) içindekilerden farklı davranan bir
backend gördüyseniz. Kısa kurallar: [CONTRIBUTING.md](CONTRIBUTING.md).

## Lisans

[MIT](LICENSE)
