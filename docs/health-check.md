# Sağlık kontrolü — basit ve gelişmiş

Bu depodaki testler iki seviyede kullanılabilir:

| | Soru | Komut | Süre |
| --- | --- | --- | --- |
| **Basit** | "Bu endpoint çalışıyor mu?" | `llm-check.sh` / `Test-LlmEndpoint.ps1` | ~1 sn |
| **Gelişmiş** | "Ne kadar iyi çalışıyor, nerede bozuluyor?" | `--full`, sonra tek tek özel betikler | ~5 sn – dakikalar |

Basit seviye tek komuttur, öğrenilecek parametresi yoktur ve `0` / `1` exit
kodu döndürür. Gelişmiş seviye aynı betiğin `--full` modu ve altındaki
uzmanlaşmış betiklerdir.

| | Linux / macOS / WSL | Windows |
| --- | --- | --- |
| Betik | [`bash/llm-check.sh`](../bash/llm-check.sh) | [`powershell/Test-LlmEndpoint.ps1`](../powershell/Test-LlmEndpoint.ps1) |
| Gerekenler | `curl` + (`jq` ya da `python3`) | PowerShell 5.1 dışında hiçbir şey |

---

## Basit: altı kontrol, tek komut

```bash
llm-check.sh
```

```
Endpoint  http://127.0.0.1:8899/v1
Model     mock-model

PASS  erişim            HTTP 200 · 4 model listeleniyor
PASS  kimlik doğrulama  bearer token kabul edildi
PASS  model             listede var
PASS  chat              yanıt geldi · 16 token · finish=stop
PASS  UTF-8             geçerli · "Merhaba! Bu bir mock yanittir - Türkçe k"
PASS  streaming         11 chunk · 322ms

Sonuç: 6/6 geçti · 0 uyarı · endpoint sağlıklı (0.4s)
```

Ne kontrol ediliyor ve neden:

| Kontrol | Yanıtladığı soru |
| --- | --- |
| **erişim** | Sunucu ayakta mı, `/v1/models` cevap veriyor mu? Bağlantı kurulamıyorsa burada durur — gerisini denemenin anlamı yok |
| **kimlik doğrulama** | Bearer token kabul edildi mi? 401/403 burada görünür |
| **model** | Çağıracağınız model gerçekten listede mi? Yanlış model adı, en sık görülen 400 sebebidir |
| **chat** | Gerçek bir istek gerçek bir yanıt döndürüyor mu? Token sayısı ve `finish_reason` da yazılır |
| **UTF-8** | Yanıt bozulmadan geliyor mu? Türkçe bir prompt gönderilir ve yanıtta U+FFFD (bozuk karakter) aranır |
| **streaming** | SSE çalışıyor mu, kaç chunk geliyor? Araya giren bir proxy tamponluyorsa burada belli olur |

**Exit kodu:** hepsi geçtiyse `0`, en az bir `FAIL` varsa `1`. `UYARI` exit
kodunu değiştirmez — örneğin `/v1/models` uygulamayan tek modelli bir sunucu
uyarı üretir ama sağlıksız sayılmaz.

### Cron / CI için

```bash
llm-check.sh -q || echo "endpoint sorunlu" | mail -s "LLM alarm" ekip@example.com
```

```
Sonuç: 6/6 geçti · 0 uyarı · endpoint sağlıklı (0.4s)
```

`-q` / `-Quiet` yalnızca son satırı yazar; exit kodu aynıdır.

---

## Gelişmiş: `--full`

Aynı komut, üç ağır kontrol eklenmiş hali:

```bash
llm-check.sh --full
```

