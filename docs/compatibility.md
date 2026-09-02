# Backend uyumluluğu

Buradaki her şey düz OpenAI HTTP'si konuşur — bearer auth, `/v1/chat/completions`,
`/v1/models` ve `/v1/embeddings` — yani bu yüzeyi uygulayan her şeyin çalışması
beklenir. Bu sayfa, insanları takan backend'e özgü ayrıntıları toplar.

> **Doğrulama durumu.** CI, betikleri Ubuntu, macOS ve Windows üzerinde birlikte
> gelen sahte sunucuya karşı çalıştırır. Aşağıdaki tablolardaki notlar, her
> backend'e karşı otomatik bir matristen değil, ilgili projelerin API yüzeyinden
> derlenmiştir — **bir istisnayla:** aşağıdaki "gerçek backend" bölümü elle
> çalıştırılmış, doğrulanmış sonuçlardır. Bir sunucu sizde farklı davranıyorsa
> lütfen issue açın; bu dosya tam olarak bu bildirimleri toplamak için var.

## Doğrulanmış gerçek backend sonuçları

### llama.cpp (`server-vulkan`, Qwen3-30B-A3B GGUF) — 2026-09-01

Chat endpoint'i, sağlık kontrolünün altı kontrolünü de geçti:

```
PASS  erişim            HTTP 200 · 1 model listeleniyor
PASS  kimlik doğrulama  bearer token kabul edildi
PASS  model             listede var
PASS  chat              yanıt geldi · 6 token · finish=stop
PASS  UTF-8             geçerli · "çğışöü"
PASS  streaming         7 chunk · 107ms
```

Yük testi (10 istek, 2 eşzamanlı, `max_tokens=64`):

```
Throughput  2.2 istek/s · 138.0 çıktı token/s
TTFT  (ms)  ort=57 p50=42 p90=85 p95=86 p99=86 maks=86
ITL   (ms)  ort=13.8 p50=13.7 p95=15.4 maks=17.3
E2E   (ms)  ort=926 p50=911 p95=956 p99=956 maks=956
```

Doğrulanan davranışlar:

| Gözlem | Sonuç |
| --- | --- |
| `model` alanı yok sayılıyor | ✅ Doğrulandı. Var olmayan bir model adıyla istek attık, sunucu **normal bir yanıt döndürdü**. Tek modelli sunucularda `--has` chat çağrısından daha bilgilendiricidir |
| `/v1/models` içinde `max_model_len` yok | ✅ `CONTEXT` sütunu `-` gösteriyor; context limitini listeden öğrenemezsiniz |
| Bearer token zorunlu değil | ✅ `--api-key` verilmemişse herhangi bir değer (ya da hiç) kabul ediliyor. Betikler yine de bir anahtar ister — `-k dummy` geçin |
| Türkçe karakterler | ✅ Prompt ve yanıt bozulmadan gidip geliyor |

### llama.cpp embeddings (Qwen3-Embedding GGUF) — 2026-09-01

```
PASS   batch içinde dim tutarlı               dim=1024
PASS   vektörler L2-normalize                 norms=1.000000, 1.000000, 1.000000
PASS   çağrılar arası deterministik           max|delta|=0.000e+00 cos=1.00000000
PASS   cos(paraphrase) > cos(alakasız)        para=0.8112 alakasız=0.1998 fark=0.6113
PASS   cos(aynı metin) ~= 1.0                 cos=0.99991462
UYARI  batch pozisyonu vektörü değiştirmiyor  cos(pos0)=0.99993394 cos(pos3)=0.99983813  (quantize/batch kaynaklı sapma, pratikte önemsiz)
UYARI  uzun girdi (~264000 karakter) işlendi  sunucu reddetti (HTTP 400) - ingestion tarafında chunk'lama gerekir

5/7 geçti · 2 uyarı  (dim=1024, ilk çağrı 131ms, prompt_tokens=55)
```

Buradan çıkan iki pratik sonuç:

