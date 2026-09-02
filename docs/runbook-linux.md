# Test runbook'u — Linux / macOS / WSL

Aşağıdaki her test **gerçekten çalıştırılmış ve doğrulanmıştır**: komut, yazmanız
gerekenin aynısıdır ve beklenen çıktı, sahte sunucuya karşı yapılan gerçek bir
koşumdan birebir kopyalanmıştır. Koşumlar arasında meşru olarak değişen şeyler
(gecikme, tok/s) her testin altında ayrıca belirtilir.

Windows kullanıyorsanız: [runbook-windows.md](runbook-windows.md).
Çıktılardaki terimler için: [sözlük](glossary.md).

**Her test aynı düzendedir:**

> **Komut** → yazacağınız satır
> **Çıktı** → görmeniz gereken
> **Geçti sayılır** → neye bakarak "tamam" diyeceğiniz
> **Değişen** → koşumdan koşuma farklılaşacak kısımlar (genelde süreler)

## Doğrulanmış ortamlar

| Ortam | Kabuk | Python | curl / jq | Sonuç |
| --- | --- | --- | --- | --- |
| macOS 26.5.2 (yerel) | Bash 3.2.57 | 3.9.6 | curl 8.7.1 / jq 1.7.1 | ✅ 64/64 |
| `ubuntu-latest` (CI) | Bash 5.x | 3.14.7 | curl 8.5.0 / jq 1.7 | ✅ 64/64 |
| `macos-latest` (CI) | Bash 3.2.57 | 3.14.6 | curl 8.7.1 / jq 1.8.2 | ✅ 64/64 |

Bash 3.2 bilinçli bir hedef: macOS'un getirdiği sürüm o, orada çalışan her şey
modern Linux'ta da çalışır.

## Hazırlık

```bash
git clone https://github.com/tahircengiz/LLM-Inference-Toolkit.git
cd LLM-Inference-Toolkit
chmod +x bash/*.sh python/*.py

# 1. terminal - aşağıdaki beklenen değerleri üreten sahte sunucu
python3 examples/mock_server.py --port 8899

# 2. terminal
export LLM_ENDPOINT=http://127.0.0.1:8899
export LLM_API_KEY=sk-mock
export LLM_MODEL=mock-model
export LLM_EMBED_MODEL=mock-embed
export LLM_RERANK_MODEL=mock-rerank
```

Testleri tek tek yerine hepsini birden çalıştırmak için:

```bash
python3 tests/smoke_test.py          # beklenen: 64 geçti, 0 başarısız
```

---

## Basit kontroller

Tek komut, öğrenilecek parametre yok. "Endpoint çalışıyor mu?" sorusunun yanıtı.

### B1 — Sağlık kontrolü

```bash
bash/llm-check.sh
```

```
Endpoint  http://127.0.0.1:8899/v1
Model     mock-model

PASS  erişim            HTTP 200 · 4 model listeleniyor
PASS  kimlik doğrulama  bearer token kabul edildi
PASS  model             listede var
PASS  chat              yanıt geldi · 16 token · finish=stop
PASS  UTF-8             geçerli · "Merhaba! Bu bir mock yanittir -…"
PASS  streaming         11 chunk · 322ms

Sonuç: 6/6 geçti · 0 uyarı · endpoint sağlıklı (0.4s)
```

**Geçti sayılır:** exit `0` · altı satırın altısı da `PASS` · son satırda
`endpoint sağlıklı`.
**Değişen:** streaming süresi, toplam süre ve UTF-8 satırındaki yanıt önizlemesi.