```
PASS  erişim            HTTP 200 · 4 model listeleniyor
PASS  kimlik doğrulama  bearer token kabul edildi
PASS  model             listede var
PASS  chat              yanıt geldi · 16 token · finish=stop
PASS  UTF-8             geçerli · "Merhaba! Bu bir mock yanittir - Türkçe k"
PASS  streaming         11 chunk · 332ms

UYARI model yoklama     1/4 model cevap verdi (detay: llm-models.sh --probe)
PASS  embeddings        7/7 geçti  (dim=128, ilk çağrı 6ms, prompt_tokens=36)
PASS  rerank            8/8 geçti  (4 doküman, ilk çağrı 5ms, prompt_tokens=61)
PASS  yük               10/10 istek · TTFT p95 67ms · 65 token/s

Sonuç: 9/10 geçti · 1 uyarı · endpoint sağlıklı (2.6s)
```

| Ek kontrol | Ne yapar | Kullandığı betik |
| --- | --- | --- |
| **model yoklama** | Listedeki her modele 1 token'lık istek atar; hepsi cevap vermiyorsa UYARI (embedding modelleri chat'i haklı olarak reddeder) | [`llm-models.sh --probe`](models.md) |
| **embeddings** | 7 kontrollük embedding sağlık paketi. `LLM_EMBED_MODEL` tanımlı değilse atlanır | [`embed-test.py --suite`](embeddings.md) |
| **rerank** | 8 kontrollük reranker sağlık paketi. `LLM_RERANK_MODEL` tanımlı değilse atlanır | [`rerank-test.py --suite`](rerank.md) |
| **yük** | 10 istek / 2 eşzamanlılık ile kısa bir yük testi; TTFT p95 ve çıktı token/s | [`chat-loadtest.py`](loadtest.md) |

Yukarıdaki çıktıdaki `UYARI` sahte sunucudan gelir: mock, bilerek çalışmayan bir
model yayınlar. Gerçek bir endpoint'te `4/4 model cevap verdi` beklenir.

Bulunamayan betikler ve kurulu olmayan çalışma ortamları (`python3` yoksa) hata
değil UYARI üretir — `--full`, betiğin tek başına taşınmasını engellemez.

---

## Sonra nereye bakmalı

`--full` bir sorun gösterdiğinde, o satırın parantezindeki betiği doğrudan
çalıştırın; her biri o alanın tam detayını verir:

| `--full` satırı sorun gösterirse | Detay için |
| --- | --- |
| model yoklama | `llm-models.sh --probe` → [model keşfi](models.md) |
| embeddings | `embed-test.py --suite` → [embeddings](embeddings.md) |
| rerank | `rerank-test.py --suite` → [rerank](rerank.md) |
| yük | `chat-loadtest.py -n 100 -c 16` → [yük testi ve TTFT](loadtest.md) |
| chat / UTF-8 / streaming | `llm-prompt.sh -v --stream` → [chat completions](chat-completions.md) |

Belirti–sebep–çözüm tablosu: [sorun giderme](troubleshooting.md).

---

## Her betik de kendi içinde iki seviyelidir

Tasarım kuralı: **parametresiz çalıştırınca en basit soruyu yanıtlar; parametre
ekledikçe detay verir.**

| Betik | Basit kullanım | Gelişmiş kullanım |
| --- | --- | --- |
| `llm-check.sh` | `llm-check.sh` — çalışıyor mu? | `--full` — ne kadar iyi çalışıyor? |
| `llm-prompt.sh` | `llm-prompt.sh "Merhaba"` — yanıt | `-v` token/gecikme · `--stream` · `--raw` ham JSON |
| `llm-models.sh` | `llm-models.sh` — id listesi | `-l` metadata · `--probe` yoklama · `--has` CI kapısı |
| `embed-test.py` | `embed-test.py "metin"` — dim ve norm | `--suite` 7 kontrol · `--pair` cosine · `--bench` throughput |
| `rerank-test.py` | `rerank-test.py` — yerleşik örnekle sıralama | `--suite` 8 kontrol · `--bench` throughput |
| `chat-loadtest.py` | `chat-loadtest.py -n 10` — TTFT özeti | `--duration` · `--csv` / `--json` · `--max-ttft-p95` SLO |

Doğrulanmış komut–çıktı çiftleri runbook'larda:
[Linux](runbook-linux.md#basit-kontroller) · [Windows](runbook-windows.md#basit-kontroller).