1. **Quantize edilmiş modeller bit-bit deterministik değildir.** `cos=0.9999`
   civarındaki sapmalar normaldir ve RAG sonuçlarını değiştirmez; sağlık paketi
   bu yüzden bunları `FAIL` değil `UYARI` sayar. Sapma `cos < 0.999` seviyesine
   inerse gerçek bir sorun vardır.
2. **Bu sunucu uzun girdiyi sessizce kırpmıyor, 400 döndürüyor.** Yani
   ingestion hattınızın kendi chunk'lama koruması olmalı — aksi halde uzun
   dokümanlar sessizce değil, gürültülü biçimde kaybolur.

Bu bölüm, sağlık paketinin eşiklerini gerçek dünyaya göre kalibre etmemizi
sağladı: ilk koşumda üç kontrol `FAIL` veriyordu, oysa sapmalar pratikte
önemsizdi.



### llama.cpp rerank (Qwen3-Reranker-0.6B) — 2026-09-02

llama.cpp sunucusu `--reranking --pooling rank` ile `/rerank` ve `/v1/rerank`
uçlarını açıyor; ayrı bir yığın (TEI, Infinity) gerekmiyor.

```
PASS   her doküman puanlandı                    4 doküman gönderildi, 4 sonuç döndü
PASS   index'ler geçerli ve benzersiz           index'ler=[1, 3, 2, 0]
PASS   sonuçlar skora göre azalan sıralı        skorlar=0.9999, 0.0407, 0.0007, 0.0002
PASS   ilgili doküman ilk sırada                ilk=index 1 · fark=0.9592
PASS   çağrılar arası deterministik             sıra aynı=evet max|delta|=0.000e+00
PASS   doküman sırası sonucu değiştirmiyor      ters sırada da aynı doküman ilk=evet · skor farkı=0.000e+00
PASS   top_n uygulanıyor                        top_n=2 için 2 sonuç döndü
UYARI  uzun doküman (~132000 karakter) işlendi  sunucu reddetti (HTTP 500) - chunk'lama gerekir

7/8 geçti · 1 uyarı
```

| Gözlem | Sonuç |
| --- | --- |
| Yanıt biçimi | `{"model", "object", "usage", "results": [{"index", "relevance_score"}]}` — Cohere/Jina biçimi |
| Skor aralığı | 0–1. Türkçe sondaj setinde ilgili doküman **0.9999**, kısmen ilgili 0.0407, alakasız 0.0002 — **fark 0.96**, sahte sunucudaki 0.08'in çok üstünde |
| Uzun girdi | ✅ Reddediyor ama **HTTP 500** ile, 4xx ile değil. Ingestion tarafında chunk'lama şart |
| Determinizm | ✅ Birebir (max\|delta\|=0) — chat modelinin aksine batch etkisi yok |

### LiteLLM gateway — 2026-09-02

Dokuz alias'ın hepsi erişilebilir: chat, embedding, rerank, STT (whisper), TTS,
bir RAG servisi ve gerçek OpenAI'ye giden bir model.

| Gözlem | Sonuç |
| --- | --- |
| Sağlık kontrolü | `7/10 geçti · 3 uyarı · endpoint sağlıklı` — uyarılar beklenen: chat dışı modeller (embedding, rerank, STT, TTS) `--probe`'da 4xx döner |
| `model` alanı | ⚠️ **Gateway alias'ı geri yansıtıyor.** `qwen3-14b` isteyip 30B'ye yönlendirildiğinizde bile yanıtta `qwen3-14b` yazıyor — bu alan gateway'in arkasını **göstermez** |
| Rerank yanıtı | LiteLLM Cohere biçimine çeviriyor: `{"id", "results", "meta"}` — `model` alanı yok, `usage` yerine `meta.billed_units` |
| `/v1/models` | Alias'ları listeliyor; `CONTEXT` sütunu boş (gateway yayınlamıyor) |
| Ses zinciri | TTS ile üretilen sesi Whisper'a geri okuttuk: *"Merhaba dünya bu bir testtir."* — ikisi de gateway üzerinden çalışıyor |

