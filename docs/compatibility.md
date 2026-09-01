# Backend uyumluluğu

Buradaki her şey düz OpenAI HTTP'si konuşur — bearer auth, `/v1/chat/completions`,
`/v1/models` ve `/v1/embeddings` — yani bu yüzeyi uygulayan her şeyin çalışması
beklenir. Bu sayfa, insanları takan backend'e özgü ayrıntıları toplar.

> **Doğrulama durumu.** CI, betikleri Ubuntu, macOS ve Windows üzerinde birlikte
> gelen sahte sunucuya karşı çalıştırır. Aşağıdaki notlar, her backend'e karşı
> otomatik bir matristen değil, ilgili projelerin API yüzeyinden derlenmiştir.
> Bir sunucu sizde farklı davranıyorsa lütfen issue açın — bu dosya tam olarak
> bu bildirimleri toplamak için var.

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
   döndürür. Önem taşıyorsa `--raw | jq .model` ile kontrol edin.
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
