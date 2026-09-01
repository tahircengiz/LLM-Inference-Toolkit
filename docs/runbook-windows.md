# Test runbook'u — Windows / PowerShell

Aşağıdaki her test **gerçekten çalıştırılmış ve doğrulanmıştır**: komut, yazmanız
gerekenin aynısıdır ve beklenen çıktı, sahte sunucuya karşı yapılan gerçek bir
koşumdan birebir kopyalanmıştır. Koşumlar arasında meşru olarak değişen şeyler
(gecikme, tok/s) her testin altında ayrıca belirtilir.

Linux / macOS / WSL kullanıyorsanız: [runbook-linux.md](runbook-linux.md).

## Doğrulanmış ortamlar

| Ortam | PowerShell | Python | Sonuç |
| --- | --- | --- | --- |
| `windows-latest` (CI, Windows Server) | 7.6.5 | 3.14.7 | ✅ 27/27 (Bash testleri tasarım gereği atlanır) |
| macOS üzerinde PowerShell 7.6.3 (yerel) | 7.6.3 | 3.9.6 | ✅ |
| Windows PowerShell 5.1 | 5.1 | — | ⚠️ destekleniyor, CI kapsamında değil — bildirimlere açığız |

CI, Windows'ta genellikle yanlış giden şeyi doğruluyor: yanıt temiz UTF-8 olarak
geliyor, yani `çğışöüÇĞİŞÖÜ` gidiş-dönüşten sağ çıkıyor.

`.ps1` dosyaları UTF-8 **BOM** ile saklanır; PowerShell 5.1 BOM olmadan dosyayı
sistem kod sayfasıyla okur ve kaynaktaki Türkçe metinleri bozar.

## Hazırlık

```powershell
git clone https://github.com/tahircengiz/LLM-Inference-Toolkit.git
cd LLM-Inference-Toolkit

# 1. pencere - aşağıdaki beklenen değerleri üreten sahte sunucu
python examples\mock_server.py --port 8899

# 2. pencere
$env:LLM_ENDPOINT    = 'http://127.0.0.1:8899'
$env:LLM_API_KEY     = 'sk-mock'
$env:LLM_MODEL       = 'mock-model'
$env:LLM_EMBED_MODEL = 'mock-model'
```

Betik başlamıyorsa:

```powershell
Unblock-File .\powershell\Invoke-LlmPrompt.ps1
# ya da her çağrıda:
powershell -ExecutionPolicy Bypass -File .\powershell\Invoke-LlmPrompt.ps1 "Merhaba"
```

Testleri tek tek yerine hepsini birden çalıştırmak için:

```powershell
python tests\smoke_test.py     # beklenen: 27 geçti, 0 başarısız, 1 atlandı
```

Atlanan, Bash betiğidir — Windows'ta PowerShell olanı kullanılır.

---

## Basit kontroller

Tek komut, öğrenilecek parametre yok. "Endpoint çalışıyor mu?" sorusunun yanıtı.

### B1 — Sağlık kontrolü

```powershell
.\powershell\Test-LlmEndpoint.ps1
```

```
Endpoint  http://127.0.0.1:8899/v1
Model     mock-model

PASS  erişim            HTTP 200 · 3 model listeleniyor
PASS  kimlik doğrulama  bearer token kabul edildi
PASS  model             listede var
PASS  chat              yanıt geldi · 16 token · finish=stop
PASS  UTF-8             geçerli · "Merhaba! Bu bir mock yanittir - Türkçe kar"
PASS  streaming         10 chunk · 315ms

Sonuç: 6/6 geçti · 0 uyarı · endpoint sağlıklı (0.4s)
```

**Geçti sayılır:** exit `0` · altı satırın altısı da `PASS` · son satırda
`endpoint sağlıklı`.
**Değişen:** streaming süresi, toplam süre ve UTF-8 satırındaki yanıt önizlemesi.