## Chat (`/v1/chat/completions`)

| Backend | Tipik temel URL | `model` değeri | Auth | Notlar |
| --- | --- | --- | --- | --- |
| **vLLM** | `http://host:8000` | HF repo id ya da `--served-model-name` | `--api-key` (yoksa herhangi bir token) | Referans hedef. `GET /v1/models` gerçekte ne servis edildiğini söyler; `/metrics` altında Prometheus metrikleri var |
| **SGLang** | `http://host:30000` | servis edilen model adı | opsiyonel | OpenAI uyumlu router ve sunucu |
| **llama.cpp** (`llama-server`) | `http://host:8080` | herhangi bir metin — tek model servis eder | `--api-key` | `model` alanını yok sayar; yönlendirmeyi değil taşımayı test etmek istediğinizde kullanışlı |
| **TGI** (Messages API) | `http://host:8080` | çoğunlukla düz `tgi` | bearer | OpenAI uyumlu chat TGI 1.4'ten beri var; eski sürümlerde yalnızca `/generate` |
| **Ollama** | `http://host:11434` | `llama3.1:8b` (tag dahil) | yok sayılır — herhangi bir token gönderin | Uyumluluk katmanı `/v1` altında; betikler *bir* anahtar ister, `-k ollama` geçin |
| **LM Studio** | `http://host:1234` | uygulamada görünen id | yok sayılır | Dizüstünde denemek için pratik |
| **OpenAI** | `https://api.openai.com` | `gpt-4o-mini`, … | gerçek anahtar | Aşağıdaki `max_tokens` uyarısına bakın |
| **LiteLLM / gateway'ler** | `https://gw.example.com` | sanal model alias'ınız | sanal anahtar | Path öneki çalışır: `https://gw.example.com/team-a/v1` |
| **Azure OpenAI** (klasik) | `https://x.openai.azure.com/openai/deployments/...` | deployment adı | `api-key` **başlığı** | ✗ Desteklenmiyor: URL biçimi ve başlık farklı. Önüne bir gateway koyun ya da bearer kabul eden yeni Azure yüzeyini kullanın |

## Embeddings (`/v1/embeddings`)

| Backend | Tipik temel URL | Notlar |
| --- | --- | --- |
| **vLLM** (embedding modeli) | `http://host:8000` | Bir embedding modeli servis edin, ör. `vllm serve BAAI/bge-m3` |
| **TEI** (text-embeddings-inference) | `http://host:8080` | Hem kendi `/embed` yüzeyini hem OpenAI uyumlu `/v1/embeddings` sunar |
| **Infinity** | `http://host:7997` | OpenAI uyumlu, tek süreçte birden çok model destekler |
| **Ollama** | `http://host:11434` | `nomic-embed-text` gibi bir embedding modeliyle `/v1/embeddings` |
| **OpenAI** | `https://api.openai.com` | `text-embedding-3-small/large`, `dimensions` destekler |

## Rerank (`/v1/rerank`)

| Backend | Notlar |
| --- | --- |
| **vLLM** | `vllm serve BAAI/bge-reranker-v2-m3`; `/rerank`, `/v1/rerank` ve `/v2/rerank` |
| **TEI** | Sequence-classification reranker'ları; yerel `/rerank` ve Cohere uyumlu yol |
| **Infinity** | Embedding ve rerank aynı süreçte |
| **Jina / Cohere / Voyage** | Bulut; `relevance_score` 0–1 arası |
| **Ollama** | Rerank endpoint'i yok |

`/v1/rerank` bir OpenAI standardı değil, Cohere'in başlattığı yaygın bir biçim;
yanıt şekilleri farklılaşabilir. Ayrıntı: [rerank.md](rerank.md).

## Model listeleri (`/v1/models`)

