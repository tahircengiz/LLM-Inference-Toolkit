# Sorun giderme

Belirti → sebep → çözüm. Her betik, 2xx olmayan yanıtlarda sunucunun kendi hata
gövdesini stderr'e yazar; önce onu okuyun.

## HTTP hataları

| Gördüğünüz | Muhtemel sebep | Çözüm |
| --- | --- | --- |
| `HTTP 404` ve HTML gövde | Yanlış path. Endpoint bir önek altında ya da sunucu sandığınız sunucu değil | Temel URL'yi, `.../v1`'i ve tam path'i deneyin — betikler üçünü de normalize eder. `bash/llm-models.sh` ile gerçekte ne olduğuna bakın |
| `HTTP 401` / `authentication_error` | Bearer token eksik ya da yanlış | `-k` / `-ApiKey` veya `LLM_API_KEY`. Ollama değeri yok sayar ama betikler yine de bir anahtar ister — `-k ollama` geçin |
| `HTTP 400` `model ... does not exist` | Model adı sunucunun servis ettiği ad değil | `bash/llm-models.sh` ya da `Get-LlmModels.ps1` ile listeleyin |
| `HTTP 400` ve `max_tokens` uyarısı | `max_completion_tokens` isteyen yeni bir OpenAI reasoning modeli | Self-hosted endpoint kullanın ya da o modeli SDK ile çağırın. Bkz. [uyumluluk](compatibility.md#openai-uyumlu-olmak-neyi-garanti-etmez) |
| Embeddings sunucusundan `HTTP 422` | Girdi `max-model-len`'den uzun ya da desteklenmeyen `dimensions` | Girdiyi chunk'layın; `--dimensions` parametresini kaldırın |
| `HTTP 429` | Rate limit ya da dolu istek kuyruğu | `--concurrency` değerini düşürün; tekrar deneyin |
| Uzun beklemeden sonra `HTTP 500` | Model hâlâ yükleniyor ya da uzun prompt'ta OOM | Sunucu loglarına bakın. Soğuk başlangıç için `--timeout` değerini artırın |

## TLS

| Gördüğünüz | Çözüm |
| --- | --- |
| `curl: (60) SSL certificate problem: self signed certificate` | İç CA'yı trust store'a ekleyin ya da tek seferlik kontrol için `-i` kullanın |
| PowerShell: *Could not create SSL/TLS secure channel* | Betik 5.1'de TLS 1.2'yi zaten zorluyor. Devam ediyorsa endpoint muhtemelen TLS 1.3 istiyor (PowerShell 7 kullanın) ya da istemci sertifikası gerekiyor |
| PowerShell: *The remote certificate is invalid* | `-Insecure`, ya da CA'yı `Cert:\LocalMachine\Root` altına kurun |

`-i` / `-Insecure` doğrulamayı tamamen kapatır. Lab endpoint'i için uygundur,
internetten erişilebilen hiçbir şey için değil.

## Kodlama

| Gördüğünüz | Sebep | Çözüm |
| --- | --- | --- |
| `Türkçe` yerine `TÃ¼rkÃ§e` | Sunucu `charset=utf-8` göndermedi, istemci ISO-8859-1 varsaydı | Buradaki betikler bunu açıkça çözer. Kendi aracınızda görüyorsanız başlığa güvenmek yerine ham byte'ları UTF-8 olarak çözün |
| Terminalde doğru, dosyaya yönlendirince bozuk | Yanıt değil, konsol kod sayfası | Windows'ta: çalıştırmadan önce `[Console]::OutputEncoding = [Text.Encoding]::UTF8`, ya da `-Raw` kullanıp JSON'ı sonradan ayrıştırın |
| Sadece streaming modunda bozulma | Çok baytlı bir karakter iki SSE chunk'ına bölünmüş | Betikler akışı uçtan uca UTF-8 çözer; kendi ayrıştırıcınızı yazdıysanız karakter değil byte tamponlayın |
| PowerShell betiğindeki Türkçe metinler bozuk | `.ps1` dosyası BOM'suz kaydedilmiş; 5.1 onu sistem kod sayfasıyla okuyor | Dosyayı UTF-8 **BOM** ile kaydedin (bu depodaki `.ps1` dosyaları öyle) |
| `The property 'Count' cannot be found on this object` (PowerShell 5.1) | Sunucu tek model döndürdüğünde liste dizi değil tek nesne oluyor; 5.1'de StrictMode skalerde `.Count` erişimini reddediyor | Düzeltildi (2026-09-02). Depoyu güncelleyin: `git pull`. Tek modelli sunucu artık CI'da hem pwsh 7 hem 5.1 ile test ediliyor |
| Python betiği Windows'ta `UnicodeEncodeError` | Konsol cp1252 | Betikler açılışta stdout/stderr'i UTF-8'e sabitler; kendi betiğinizde `sys.stdout.reconfigure(encoding="utf-8")` kullanın |

## Streaming hiçbir şey yazmıyor

1. Sunucu `stream: true` isteğini yok sayıp tek JSON gövdesi döndürmüştür — aynı
   çağrıyı `--raw` ile yapıp bakın.
2. Bir reverse proxy tamponluyordur. nginx'te: `proxy_buffering off;` ve tüm
   üretim süresini kapsayacak kadar yüksek `proxy_read_timeout`.
3. Bash tarafında tamponlayan bir şeyden geçiriyorsunuzdur. Betik zaten `awk` +
   `fflush()` ve `jq --unbuffered` kullanıyor; sona bir `grep` ya da `sed`
   eklemek tamponlamayı geri getirebilir.

## Ortam

| Sorun | Çözüm |
| --- | --- |
| `jq: command not found` | Ölümcül değil — Bash betiği `python3`'e düşer. Biraz daha hızlı JSON için `jq` kurun |
| `curl: command not found` | Bash betiği için gerekli. Windows'ta bunun yerine PowerShell betiğini kullanın; `curl.exe` gerektirmez |
| `.\Invoke-LlmPrompt.ps1 cannot be loaded because running scripts is disabled` | `powershell -ExecutionPolicy Bypass -File .\Invoke-LlmPrompt.ps1 ...` ya da `Unblock-File .\Invoke-LlmPrompt.ps1` |
| `llm-prompt.sh` çalıştırırken `Permission denied` | `chmod +x bash/llm-prompt.sh`, ya da `bash bash/llm-prompt.sh` şeklinde çağırın |
| Yerelde çalışıyor, jump host'tan takılıyor | Proxy değişkenleri. `curl`, `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY` değişkenlerine uyar; .NET sistem proxy'sini kullanır. İç host'ları `NO_PROXY` içine ekleyin |
| İlk çağrı zaman aşımına uğruyor, sonrakiler hızlı | Soğuk başlangıç — ağırlık yükleme, CUDA graph capture. `--timeout` / `-TimeoutSec` değerini artırın |

## Sonuçlar yanlış görünüyor

| Gözlem | Genellikle şu anlama gelir |
| --- | --- |
| `finish=length` ve yarım kalmış yanıt | `max_tokens`'a çarptınız. `-n` / `-MaxTokens` değerini artırın |
| tok/s beklenenden çok düşük | Sayı kuyruk ve ağı içerir. Sunucunun kendi metriklerine bakın, daha yakın bir makineden ölçün, benzeri benzerle karşılaştırın. Yük altındaki gerçek resim için [yük testi](loadtest.md) |
| TTFT yüksek ama ITL normal | Prefill ya da kuyruk sorunu: prompt uzun, ya da istek başkalarının arkasında bekliyor. Eşzamanlılığı düşürüp tekrar ölçün |
| ITL yüksek ama TTFT normal | Decode yavaş: model bu donanım için büyük, ya da batch çok kalabalık |
| `--bench` / yük testi throughput'u GPU boşken doyuyor | Darboğaz sunucu değil istemci. Daha güçlü bir makineden ya da paralel birkaç makineden çalıştırın |
| `--suite`: **vektörler L2-normalize FAIL** | Model normalize edilmemiş vektör döndürüyor. Dot product'ı cosine gibi kullanmadan önce istemcide normalize edin; yoksa sıralamaya vektör büyüklüğü hakim olur |
| `--suite`: **batch pozisyonu vektörü değiştirmiyor FAIL** | Sunucuda pooling/padding hatası. Batch'le indexlenen dokümanlar tek tek embed edilen sorgularla eşleşmez — bunu blocker sayın |
| `--suite`: **cos(paraphrase) > cos(alakasız) FAIL** | Ya yanlış model yüklü ya da bu bir retrieval modeli değil. Karar vermeden önce kendi alanınızdan cümlelerle deneyin |
| `--probe`: model listede ama 400 dönüyor | Embedding/reranker modeline chat isteği atmış olabilirsiniz — NOT sütunundaki sunucu mesajını okuyun |

## Hâlâ takıldıysanız

Önce sahte sunucuya karşı tekrarlayın:

```bash
python3 examples/mock_server.py --port 8899 -v
python3 tests/smoke_test.py -v
```

Smoke test geçip kendi endpoint'iniz başarısız oluyorsa fark sunucu tarafındadır
— ve ikisinin `-v` çıktısı bir issue'ya eklenecek en iyi şeydir.
