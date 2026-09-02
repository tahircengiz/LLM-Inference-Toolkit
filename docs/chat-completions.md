# Chat completions

İki betik, tek iş: `/v1/chat/completions` adresine bir prompt gönderip ne
döndüğünü tam olarak göstermek.

| | Linux / macOS / WSL | Windows |
| --- | --- | --- |
| Betik | [`bash/llm-prompt.sh`](../bash/llm-prompt.sh) | [`powershell/Invoke-LlmPrompt.ps1`](../powershell/Invoke-LlmPrompt.ps1) |
| Gerekenler | `curl` + (`jq` ya da `python3`) | PowerShell 5.1 dışında hiçbir şey |

İkisi de aynı endpoint biçimlerini kabul eder, aynı ortam değişkenlerini okur ve
asistan mesajını **stdout**'a, tanılamayı **stderr**'e yazar — yani
`llm-prompt.sh "..." > yanit.txt` komutu `-v` açıkken bile temiz bir dosya verir.

---

## `bash/llm-prompt.sh`

```
Kullanim: llm-prompt.sh [secenekler] "prompt"

  -e, --endpoint URL     Temel URL, .../v1 ya da tam .../v1/chat/completions
                         (env: LLM_ENDPOINT)
  -k, --api-key KEY      Bearer token (env: LLM_API_KEY)
  -m, --model AD         Model adi (env: LLM_MODEL)
  -s, --system METIN     System prompt
  -t, --temperature N    Varsayilan 0.0
  -n, --max-tokens N     Varsayilan 512
      --timeout N        Toplam istek zaman asimi (saniye), varsayilan 300
      --stream           Token'lari geldikce yazdir (SSE)
      --raw              Tam JSON yanitini yazdir
  -i, --insecure         TLS dogrulamasini atla (self-signed endpoint)
  -v, --verbose          Token kullanimi, gecikme ve tok/s bilgisini stderr'e yaz
  -h, --help             Bu metin
```

Prompt parametre, pipe ya da dosya olarak verilebilir:

```bash
llm-prompt.sh "Merhaba"
echo "Merhaba" | llm-prompt.sh
llm-prompt.sh < prompt.txt
llm-prompt.sh -- "--tire-ile-baslayan-bir-metin"
```

### Taşınabilirlik

Betik **Bash 3.2**'yi hedefler (macOS'un getirdiği sürüm) ve GNU'ya özel
davranışlardan kaçınır; böylece aynı dosya BusyBox container'ında, BSD makinede
ya da WSL'de de çalışır:

- Geçen süre önce `$EPOCHREALTIME` (Bash 5), sonra GNU `date +%s%N`, sonra
  `python3`, en sonda tam saniye üzerinden hesaplanır — BSD `date`'in çözemediği
  ham `%N` asla çıktıya sızmaz.
- SSE akışı `grep --line-buffered | sed -u` yerine `awk` + `fflush()` ile
  ayrıştırılır; bu GNU parametreleri GNU dışı sistemlerde yoktur.
- `jq` varsa kullanılır, yoksa istek gövdesini kuran ve yanıtı ayrıştıran
  `python3`'e düşülür. İkisinden biri yeterlidir.

---

## `powershell/Invoke-LlmPrompt.ps1`

```powershell
.\Invoke-LlmPrompt.ps1 [-Prompt] <string>
                       [-Endpoint <string>] [-ApiKey <string>] [-Model <string>]
                       [-SystemPrompt <string>] [-Temperature <double>]
                       [-MaxTokens <int>] [-TimeoutSec <int>]
                       [-Stream] [-Raw] [-Insecure] [-Verbose]
```

**Kısa biçimler Bash betiğiyle aynıdır** — `-e`, `-k`, `-m`, `-s`, `-t`, `-n`,
`-i` doğrudan çalışır ve PowerShell parametre adları büyük/küçük harf duyarsızdır:

```powershell
.\Invoke-LlmPrompt.ps1 "Merhaba" -e http://10.0.0.10:8000 -k sk-xxx -m qwen -n 64
.\Invoke-LlmPrompt.ps1 "Merhaba" -endpoint http://10.0.0.10:8000 -apikey sk-xxx -model qwen
```

Sayısal parametreler doğrulanır: `-Temperature` 0–2, `-MaxTokens` ≥ 1,
`-TimeoutSec` ≥ 1. Aralık dışı bir değer, istek gönderilmeden önce net bir
hatayla reddedilir.

Windows PowerShell 5.1, OpenAI uyumlu çağrıları iki noktada bozar; betik ikisini
de ele alır:

1. **TLS.** 5.1 bazı makinelerde SSL3/TLS1.0 ile anlaşmaya çalışır. Betik ilk
   istekten önce `ServicePointManager.SecurityProtocol` değerine TLS 1.2 ekler.
