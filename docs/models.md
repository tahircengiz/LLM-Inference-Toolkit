# Model keşfi — `/v1/models`

`GET /v1/models`, bir inference endpoint'ine sorabileceğiniz en ucuz sorudur ve
"neden çalışmıyor" ticket'larının çoğunu daha açılmadan kapatır: *çağırmak
üzere olduğum şey gerçekten orada mı ve cevap veriyor mu?*

| | Linux / macOS / WSL | Windows |
| --- | --- | --- |
| Betik | [`bash/llm-models.sh`](../bash/llm-models.sh) | [`powershell/Get-LlmModels.ps1`](../powershell/Get-LlmModels.ps1) |
| Gerekenler | `curl` + (`jq` ya da `python3`) | PowerShell 5.1 dışında hiçbir şey |

İkisi de chat betikleriyle aynı endpoint biçimlerini kabul eder, aynı
`LLM_ENDPOINT` / `LLM_API_KEY` değişkenlerini okur ve aynı durumlarda **aynı exit
kodunu** verir.

---

## `bash/llm-models.sh`

```
Kullanim: llm-models.sh [secenekler] [desen]

  desen                  Model id'sinde buyuk/kucuk harf duyarsiz altdizi filtresi

  -e, --endpoint URL     Temel URL, .../v1 ya da tam .../v1/models
  -k, --api-key KEY      Bearer token
  -l, --long             Tablo: id, owned_by, created, context uzunlugu
      --json             Ham JSON yanitini yazdir
      --has MODEL        Yalnizca MODEL birebir servis ediliyorsa exit 0
      --probe            Listedeki her modele 1 token'lik chat istegi gonderir
      --timeout N        Istek zaman asimi (saniye), varsayilan 60
  -i, --insecure         TLS dogrulamasini atla
  -v, --verbose          Istek URL'sini stderr'e yaz
  -h, --help             Bu metin
```

## `powershell/Get-LlmModels.ps1`

```powershell
.\Get-LlmModels.ps1 [[-Pattern] <string>]
                    [-Endpoint <string>] [-ApiKey <string>]
                    [-Long] [-Json] [-Has <string>] [-Probe]
                    [-TimeoutSec <int>] [-Insecure] [-Verbose]
```

PowerShell sürümü metin değil **nesne** döndürür; keşif böylece kabuğun geri
kalanıyla zincirlenir:

```powershell
.\powershell\Get-LlmModels.ps1 -Long | Where-Object { $_.Context -ne '-' -and [int]$_.Context -ge 1024 }
.\powershell\Get-LlmModels.ps1 -Long | Export-Csv modeller.csv -NoTypeInformation
```

---

## Yanıtladığı dört soru

### 1. Ne servis ediliyor?

```bash
llm-models.sh          # id'ler, satır başına bir tane - pipe'lanabilir
llm-models.sh -l       # id, sahip, oluşturulma, context uzunluğu
```

Context sütunu sırasıyla `max_model_len` (vLLM), `context_length` ve
`max_input_tokens` alanlarını okur; hiçbiri yayınlanmıyorsa `-` gösterir. Bunu
baştan bilmek, bir ingestion koşusunun yarısında 400 almanızı engeller.

### 2. *Benim* modelim servis ediliyor mu? (deploy kapısı)

```bash
llm-models.sh --has "Qwen/Qwen2.5-7B-Instruct" || {
    echo "$LLM_ENDPOINT üzerinde model yok"; exit 1
}
```

Başarıda sessizdir, hatada stderr'e tek satır yazıp exit 1 verir — tam olarak
`grep -q` biçimi, yani doğrudan CI'ya girer. Eşleşme **birebir ve büyük/küçük
harf duyarlıdır**, çünkü sunucu da öyle eşleştirir.

### 3. Hangileri gerçekten cevap veriyor?

```bash
llm-models.sh --probe
```

```
MODEL       STATUS    LATENCY  NOT
mock-model  ok           16ms
mock-embed  400          17ms  bu model chat completions desteklemiyor
error-503   503          17ms  'error-503' modeli için enjekte edilmiş hata

1/4 model cevap verdi
```

Listeleme bir iddiadır, garanti değil. Gateway'ler rutin olarak route edilmemiş,
anahtarı yanlış ya da zaten chat modeli olmayan model adları yayınlar. `--probe`
her modele `max_tokens: 1` ile bir istek atıp ne döndüğünü yazar; biri bile hata
verirse exit 1 olur, yani deploy sonrası kontrol olarak kullanılabilir.

İki nokta:

- **Token harcar.** Model başına küçücük bir istek, ama 50 alias'lı ücretli bir
  gateway'de 50 faturalı çağrı demektir. Önce filtreleyin:
  `llm-models.sh --probe qwen`.
- **400 her zaman arıza değildir.** Embedding ve reranker modelleri chat
  isteklerini haklı olarak reddeder; NOT sütunu sunucunun kendi açıklamasını
  taşır, ikisini oradan ayırt edersiniz.

### 4. Ham yanıt neye benziyor?

```bash
llm-models.sh --json | jq '.data[0]'
```

Sunucu ek alanlar yayınlıyorsa işe yarar — vLLM `max_model_len` ve `permission`
ekler, bazı gateway'ler yönlendirme bilgisi koyar.

---

## Exit kodları

İki betikte de aynı:

| Kod | Anlamı |
| --- | --- |
| `0` | Listeleme başarılı · `--has` modeli buldu · `--probe` ve tüm modeller cevap verdi |
| `1` | Eksik parametre, bağlantı hatası, 2xx olmayan status, ayrıştırılamayan gövde, filtreye uyan model yok, `--has` bulamadı ya da `--probe` en az bir hata gördü |

---

## Backend notları

| Backend | `/v1/models` ne döndürür |
| --- | --- |
| **vLLM** | Servis edilen model ve `max_model_len` — `--served-model-name` doğru mu, en hızlı buradan görülür |
| **llama.cpp** (`llama-server`) | Yüklü tek model. Chat isteğinde `model` alanı tamamen yok sayıldığı için `--has` chat çağrısından daha bilgilendiricidir |
| **Ollama** | Çekilmiş tag'ler (`llama3.1:8b`). Herhangi bir bearer token kabul edilir ama gönderilmesi gerekir |
| **TGI** | Çoğunlukla `tgi` adında tek kayıt |
| **LiteLLM / gateway'ler** | Upstream model adları değil, sizin sanal alias'larınız. Bir alias listede olup route edilmemiş olabilir — `--probe` tam da bunu yakalar |
| **OpenAI** | Anahtarınızın görebildiği tüm katalog; uzun olur, önce filtreleyin |

Sadece "endpoint çalışıyor mu?" diye soruyorsanız
[sağlık kontrolü](health-check.md) tek komutta bu betiği de çağırır.

Doğrulanmış komut–çıktı çiftleri runbook'larda:
[Linux](runbook-linux.md#model-keşfi) · [Windows](runbook-windows.md#model-keşfi).