Her kontrolün ne sorduğu: [health-check.md](health-check.md#basit-altı-kontrol-tek-komut).

### B2 — Gelişmiş mod

```powershell
.\powershell\Test-LlmEndpoint.ps1 -Full
```

```
UYARI model yoklama     1/3 model cevap verdi (detay: Get-LlmModels.ps1 -Probe)
PASS  embeddings        7/7 geçti  (dim=128, ilk çağrı 5ms, prompt_tokens=36)
PASS  yük               10/10 istek · TTFT p95 67ms · 66 token/s

Sonuç: 8/9 geçti · 1 uyarı · endpoint sağlıklı (2.7s)
```

**Geçti sayılır:** exit `0` · basit kontrollerin altı satırı + üç gelişmiş satır ·
`model yoklama` **UYARI** — çünkü sahte sunucu bilerek çalışmayan bir model
yayınlıyor; gerçek bir endpoint'te `3/3 model cevap verdi` beklenir.
**Değişen:** bütün zaman değerleri.

`UYARI` exit kodunu değiştirmez; yalnızca `FAIL` değiştirir. Embeddings satırı
`LLM_EMBED_MODEL` tanımlı değilse ya da `python` bulunamazsa atlanır.

### B3 — Tek satır (zamanlanmış görev / CI)

```powershell
pwsh -NoProfile -File .\powershell\Test-LlmEndpoint.ps1 -Quiet
$LASTEXITCODE
```

```
Sonuç: 6/6 geçti · 0 uyarı · endpoint sağlıklı (0.4s)
0
```

**Geçti sayılır:** **tam olarak bir satır** çıktı ve exit `0`.

### B4 — Sorunlu endpoint'ler

```powershell
pwsh -NoProfile -File .\powershell\Test-LlmEndpoint.ps1 -Model olmayan-model -Quiet
$LASTEXITCODE
pwsh -NoProfile -File .\powershell\Test-LlmEndpoint.ps1 -Endpoint http://127.0.0.1:9 -Quiet
$LASTEXITCODE
```

```
Sonuç: 5/6 geçti · 1 hata · 0 uyarı · endpoint SAĞLIKSIZ (0.3s)
1
Sonuç: endpoint erişilemiyor · http://127.0.0.1:9/v1
1
```

Yanlış anahtarla (yalnızca doğru anahtarı kabul eden bir sunucuya karşı):

```
FAIL  erişim            HTTP 401
FAIL  kimlik doğrulama  Authorization başlığı eksik ya da hatalı
...
Sonuç: 0/6 geçti · 4 hata · 2 uyarı · endpoint SAĞLIKSIZ (0.0s)
```

**Geçti sayılır:** üç senaryoda da exit `1` · bağlantı kurulamadığında betik
gerisini denemeden duruyor · 401 hem `erişim` hem `kimlik doğrulama` satırında
görünüyor. Çıktı Bash betiğiyle satır satır aynıdır.

---

## Gelişmiş kontroller

Buradan aşağısı, bir sorunun nerede olduğunu bulmak ya da rakam üretmek için.

## Chat completions

### W01 — Tanılamalı bloklayan istek

```powershell
.\powershell\Invoke-LlmPrompt.ps1 "Merhaba, kendini tanıt" -Verbose
```

```
VERBOSE: POST http://127.0.0.1:8899/v1/chat/completions
VERBOSE: Body: {"model":"mock-model","messages":[{"role":"user","content":"Merhaba, kendini tanıt"}],"temperature":0.0,"max_tokens":512,"stream":false}
Merhaba! Bu bir mock yanittir - Türkçe karakter testi: çğışöüÇĞİŞÖÜ
VERBOSE: prompt=5 completion=16 total=21 | 0.02s | 1004.7 tok/s | finish=stop
```

**Geçti sayılır:** exit `0` · yanıt stdout'ta · `finish=stop` · Türkçe karakterler
bozulmamış. Usage satırı Türkçe locale'li bir makinede bile ondalık ayırıcı olarak
`.` kullanır — `InvariantCulture` ile biçimlendirildiği için çıktı ayrıştırılabilir kalır.
**Değişen:** `0.02s` ve `1004.7 tok/s` değerleri.

> `$LASTEXITCODE` yalnızca harici programlar için ayarlanır. Bu betiğin exit
> kodunu görmek için `pwsh -NoProfile -File .\powershell\Invoke-LlmPrompt.ps1 ...`
> şeklinde çalıştırıp ardından `$LASTEXITCODE` okuyun.

### W02 — Streaming (SSE)

```powershell
.\powershell\Invoke-LlmPrompt.ps1 "Merhaba" -Stream
```

```
Merhaba! Bu bir mock yanittir - Türkçe karakter testi: çğışöüÇĞİŞÖÜ
```

**Geçti sayılır:** exit `0` · metin **parça parça**, kelime kelime beliriyor
(net görmek için sahte sunucuyu `--delay 0.2` ile başlatın) · `data:` öneki yok ·
usage satırı yok — sunucular streaming sırasında onu göndermez.

Streaming, yanıtın tamamını tamponlayan `Invoke-WebRequest` yerine `HttpClient`
kullanır. CI'da üç işletim sisteminde de PowerShell 7 üzerinde doğrulanıyor;
5.1'de `System.Net.Http` gerektiğinde yüklenir.

### W03 — Ham JSON

```powershell
.\powershell\Invoke-LlmPrompt.ps1 "Merhaba" -Raw | ConvertFrom-Json |
    Select-Object model, @{n='finish';e={$_.choices[0].finish_reason}}, @{n='total';e={$_.usage.total_tokens}}
```

```
model      finish total
-----      ------ -----
mock-model stop      17
```

**Geçti sayılır:** exit `0` · geçerli JSON · `model` istediğiniz model — sizi
sessizce başka yere yönlendiren bir gateway'i böyle yakalarsınız.

### W04 — System prompt ve örnekleme parametreleri

```powershell
.\powershell\Invoke-LlmPrompt.ps1 "Merhaba" -SystemPrompt "Kısa cevap ver" -Temperature 0.2 -MaxTokens 64
```

```
Merhaba! Bu bir mock yanittir - Türkçe karakter testi: çğışöüÇĞİŞÖÜ
```

**Geçti sayılır:** exit `0`. `-Verbose` ekleyip gövdede `system` mesajını,
`"temperature":0.2` ve `"max_tokens":64` değerlerini doğrulayın. (Sahte sunucu
örneklemeyi yok sayar; gerçek model saymaz.)

### W05 — Endpoint normalizasyonu

```powershell
.\powershell\Invoke-LlmPrompt.ps1 "ping" -Endpoint 'http://127.0.0.1:8899'
.\powershell\Invoke-LlmPrompt.ps1 "ping" -Endpoint 'http://127.0.0.1:8899/v1'
.\powershell\Invoke-LlmPrompt.ps1 "ping" -Endpoint 'http://127.0.0.1:8899/v1/chat/completions'
```

**Geçti sayılır:** üçü de aynı yanıtı basar ve exit `0` verir. Gateway path öneki
(`https://gw.example.com/team-a/v1`) korunur.

### W06 — HTTP hatası yutulmuyor, gösteriliyor

```powershell
pwsh -NoProfile -File .\powershell\Invoke-LlmPrompt.ps1 "x" -Model error-404
$LASTEXITCODE
```

```
HTTP 404 from http://127.0.0.1:8899/v1/chat/completions

{
  "error": {
    "message": "'error-404' modeli için enjekte edilmiş hata",
    "type": "injected_error",
    "code": null
  }
}
1
```

**Geçti sayılır:** exit `1` · sunucunun kendi hata gövdesi **stderr**'de ·
stdout boş. İlk satır Bash betiğiyle karakter karakter aynıdır; altındaki gövdeyi
PowerShell 7 kendi biçimlendirir (betik, PS'in eklediği `\uXXXX` kaçışlarını
çözerek Türkçe mesajı okunur tutar). `error-<status>` biçimindeki her model adı
çalışır (`error-401`, `error-429`, `error-500`).

### W07 — Eksik yapılandırma hemen hata veriyor

```powershell
$env:LLM_MODEL = ''
pwsh -NoProfile -File .\powershell\Invoke-LlmPrompt.ps1 "x"
$LASTEXITCODE
$env:LLM_MODEL = 'mock-model'   # geri al
```

```
-Model parametresi gerekli (ya da $env:LLM_MODEL ayarlayın).
1
```

**Geçti sayılır:** hiç ağ isteği yapılmadan exit `1` ve tek satırlık temiz bir
stderr mesajı — PowerShell'in çok satırlı hata bloğu yok.

---

## Model keşfi

### W08 — Ne servis edildiğini listele

```powershell
.\powershell\Get-LlmModels.ps1
```

```
mock-model
mock-embed
error-503
```

**Geçti sayılır:** exit `0` · satır başına bir id, sunucunun kendi sırasıyla.
Sahte sunucu bilerek üç model yayınlar, biri çalışmaz — W11'i tekrarlanabilir
kılan da bu.

### W09 — Metadata tablosu

```powershell
.\powershell\Get-LlmModels.ps1 -Long
```

```
Model      Sahip Olusturulma          Context
-----      ----- -----------          -------
mock-model mock  2025-01-01T00:00:00Z 8192
mock-embed mock  2025-03-01T00:00:00Z 512
error-503  mock  -                    -
```

**Geçti sayılır:** exit `0` · zaman damgaları UTC ISO-8601, `InvariantCulture` ile
biçimlendirildiği için tr-TR bir makinede de aynı metin · sunucunun yayınlamadığı
her alanda `-`.
**Değişen:** hiçbir şey. Bu çıktı her makinede byte-byte aynıdır.

`-Long` **nesne** döndürür; keşif böylece PowerShell'in geri kalanıyla zincirlenir:

```powershell
.\powershell\Get-LlmModels.ps1 -Long |
    Where-Object { $_.Context -ne '-' -and [int]$_.Context -ge 1024 } |
    Select-Object Model, Context
```

```
Model      Context
-----      -------
mock-model 8192
```

### W10 — Altdizi filtresi

```powershell
.\powershell\Get-LlmModels.ps1 mock-embed
```

```
mock-embed
```

**Geçti sayılır:** exit `0` · büyük/küçük harf duyarsız eşleşme · eşleşme yoksa
`'<desen>' desenine uyan model yok` ile exit `1`.

### W11 — Yoklama: hangi modeller gerçekten cevap veriyor?

```powershell
pwsh -NoProfile -File .\powershell\Get-LlmModels.ps1 -Probe
$LASTEXITCODE
```

```
Model      Status Ms Not
-----      ------ -- ---
mock-model ok      2
mock-embed 400     3 bu model chat completions desteklemiyor
error-503  503     1 'error-503' modeli için enjekte edilmiş hata
1/3 model cevap verdi
1
```

**Geçti sayılır:** exit `1` — çünkü yayınlanan modellerden biri hata veriyor,
testin amacı da bu · her model için bir satır · `Not` sütununda **sunucunun kendi**
hata mesajı · `n/n model cevap verdi` özeti stderr'e gider, böylece tablo
yönlendirildiğinde temiz kalır.
**Değişen:** `Ms` sütunu.

Embedding modelindeki `400` doğru davranıştır, arıza değil. Her yoklama gerçek
bir `max_tokens: 1` isteğidir; ücretli gateway'de önce filtreleyin:
`.\powershell\Get-LlmModels.ps1 -Probe qwen`.

### W12 — Model varlığını doğrula (CI kapısı)

```powershell
pwsh -NoProfile -File .\powershell\Get-LlmModels.ps1 -Has mock-model
$LASTEXITCODE
pwsh -NoProfile -File .\powershell\Get-LlmModels.ps1 -Has olmayan-model
$LASTEXITCODE
```

```
0
'olmayan-model' modeli http://127.0.0.1:8899/v1/models tarafından servis edilmiyor
1
```

**Geçti sayılır:** başarıda sessiz, bulamazsa stderr'e tek satır ve exit `1`.
Eşleşme birebir ve büyük/küçük harf duyarlıdır — sunucu da öyle eşleştirir.

### W13 — Ham JSON

```powershell
.\powershell\Get-LlmModels.ps1 -Json | ConvertFrom-Json | Select-Object -ExpandProperty data | Select-Object -First 1
```

```
id            : mock-model
object        : model
created       : 1735689600
owned_by      : mock
max_model_len : 8192
```

**Geçti sayılır:** exit `0` · sunucudan gelen geçerli JSON.

---

## Yük testi

Yük testi Python'dur ve her işletim sisteminde aynı şekilde çalışır; ayrı bir
PowerShell sürümü yoktur. `python3` yerine `python` (ya da `py -3`) kullanın.

### W14 — TTFT, ITL ve throughput

```powershell
python python\chat-loadtest.py -n 12 -c 4
```

```
Yük testi   model=mock-model · stream=açık · max_tokens=128
Yük         12 istek · eşzamanlılık 4 · ısınma 1

Sonuç       12 istek · 12 başarılı · 0 hata (%0.0)
Süre        1.03s
Throughput  11.7 istek/s · 116.6 çıktı token/s

TTFT  (ms)  ort=68 p50=69 p90=71 p95=71 p99=72 maks=72
ITL   (ms)  ort=26.6 p50=28.1 p95=30.3 maks=30.9
E2E   (ms)  ort=333 p50=334 p95=347 p99=350 maks=350
Çıktı token ort=10.0 · toplam=120
```

**Geçti sayılır:** exit `0` · `12 istek · 12 başarılı · 0 hata` · **TTFT belirgin
biçimde ITL'den büyük** (sahte sunucu ilk token'dan önce üç chunk gecikmesi
bekler, bu ölçümün doğruluğunun kanıtıdır).
**Değişen:** bütün zaman değerleri.