Her kontrolün ne sorduğu: [health-check.md](health-check.md#basit-altı-kontrol-tek-komut).

### B2 — Gelişmiş mod

```bash
bash/llm-check.sh --full
```

```
UYARI model yoklama     1/4 model cevap verdi (detay: llm-models.sh --probe)
PASS  embeddings        7/7 geçti  (dim=128, ilk çağrı 6ms, prompt_tokens=36)
PASS  rerank            8/8 geçti  (4 doküman, ilk çağrı 5ms, prompt_tokens=61)
PASS  yük               10/10 istek · TTFT p95 67ms · 65 token/s

Sonuç: 9/10 geçti · 1 uyarı · endpoint sağlıklı (2.6s)
```

**Geçti sayılır:** exit `0` · basit kontrollerin altı satırı + dört gelişmiş satır ·
`model yoklama` **UYARI** — çünkü sahte sunucu bilerek çalışmayan bir model
yayınlıyor; gerçek bir endpoint'te `4/4 model cevap verdi` beklenir.
**Değişen:** bütün zaman değerleri.

`UYARI` exit kodunu değiştirmez; yalnızca `FAIL` değiştirir.

### B3 — Tek satır (cron / CI)

```bash
bash/llm-check.sh -q; echo "exit=$?"
```

```
Sonuç: 6/6 geçti · 0 uyarı · endpoint sağlıklı (0.4s)
exit=0
```

**Geçti sayılır:** **tam olarak bir satır** çıktı ve exit `0`.

### B4 — Sorunlu endpoint'ler

```bash
bash/llm-check.sh -m olmayan-model -q;       echo "exit=$?"
bash/llm-check.sh -e http://127.0.0.1:9 -q;  echo "exit=$?"
```

```
Sonuç: 5/6 geçti · 1 hata · 0 uyarı · endpoint SAĞLIKSIZ (0.5s)
exit=1
Sonuç: endpoint erişilemiyor · http://127.0.0.1:9/v1
exit=1
```

Yanlış anahtarla (yalnızca doğru anahtarı kabul eden bir sunucuya karşı):

```
FAIL  erişim            HTTP 401
FAIL  kimlik doğrulama  Authorization başlığı eksik ya da hatalı
...
Sonuç: 0/6 geçti · 4 hata · 2 uyarı · endpoint SAĞLIKSIZ (0.1s)
```

**Geçti sayılır:** üç senaryoda da exit `1` · bağlantı kurulamadığında betik
gerisini denemeden duruyor · 401 hem `erişim` hem `kimlik doğrulama` satırında
görünüyor.

---

## Gelişmiş kontroller

Buradan aşağısı, bir sorunun nerede olduğunu bulmak ya da rakam üretmek için.

## Chat completions

### L01 — Tanılamalı bloklayan istek

```bash
bash/llm-prompt.sh -v "Merhaba, kendini tanıt"
```

```
POST http://127.0.0.1:8899/v1/chat/completions
{"model":"mock-model","messages":[{"role":"user","content":"Merhaba, kendini tanıt"}],"temperature":0.0,"max_tokens":512,"stream":false}
Merhaba! Bu bir mock yanittir - Türkçe karakter testi: çğışöüÇĞİŞÖÜ
prompt=5 completion=16 total=21 | 0.02s | 941.2 tok/s | finish=stop
```

**Geçti sayılır:** exit `0` · yanıt stdout'ta · `finish=stop` · Türkçe karakterler
bozulmamış (`çğışöüÇĞİŞÖÜ`, `Ã§ÄŸ` değil) · istek satırı ve usage satırı stderr'de.
**Değişen:** `0.02s` ve `941.2 tok/s` değerleri.

### L02 — Streaming (SSE)

```bash
bash/llm-prompt.sh --stream "Merhaba"
```

```
Merhaba! Bu bir mock yanittir - Türkçe karakter testi: çğışöüÇĞİŞÖÜ
```

**Geçti sayılır:** exit `0` · metin **parça parça**, kelime kelime beliriyor
(net görmek için sahte sunucuyu `--delay 0.2` ile başlatın) · çıktıda `data:`
öneki ya da JSON yok · usage satırı yok — sunucular streaming sırasında onu
göndermez.

### L03 — Ham JSON

```bash
bash/llm-prompt.sh --raw "Merhaba" | jq -c '{model, finish: .choices[0].finish_reason, usage}'
```

```json
{"model":"mock-model","finish":"stop","usage":{"prompt_tokens":1,"completion_tokens":16,"total_tokens":17}}
```

**Geçti sayılır:** exit `0` · geçerli JSON · `model` alanı dolu.

`model` alanının ne kadar bilgilendirici olduğu sunucuya bağlıdır: tek modelli
bir sunucu kendi adını döndürür (uydurma bir ad göndersek bile), bir gateway ise
istediğiniz alias'ı geri yansıtır. Ayrıntı:
[chat-completions.md](chat-completions.md#tarifler).

### L04 — stdin'den prompt

```bash
echo "Merhaba" | bash/llm-prompt.sh
```

```
Merhaba! Bu bir mock yanittir - Türkçe karakter testi: çğışöüÇĞİŞÖÜ
```

**Geçti sayılır:** exit `0` · parametre olarak vermekle birebir aynı sonuç.
`bash/llm-prompt.sh < prompt.txt` de çalışır.

### L05 — System prompt ve örnekleme parametreleri

```bash
bash/llm-prompt.sh -s "Kısa cevap ver" -t 0.2 -n 64 "Merhaba"
```

```
Merhaba! Bu bir mock yanittir - Türkçe karakter testi: çğışöüÇĞİŞÖÜ
```

**Geçti sayılır:** exit `0`. Parametrelerin sunucuya gerçekten gittiğini `-v` ile
doğrulayın: gövdede `system` mesajı, `"temperature":0.2` ve `"max_tokens":64`
görünmeli. (Sahte sunucu örneklemeyi yok sayar; gerçek model saymaz.)

### L06 — Endpoint normalizasyonu

```bash
bash/llm-prompt.sh -e http://127.0.0.1:8899                      "ping"
bash/llm-prompt.sh -e http://127.0.0.1:8899/v1                   "ping"
bash/llm-prompt.sh -e http://127.0.0.1:8899/v1/chat/completions  "ping"
```

**Geçti sayılır:** üçü de aynı yanıtı basar ve exit `0` verir. Gateway path öneki
(`https://gw.example.com/team-a/v1`) korunur.

### L07 — HTTP hatası yutulmuyor, gösteriliyor

```bash
bash/llm-prompt.sh -m error-404 "x"; echo "exit=$?"
```

```
HTTP 404 from http://127.0.0.1:8899/v1/chat/completions
{"error": {"message": "'error-404' modeli için enjekte edilmiş hata", "type": "injected_error", "code": null}}
exit=1
```

**Geçti sayılır:** exit `1` · sunucunun kendi hata gövdesi **stderr**'de ·
stdout boş. `error-<status>` biçimindeki her model adı çalışır (`error-401`,
`error-429`, `error-500`) — hattınızın nasıl tepki verdiğini provası için kullanın.

### L08 — Eksik yapılandırma hemen hata veriyor

```bash
LLM_MODEL="" bash/llm-prompt.sh "x"; echo "exit=$?"
```

```
model gerekli (-m ya da $LLM_MODEL)
exit=1
```

**Geçti sayılır:** hiç ağ isteği yapılmadan exit `1`. Eksik endpoint ve anahtar
için de aynısı geçerli.

---

## Model keşfi

### L09 — Ne servis edildiğini listele

```bash
bash/llm-models.sh
```

```
mock-model
mock-embed
mock-rerank
error-503
```

**Geçti sayılır:** exit `0` · satır başına bir id, sunucunun kendi sırasıyla ·
pipe'lanabilir (`bash/llm-models.sh | wc -l`). Sahte sunucu bilerek dört model
yayınlar, biri çalışmaz — L12'yi tekrarlanabilir kılan da bu.

### L10 — Metadata tablosu

```bash
bash/llm-models.sh -l
```

```
MODEL        SAHIP  OLUSTURULMA           CONTEXT
mock-model   mock   2025-01-01T00:00:00Z  8192
mock-embed   mock   2025-03-01T00:00:00Z  512
mock-rerank  mock   2025-03-01T00:00:00Z  512
error-503    mock   -                     -

4 model
```

**Geçti sayılır:** exit `0` · zaman damgaları UTC ISO-8601 (makineden bağımsız) ·
sunucunun yayınlamadığı her alanda `-`. `CONTEXT` sütunu sırasıyla
`max_model_len`, `context_length` ve `max_input_tokens` okur — vLLM'de yürürlükteki
gerçek `--max-model-len` değerini görmenin en hızlı yolu.
**Değişen:** hiçbir şey. Bu çıktı her makinede byte-byte aynıdır.

### L11 — Altdizi filtresi

```bash
bash/llm-models.sh embed
```

```
mock-embed
```

**Geçti sayılır:** exit `0` · id üzerinde büyük/küçük harf duyarsız eşleşme ·
eşleşme yoksa `'<desen>' desenine uyan model yok` ile exit `1`. Yüzlerce alias
yayınlayan gateway'lerde işe yarar.

### L12 — Yoklama: hangi modeller gerçekten cevap veriyor?

```bash
bash/llm-models.sh --probe; echo "exit=$?"
```

```
MODEL        STATUS    LATENCY  NOT
mock-model   ok           11ms
mock-embed   400          11ms  bu model chat completions desteklemiyor
mock-rerank  400          11ms  bu model chat completions desteklemiyor
error-503    503          10ms  'error-503' modeli için enjekte edilmiş hata

1/4 model cevap verdi
exit=1
```

**Geçti sayılır:** exit `1` — çünkü yayınlanan modellerden biri hata veriyor,
testin amacı da bu · her model için bir satır · NOT sütununda **sunucunun kendi**
hata mesajı.
**Değişen:** gecikme sütunu.

Embedding modelindeki `400` doğru davranıştır, arıza değil. Karar vermeden önce
NOT sütununu okuyun. Her yoklama gerçek bir `max_tokens: 1` isteğidir; ücretli
gateway'de önce filtreleyin: `bash/llm-models.sh --probe qwen`.

### L13 — Model varlığını doğrula (CI kapısı)

```bash
bash/llm-models.sh --has mock-model;      echo "exit=$?"
bash/llm-models.sh --has olmayan-model;   echo "exit=$?"
```

```
exit=0
'olmayan-model' modeli http://127.0.0.1:8899/v1/models tarafından servis edilmiyor
exit=1
```

**Geçti sayılır:** başarıda sessiz (`grep -q` gibi), bulamazsa stderr'e tek satır
ve exit `1`. Eşleşme birebir ve büyük/küçük harf duyarlıdır — sunucu da öyle eşleştirir.

```bash
bash/llm-models.sh --has "$LLM_MODEL" || { echo "model yok"; exit 1; }
```

### L14 — Ham JSON

```bash
bash/llm-models.sh --json | jq '.data[0]'
```

```json
{
  "id": "mock-model",
  "object": "model",
  "created": 1735689600,
  "owned_by": "mock",
  "max_model_len": 8192
}
```

**Geçti sayılır:** exit `0` · geçerli JSON. Sunucu ek alanlar yayınlıyorsa
(vLLM `max_model_len` ve `permission` ekler) burada görürsünüz.

---

## Yük testi

### L15 — TTFT, ITL ve throughput

```bash
python3 python/chat-loadtest.py -n 12 -c 4
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

**Geçti sayılır:** exit `0` · `12 istek · 12 başarılı · 0 hata` · TTFT, ITL ve
E2E satırlarının üçü de dolu · **TTFT belirgin biçimde ITL'den büyük**.
**Değişen:** bütün zaman değerleri.

Son madde tesadüf değil: sahte sunucu ilk token'dan önce bilerek bekler
(`--prefill`), sonra her chunk arasında çok daha kısa bir gecikme koyar. Yani
doğru çalışan bir ölçümde TTFT, ITL'nin kat kat üstünde çıkmalıdır.
`tests/smoke_test.py` bunu 400ms prefill + 10ms chunk ayarlı ayrı bir sunucuyla
her koşumda kontrol eder — ölçümün iki metriği birbirine karıştırmadığının kanıtı:

```
PASS  python: TTFT, ITL'den ayrı ölçülüyor       ttft_p50=407ms itl_p50=12ms (sunucu 400ms prefill + 10ms chunk)
```

### L16 — Streaming olmadan

```bash
python3 python/chat-loadtest.py -n 8 -c 4 --no-stream
```

```
TTFT  (ms)  ölçülmedi (--no-stream)
E2E   (ms)  ort=1 p50=1 p95=1 p99=1 maks=1
Çıktı token ort=16.0 · toplam=128
```

**Geçti sayılır:** exit `0` · TTFT satırı ölçülemediğini açıkça söylüyor · E2E
yine raporlanıyor. Bloklayan istemcilerin gördüğü gecikmeyi ölçmek için kullanın.

### L17 — SLO kapısı

```bash
python3 python/chat-loadtest.py -n 6 -c 2 --max-ttft-p95 2000 | tail -1
python3 python/chat-loadtest.py -n 6 -c 2 --max-ttft-p95 10 >/dev/null; echo "exit=$?"
```

```
SLO         TTFT p95 72ms <= 2000ms ✓
SLO ihlali: TTFT p95 73ms > 10ms
exit=1
```

**Geçti sayılır:** bütçe içindeyken exit `0` ve ✓ satırı; aşıldığında stderr'e
tek satır ve exit `1`. `--max-error-rate` varsayılan olarak 0'dır: tek bir
başarısız istek bile exit `1` demektir.

### L18 — Hata dökümü

```bash
python3 python/chat-loadtest.py -n 4 -c 2 -m error-503; echo "exit=$?"
```

```
TTFT  (ms)  ölçülemedi (başarılı istek yok)
Çıktı token ort=0.0 · toplam=0

Hatalar     4× HTTP 503: 'error-503' modeli için enjekte edilmiş hata
exit=1
```

**Geçti sayılır:** exit `1` · hatalar status'a göre gruplanmış ve sunucunun kendi
mesajıyla yazılmış · TTFT satırı "ölçülemedi" ile "ölçülmedi (--no-stream)"
arasındaki farkı doğru söylüyor.

Ayrıntılı kullanım ve bu sayıların nasıl okunacağı: [loadtest.md](loadtest.md).

---

## Embeddings

### E01 — Vektörü incele

```bash
python3 python/embed-test.py "Kubernetes GPU node etiketleme"
```

```
[0] Kubernetes GPU node etiketleme                     dim=128  |v|=1.000000  min=-0.5466 max=+0.4685
     head=[+0.0000, +0.0000, -0.0781, +0.0000, +0.0000, ...]
gecikme=7ms  metin=1  prompt_tokens=7  total_tokens=7
```

**Geçti sayılır:** exit `0` · `dim=128` (sahte sunucu) · `|v|=1.000000`.
**Değişen:** `gecikme`. Gerçek bir modelde `dim` modelin genişliğidir (bge-m3
için 1024, text-embedding-3-small için 1536) ve `head` değerleri çoğunlukla sıfır
yerine yoğun olur.

### E02 — Cosine benzerliği: paraphrase ve alakasız

```bash
python3 python/embed-test.py --pair \
  "Kubernetes cluster'inda GPU node'u nasil etiketlenir?" \
  "K8s uzerinde GPU'lu sunucuya label eklemenin yolu nedir?"

python3 python/embed-test.py --pair \
  "Kubernetes cluster'inda GPU node'u nasil etiketlenir?" \
  "Dun aksam sahilde balik izgara yaptik."
```

```
cosine=0.263365  dim=128  gecikme=8ms
cosine=-0.063540  dim=128  gecikme=8ms
```

**Geçti sayılır:** paraphrase çifti, alakasız çiftten **yüksek** skor alıyor.
Yukarıdaki mutlak değerler sahte sunucuya aittir; gerçek bir retrieval modeli
paraphrase için ~0.7–0.9, alakasız için ~0.1–0.4 verir. **İddia sıralamadır,
değerin kendisi değil.**

### E03 — Sağlık paketi (asıl kapı)

```bash
python3 python/embed-test.py --suite; echo "exit=$?"
```

```
PASS   batch içinde dim tutarlı               dim=128
PASS   vektörler L2-normalize                 norms=1.000000, 1.000000, 1.000000
PASS   çağrılar arası deterministik           max|delta|=0.000e+00 cos=1.00000000
PASS   cos(paraphrase) > cos(alakasız)        para=0.2634 alakasız=-0.0635 fark=0.3269
PASS   cos(aynı metin) ~= 1.0                 cos=1.00000000
PASS   batch pozisyonu vektörü değiştirmiyor  cos(pos0)=1.00000000 cos(pos3)=1.00000000
PASS   uzun girdi (~264000 karakter) işlendi  sessizce truncate edildi, prompt_tokens=66000

7/7 geçti  (dim=128, ilk çağrı 6ms, prompt_tokens=36)
exit=0
```

**Geçti sayılır:** `7/7 geçti` ve exit `0`. Herhangi bir kontrol düşerse exit `1`
olur, yani doğrudan deploy kapısı olarak kullanılabilir:

```bash
python3 python/embed-test.py --suite || { echo "embedding endpoint sağlıksız"; exit 1; }
```

Aynı `cos` değerleri CI'da Ubuntu, macOS ve Windows'ta da üretildi — paket
platformlar arası tekrarlanabilir. Her kontrolün neyi koruduğu:
[embeddings.md](embeddings.md#--suite--bu-model-doğru-bağlanmış-mı).

### E04 — Throughput benchmark

```bash
python3 python/embed-test.py --bench 64 --concurrency 8 --batch-size 8
```

```
istek=8  batch_size=8  eşzamanlılık=8  metin=64
süre=0.11s  throughput=587.7 metin/s  73.5 istek/s
gecikme ms: ort=46 p50=11 p95=108 p99=108 maks=108
```

**Geçti sayılır:** exit `0` · `istek = 64 ÷ 8 = 8` · tüm gecikme yüzdelikleri var.
**Değişen:** bütün sayılar. Sahte sunucuya karşı bunlar loopback'i ve Python'ı
ölçer; kapasite planlaması için yalnızca gerçek endpoint rakamları anlamlıdır.

### E05 — Matryoshka dimensions ve base64

```bash
python3 python/embed-test.py --dimensions 64 --encoding-format base64 "merhaba"
```

```
[0] merhaba                                            dim=64  |v|=1.000000  min=-0.8944 max=+0.1491
     head=[+0.0000, +0.0000, +0.0000, +0.0000, +0.0000, ...]
gecikme=6ms  metin=1  prompt_tokens=1  total_tokens=1
```

**Geçti sayılır:** `dim=64` — sunucu `dimensions` parametresini uyguladı ve
base64 float32 gövdesi doğru çözüldü. `dim` tam genişlikte dönüyorsa sunucu
parametreyi yok saymıştır: bunun çalıştığını varsayarak index kurmayın.

### E06 — Embeddings hata yolu

```bash
python3 python/embed-test.py -m error-503 "x"; echo "exit=$?"
```

```
HTTP 503 from http://127.0.0.1:8899/v1/embeddings
{"error": {"message": "'error-503' modeli için enjekte edilmiş hata", "type": "injected_error", "code": null}}
exit=1
```

**Geçti sayılır:** exit `1` ve sunucunun gövdesi stderr'de.

---

## Rerank

### R1 — Sıralama doğru mu? (basit)

```bash
python3 python/rerank-test.py
```

```
Sorgu   Kubernetes'te GPU node nasıl etiketlenir?
Model   mock-rerank · 4 doküman · 8ms

  #  skor    doküman
  1  0.6338  GPU node etiketlemek için kubectl label komutu kullanılır.
  2  0.5525  Kubernetes cluster'ında pod'lara kaynak limiti tanımlama.
  3  0.5517  Prometheus ile disk doluluk alarmı kurma adımları.
  4  0.4121  Sahilde balık ızgara yapmanın püf noktaları.

Yorum   birinci ile ikinci arasındaki fark 0.0813 — ayrım orta; eşik belirlerken kendi verinizle doğrulayın
```

**Geçti sayılır:** exit `0` · **doğru cevap (`kubectl label` içeren cümle) 1.
sırada** · `Yorum` satırı farkı yorumluyor.
**Değişen:** gecikme. Skorlar sahte sunucuda sabittir; gerçek modelde farklıdır.

Parametresiz çalıştırıldığında yerleşik bir örnek kullanılır: bir soru, bir doğru
cevap, iki alakasız ve bir kısmen ilgili doküman. Kendi verinizle:

```bash
python3 python/rerank-test.py "disk alarmı nasıl kurulur" \
  "Prometheus ile disk doluluk alarmı kurma adımları." \
  "Balık ızgara tarifi." --top-n 2
```

```
  #  skor    doküman
  1  0.7300  Prometheus ile disk doluluk alarmı kurma adımları.
  2  0.4900  Balık ızgara tarifi.

Yorum   birinci ile ikinci arasındaki fark 0.2400 — ayrım net
```

Farkın nasıl yorumlanacağı: [rerank.md](rerank.md#sonucu-nasıl-okumalı).

### R2 — Sağlık paketi (gelişmiş)

```bash
python3 python/rerank-test.py --suite; echo "exit=$?"
```

```
PASS   her doküman puanlandı                    4 doküman gönderildi, 4 sonuç döndü
PASS   index'ler geçerli ve benzersiz           index'ler=[1, 3, 2, 0]
PASS   sonuçlar skora göre azalan sıralı        skorlar=0.6338, 0.5525, 0.5517, 0.4121
PASS   ilgili doküman ilk sırada                ilk=index 1 · fark=0.0813
PASS   çağrılar arası deterministik             sıra aynı=evet max|delta|=0.000e+00
PASS   doküman sırası sonucu değiştirmiyor      ters sırada da aynı doküman ilk=evet · skor farkı=0.000e+00
PASS   top_n uygulanıyor                        top_n=2 için 2 sonuç döndü
PASS   uzun doküman (~132000 karakter) işlendi  sessizce truncate edildi

8/8 geçti  (4 doküman, ilk çağrı 6ms, prompt_tokens=61)
exit=0
```

**Geçti sayılır:** `8/8 geçti` ve exit `0`. Her kontrolün neyi koruduğu:
[rerank.md](rerank.md#gelişmiş---suite). En kritik ikisi **index'ler geçerli**
(yanlış dokümanı bağlama koymanızı engeller) ve **doküman sırası sonucu
değiştirmiyor** (aday listesinin sırası cevabı değiştirmemeli).

### R3 — Throughput

```bash
python3 python/rerank-test.py --bench 24 --concurrency 4 --docs 8
```

```
istek=24  doküman/istek=8  eşzamanlılık=4  toplam doküman=192
süre=0.02s  throughput=1106.5 istek/s  8852 doküman/s
gecikme ms: ort=3 p50=3 p95=7 p99=8 maks=8
```

**Geçti sayılır:** exit `0` · `toplam doküman = istek × doküman/istek`.
**Değişen:** bütün sayılar.

Rerank'te asıl bakılacak sayı **doküman/s**'dir; maliyet doküman sayısıyla
büyür. `--docs` değerini gerçek aday sayınıza eşitleyin.

### R4 — Hata yolu

```bash
python3 python/rerank-test.py -m error-503; echo "exit=$?"
```

```
HTTP 503 from http://127.0.0.1:8899/v1/rerank
{"error": {"message": "'error-503' modeli için enjekte edilmiş hata", "type": "injected_error", "code": null}}
exit=1
```

**Geçti sayılır:** exit `1` ve sunucunun gövdesi stderr'de.

---

## Gerçek bir endpoint'e karşı

Üç değişkeni değiştirip aynı testleri tekrarlayın:

```bash
export LLM_ENDPOINT=http://10.0.0.10:8000
export LLM_API_KEY="$MY_KEY"
export LLM_MODEL=Qwen/Qwen2.5-7B-Instruct
export LLM_EMBED_MODEL=BAAI/bge-m3
export LLM_RERANK_MODEL=BAAI/bge-reranker-v2-m3
```

Sahte sunucunun sabit değerleri yerine beklenecekler:

| Test | Gerçek sunucuda beklenen |
| --- | --- |
| B1 | `6/6 geçti`. Buradan geçmiyorsa gerisini denemeye gerek yok |
| B2 | `model yoklama` satırında `n/n model cevap verdi`; embedding modeli varsa `7/7 geçti` |
| L01 | Gerçek bir yanıt · `finish=stop` (`length` ise `-n` sınırına çarptınız) · tek GPU'da küçük bir model için onlarca–yüzlerce tok/s |
| L02 | Token'lar kademeli beliriyor. Yanıtın tamamı bir anda geliyorsa bir proxy tamponluyordur — [sorun giderme](troubleshooting.md#streaming-hiçbir-şey-yazmıyor) |
| L03 | `model` alanı dolu. Bu alanın gateway'in arkasını göstermediğini unutmayın — alias geri yansıtılır |
| L07 | Bilerek yanlış bir model adı deneyin: sunucunun mesajıyla `HTTP 404` ya da `HTTP 400` bekleyin |
| L09–L10 | Gerçek katalog. vLLM'de `CONTEXT`, deploy ettiğiniz `--max-model-len` ile aynı olmalı — değilse tartışmayı sunucu kazanmış |
| L12 | `n/n model cevap verdi`. Aksi durum ya embedding/reranker modelidir (sorun değil — NOT'u okuyun) ya da bozuk route (sorun) |
| L13 | İlk gerçek istekten önce deploy hattınıza yerleştirin |
| L15 | TTFT p95 kullanıcı deneyiminizin bütçesi olmalı. `-c` artırıp çıktı token/s doyduğu ve TTFT p95'in fırladığı noktayı bulun |
| L17 | Bulduğunuz bütçeyi `--max-ttft-p95` olarak deploy hattına koyun |
| E01 | `dim` modelin gerçek genişliği · çoğu retrieval modelinde `\|v\|` = 1.0 |
| E02 | Paraphrase ≫ alakasız. Dar bir fark, modelin diliniz ya da alanınız için zayıf olduğunu gösterir |
| E03 | `7/7 geçti`. Her FAIL [sorun giderme](troubleshooting.md#sonuçlar-yanlış-görünüyor) sayfasında açıklanıyor — *batch pozisyonu* ve *L2-normalize* düşerse blocker sayın |
| E04 | `--batch-size` değerini throughput artmayı bırakana kadar yükseltin; kuyruk için p95/p99'a bakın |
| R1 | Doğru doküman 1. sırada ve fark ≥ 0.20 olmalı. Dar farkta eşik yerine sabit `top_n` kullanın |
| R2 | `8/8 geçti`. *index'ler geçerli* ve *doküman sırası sonucu değiştirmiyor* düşerse blocker sayın |
| R3 | `--docs` değerini gerçek aday sayınıza eşitleyin; doküman/s kapasitenizi belirler |

Sonuçlarınızı aynı tablo biçiminde kaydedip PR açın — gerçek backend'lerden
gelen doğrulanmış rakamlar tam olarak
[compatibility.md](compatibility.md) dosyasının beklediği şey.