2. **Kodlama.** 5.1 gövdeyi ISO-8859-1 olarak gönderir ve `charset` belirtmeyen
   bir yanıtı da aynı şekilde çözer — *Türkçe* böylece *TÃ¼rkÃ§e* olur. Betik
   `[Text.Encoding]::UTF8.GetBytes(...)` ile gönderir ve `RawContentStream`'i
   açıkça UTF-8 olarak çözer.

`-Insecure`, 5.1'de `ServerCertificateValidationCallback`'e, 7+ sürümlerinde
`-SkipCertificateCheck`'e (streaming sırasında HttpClient doğrulayıcısına) karşılık gelir.

> **Not** — streaming `HttpClient` kullanır, çünkü `Invoke-WebRequest` yanıtın
> tamamını tamponlayıp öyle döner. CI'da hem PowerShell 7 (Ubuntu, macOS,
> Windows) hem Windows PowerShell 5.1 üzerinde doğrulanıyor; 5.1'de
> `System.Net.Http` gerektiğinde yüklenir.

`.ps1` dosyaları UTF-8 **BOM** ile saklanır: 5.1, BOM olmadan dosyayı sistem kod
sayfasıyla okur ve kaynaktaki Türkçe metinleri bozar.

---

## `-v` / `-Verbose` çıktısını okumak

```
prompt=14 completion=128 total=142 | 2.31s | 55.4 tok/s | finish=stop
```

| Alan | Anlamı |
| --- | --- |
| `prompt` / `completion` / `total` | Sunucunun `usage` alanında bildirdiği token sayıları |
| `2.31s` | **İstemci tarafı duvar saati**: kuyruk + prefill + decode + ağ |
| `55.4 tok/s` | `completion_tokens ÷ geçen süre` |
| `finish` | `stop` = model kendi bitirdi · `length` = `max_tokens`'a çarptı · `content_filter` = yukarıda engellendi |

İki dürüst uyarı:

- **Bu bir benchmark değildir.** Sayı, ağ gidiş-dönüşünü ve isteğin başka
  isteklerin arkasında kuyrukta beklediği süreyi içerir. Yük altındaki gerçek
  rakamlar için [yük testi](loadtest.md) betiğini kullanın; o TTFT ve ITL'yi
  ayrı ayrı ölçer.
- **Streaming modunda token sayısı yazılmaz.** Sunucuların çoğu, istemci
  `stream_options: {"include_usage": true}` göndermedikçe SSE chunk'larında
  `usage` döndürmez; bu betik onu göndermez. Token muhasebesi için bloklayan
  modu kullanın.

---

## Tarifler

**Modeli çağırmadan önce var olduğunu doğrulayın** (bkz. [models.md](models.md))

```bash
llm-models.sh --has "$LLM_MODEL" || { echo "$LLM_ENDPOINT üzerinde model yok"; exit 1; }
llm-prompt.sh "..."
```

**İki modeli aynı prompt'la karşılaştırın**

```bash
for m in Qwen/Qwen2.5-7B-Instruct meta-llama/Llama-3.1-8B-Instruct; do
  echo "== $m"
  llm-prompt.sh -m "$m" -v "KV cache'i tek cümleyle açıkla." 2>&1
done
```

**Bir prompt dosyasını çalıştırıp sadece yanıtları saklayın**

```bash
while IFS= read -r p; do
  printf '%s\t%s\n' "$p" "$(llm-prompt.sh "$p")"
done < promptlar.txt > yanitlar.tsv
```

**Deploy sonrası soğuk başlangıcı ölçün** (ilk çağrı ağırlıkları yükler)

```bash
time llm-prompt.sh -n 1 "hi" >/dev/null
```

**Gateway'in gerçekte nereye yönlendirdiğini görün**

```bash
llm-prompt.sh --raw "hi" | jq '{model, id, system_fingerprint}'
```

**Tekrarlanabilir üretim** — `-t 0` zaten varsayılandır; ancak temperature 0,
batch'li GPU sunucularında birebir aynı çıktının garantisi değildir
([uyumluluk](compatibility.md#openai-uyumlu-olmak-neyi-garanti-etmez)).

---

## Exit kodları

| Kod | Anlamı |
| --- | --- |
| `0` | Başarılı — asistan mesajı yazıldı |
| `1` | Eksik/geçersiz parametre, bağlantı hatası, 2xx olmayan HTTP status ya da ayrıştırılamayan gövde |

2xx olmayan durumlarda yanıt gövdesi olduğu gibi stderr'e yazılır; yani sadece
kodu değil, sunucunun kendi hata mesajını da görürsünüz.