### W15 — SLO kapısı

```powershell
python python\chat-loadtest.py -n 6 -c 2 --max-ttft-p95 2000
$LASTEXITCODE
python python\chat-loadtest.py -n 6 -c 2 --max-ttft-p95 10
$LASTEXITCODE
```

```
SLO         TTFT p95 72ms <= 2000ms ✓
0
SLO ihlali: TTFT p95 73ms > 10ms
1
```

**Geçti sayılır:** bütçe içindeyken exit `0`, aşıldığında stderr'e tek satır ve
exit `1`.

### W16 — Diğer modlar

```powershell
python python\chat-loadtest.py -n 8 -c 4 --no-stream       # TTFT ölçülmez, E2E ölçülür
python python\chat-loadtest.py --duration 60 -c 16         # sayı yerine süre
python python\chat-loadtest.py -n 100 -c 16 --csv sonuc.csv --json > ozet.json
python python\chat-loadtest.py -n 4 -c 2 -m error-503      # hata dökümü, exit 1
```

Beklenen çıktılar Linux runbook'undaki
[L16–L18](runbook-linux.md#yük-testi) ile birebir aynıdır; sayıların nasıl
okunacağı [loadtest.md](loadtest.md) sayfasında.

---

## Embeddings

Embeddings betiği de Python'dur ve her işletim sisteminde aynı davranır:

```powershell
python python\embed-test.py "Kubernetes GPU node etiketleme"
python python\embed-test.py --pair "GPU node nasıl etiketlenir?" "K8s'te GPU sunucuya label"
python python\embed-test.py --suite
python python\embed-test.py --bench 64 --concurrency 8 --batch-size 8
python python\embed-test.py --dimensions 64 --encoding-format base64 "merhaba"
python python\embed-test.py -m error-503 "x"
```

Her birinin beklenen çıktısı ve kontrollerin neyi koruduğu
[runbook-linux.md § Embeddings](runbook-linux.md#embeddings) sayfasında — değerler
birebir aynıdır. CI, sağlık paketinin Windows, Ubuntu ve macOS'ta **aynı cosine
değerlerini** (`para=0.2634 alakasız=-0.0635`) ürettiğini doğruladı.

Konsolda Türkçe karakterler bozuk görünüyorsa (dosyada düzgünse) oturum başına
bir kez:

```powershell
[Console]::OutputEncoding = [Text.Encoding]::UTF8
```

Python betikleri kendi çıktılarını zaten UTF-8'e sabitler; bu ayar PowerShell
betiklerinin çıktısı içindir.

---

## Gerçek bir endpoint'e karşı

```powershell
$env:LLM_ENDPOINT    = 'http://10.0.0.10:8000'
$env:LLM_API_KEY     = $env:MY_KEY
$env:LLM_MODEL       = 'Qwen/Qwen2.5-7B-Instruct'
$env:LLM_EMBED_MODEL = 'BAAI/bge-m3'
```

Ardından B1–B4 ve W01–W16'yı tekrarlayın. Beklentiler Linux runbook'undaki
[gerçek endpoint tablosuyla](runbook-linux.md#gerçek-bir-endpointe-karşı) aynıdır.

Windows'a özgü dikkat edilecekler:

| Belirti | Sebep | Çözüm |
| --- | --- | --- |
| *Could not create SSL/TLS secure channel* | Windows PowerShell 5.1 TLS 1.2 altına düşüyor | Betik TLS 1.2'yi zaten zorluyor. Devam ediyorsa endpoint TLS 1.3 istiyordur → PowerShell 7 kullanın |
| *The remote certificate is invalid* | İç CA güvenilmiyor | Lab endpoint'i için `-Insecure`, ya da CA'yı `Cert:\LocalMachine\Root` altına kurun |
| Çıktıda `TÃ¼rkÃ§e` | Yanıt değil, konsol kod sayfası | `[Console]::OutputEncoding = [Text.Encoding]::UTF8` |
| Betikteki Türkçe metinler bozuk | `.ps1` BOM'suz kaydedilmiş | UTF-8 BOM ile kaydedin (bu depodakiler öyle) |
| Kurumsal ağdan takılıyor | Proxy | .NET sistem proxy'sini kullanır — `netsh winhttp show proxy` ile bakın, iç host'ları bypass edin |
| Betik çalışmıyor | Execution policy | `Unblock-File` ya da `-ExecutionPolicy Bypass` |