| Backend | Listede ne olur |
| --- | --- |
| **vLLM** | Servis edilen model ve `max_model_len` — `--served-model-name` doğru mu, en hızlı kontrol |
| **llama.cpp** | Yüklü tek model; chat'te `model` alanı yok sayıldığı için tek dürüst kaynak listedir |
| **Ollama** | Çekilmiş tag'ler (`llama3.1:8b`). Herhangi bir token kabul edilir ama gönderilmelidir |
| **TGI** | Çoğunlukla `tgi` adında tek kayıt |
| **LiteLLM / gateway'ler** | Upstream adlar değil, sizin alias'larınız. Bir alias listede olup route edilmemiş olabilir — `llm-models.sh --probe` bunu yakalar |
| **OpenAI** | Anahtarınızın gördüğü her şey; yoklamadan önce filtreleyin |

Bunları okuyan yardımcı: [models.md](models.md).

## "OpenAI uyumlu" olmak neyi garanti etmez

Gerçekten olay çıkaranlar bunlar. Bu depodaki betikler her birini görünür kılmak
için tasarlandı.

1. **`max_tokens` ve `max_completion_tokens`.** OpenAI'nin yeni reasoning
   modelleri `max_tokens` parametresini reddeder. Buradaki betikler `max_tokens`
   gönderir; yukarıda listelenen self-hosted sunucuların hepsi bunu kabul eder,
   ama yeni bir OpenAI reasoning modeline yapılan çağrı 400 ile `max_completion_tokens`
   kullanmanızı söyleyecektir. Bu araç seti önce self-hosted inference'ı hedefler.
2. **`temperature: 0` determinizm değildir.** Continuous batching, isteğinizin
   aynı anda gelen diğer isteklerle birlikte hesaplanması demektir ve kayan nokta
   toplama sırası batch bileşimiyle değişir. *Neredeyse* aynı bekleyin, birebir aynı değil.
3. **Streaming'de `usage`.** Sunucuların çoğu, istemci
   `stream_options: {"include_usage": true}` göndermedikçe SSE chunk'larında
   `usage` döndürmez. Token muhasebesi için bloklayan modu kullanın.
4. **Embedding'ler normalize olmayabilir.** vLLM, TEI ve Infinity çoğu model için
   normalize eder ama bu evrensel değildir — `--suite` varsaymak yerine söyler.
5. **Sessiz truncation.** `max-model-len` üzerinde bazı sunucular kırpıp yine de
   vektör döner, bazıları 4xx verir. İkisi de savunulabilir; fark, ingestion
   hattınızın kendi chunk'lama koruması gerekip gerekmediğini belirler.
6. **`model` alanı dekoratif olabilir.** Tek modelli sunucular alanı tamamen yok
   sayar; gateway'de 404 verecek bir yazım hatası yerelde mutlu mesut cevap
   döndürür. Doğrudan bir sunucuda `--raw | jq .model` bunu gösterir; **bir
   gateway'in arkasındaysanız göstermez** — LiteLLM istediğiniz alias'ı geri
   yansıtır (2026-09-02'de ölçüldü).
7. **`dimensions` yok sayılabilir.** Parametreyi kabul edip tam genişlikte vektör
   dönen bir sunucu, küçük genişlikte kurulmuş bir index'i sessizce bozar.

## Hiçbir backend olmadan denemek

[`examples/mock_server.py`](../examples/mock_server.py) dosyası `/v1/models`,
`/v1/chat/completions` (bloklayan + SSE) ve `/v1/embeddings` (float + base64)
uçlarını deterministik sahte embedding'lerle uygular — bu depodaki her kod
yolunu, sağlık paketi dahil, çalıştırmaya yeter.

```bash
python3 examples/mock_server.py --port 8899 --delay 0.2 -v
```

`--delay` yapay gecikme ekler (streaming yolunu gözle görmek için birebir),
`--no-auth` bearer kontrolünü kapatır, `-v` her isteği loglar. Model adı
`error-404` gibi olan istekler o status ile yanıtlanır.
