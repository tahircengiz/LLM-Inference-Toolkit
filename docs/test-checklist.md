# Test checklist'i — yayına hazırlık

Bu depodaki her betiği, önerdiğimiz her sonucu ve dokümandaki her çıktıyı tek tek
doğrulamak için. **Kural: doğrulanmamış hiçbir iddia dokümanda kalmayacak.**

Nasıl kullanılır: her maddeyi çalıştır, çıktıya bak, kutuyu işaretle. Sonuç
beklenenden farklıysa **dokümanı değil önce betiği** sorgula — sonra ikisinden
hangisinin yanlış olduğuna karar ver.

| İşaret | Anlamı |
| --- | --- |
| ☐ → ✅ | Beklendiği gibi |
| ☐ → ⚠️ | Çalışıyor ama not düşülecek bir davranış var (dokümana işlenecek) |
| ☐ → ❌ | Sorun; düzeltilecek |

## Hedefler

Testten önce kendi adreslerinizi doldurun. Gerçek adres ve anahtarları depoya
yazmayın; `.env` (git tarafından yok sayılır) içinde tutun —
[`examples/env.example`](../examples/env.example).

| Hedef | Adres | Model | Durum |
| --- | --- | --- | --- |
| Chat | `http://SUNUCU:PORT` | | |
| Embeddings | `http://SUNUCU:PORT` | | |
| Gateway (LiteLLM / vLLM router) | `http://SUNUCU:PORT` | | anahtar gerekli mi? |
| Reranker | `http://SUNUCU:PORT` | | kurulu mu? |
| Windows makinesi | — | — | PowerShell 5.1 + 7 |

Örnek doldurulmuş hali (bu depoyu geliştirirken kullandığımız kurulum): tek
makinede llama.cpp chat ve embedding ayrı portlarda, önlerinde bir LiteLLM
gateway, reranker yok.

## Hızlı yol: bölümü tek komutla koşmak

Her hedef için batarya tek komutla çalıştırılıp markdown rapor üretilebilir;
sonra raporu gözden geçirip değerlendirme sütununu doldurursunuz:

```bash
python3 tests/capture_report.py --label "llama.cpp Qwen3-30B" \
  -e http://SUNUCU:8084 -k "$LLM_API_KEY" -m qwen3-30b-a3b-gguf \
  --embed-model qwen3-embed --embed-endpoint http://SUNUCU:8085 \
  -o raporlar/llamacpp.md
```

Rapor her komutun kendisini, exit kodunu ve tam çıktısını içerir; API anahtarı
maskelenir. Aşağıdaki maddeler yine de tek tek okunmalı — araç kaydeder, **hüküm
vermez**.

---

## 0. Otomatik katman

| ☐ | # | Ne | Komut / yer | Beklenen |
| --- | --- | --- | --- | --- |
| ☐ | 0.1 | CI beş işte de yeşil | GitHub Actions son koşum | ubuntu 57/57 · macOS 57/57 · windows 38/38 · PS 5.1 38/38 · lint |
| ☐ | 0.2 | Temiz clone'da smoke | `git clone` → `python3 tests/smoke_test.py` | 57 geçti, 0 başarısız |
| ☐ | 0.3 | `jq` olmadan | `PATH` içinden jq'yu çıkarıp smoke | aynı sonuç (python3 yedeği) |
| ☐ | 0.4 | `chmod` sonrası doğrudan çalıştırma | `./bash/llm-check.sh -h` | yardım metni |

## A. Chat — llama.cpp (`:8084`)

| ☐ | # | Ne | Komut | Beklenen / kaydedilecek |
| --- | --- | --- | --- | --- |
| ☐ | A.1 | Basit sağlık | `bash/llm-check.sh` | 6/6 · exit 0 |
| ☐ | A.2 | Gelişmiş sağlık | `bash/llm-check.sh --full` | FAIL yok · exit 0 |
| ☐ | A.3 | PowerShell eşdeğeri | `Test-LlmEndpoint.ps1` | A.1 ile **satır satır aynı** |
| ☐ | A.4 | Model listesi | `bash/llm-models.sh -l` | `CONTEXT` sütunu: llama.cpp yayınlamıyor → `-` |
| ☐ | A.5 | Model yoklama | `bash/llm-models.sh --probe` | 1/1 · exit 0 |
| ☐ | A.6 | `--has` | `bash/llm-models.sh --has "$LLM_MODEL"` | sessiz · exit 0 |
| ☐ | A.7 | Chat + tanılama | `bash/llm-prompt.sh -v "..."` | doğru yanıt · `finish=stop` · **tok/s kaydet** |
| ☐ | A.8 | Streaming | `bash/llm-prompt.sh --stream "..."` | parça parça geliyor mu? |
| ☐ | A.9 | System prompt / sampling | `-s ... -t 0.2 -n 16` | gövdede gerçekten gidiyor mu (`-v`) |
| ☐ | A.10 | Endpoint biçimleri | base · `/v1` · tam yol | üçü de aynı sonuç |
| ☐ | A.11 | stdin | `echo "..." \| bash/llm-prompt.sh` | parametreyle aynı |
| ☐ | A.12 | `--raw` | `--raw \| jq .model` | dönen `model` alanı |
| ☐ | A.13 | PowerShell chat | `Invoke-LlmPrompt.ps1 -Verbose` | Türkçe karakterler sağlam |
| ☐ | A.14 | PowerShell streaming | `-Stream` | parça parça |
| ☐ | A.15 | Yük testi | `chat-loadtest.py -n 20 -c 4` | **TTFT p95 / ITL / token-s kaydet** |
| ☐ | A.16 | Eşzamanlılık taraması | `-c 1,2,4,8` | throughput nerede doyuyor? |
| ☐ | A.17 | SLO kapısı | `--max-ttft-p95 <ölçülen×1.5>` | geçmeli; yarısıyla düşmeli |

## B. Embeddings — llama.cpp (`:8085`)

| ☐ | # | Ne | Komut | Beklenen / kaydedilecek |
| --- | --- | --- | --- | --- |
| ☐ | B.1 | Sağlık paketi | `embed-test.py --suite` | UYARI'lar kabul · **FAIL olmamalı** |
| ☐ | B.2 | Kendi alanınızdan çift | `--pair "<gerçek soru>" "<gerçek doküman>"` | **cosine kaydet** — eşik kalibrasyonu |
| ☐ | B.3 | Alakasız çift | `--pair "<soru>" "<alakasız>"` | B.2'den belirgin düşük olmalı |
| ☐ | B.4 | Benchmark | `--bench 100 --concurrency 8 --batch-size 8` | **throughput / p95 kaydet** |
| ☐ | B.5 | `dimensions` | `--dimensions 256` | uygulanıyor mu, yoksa tam genişlik mi? |
| ☐ | B.6 | `base64` | `--encoding-format base64` | çözülüyor mu |
| ☐ | B.7 | Uzun girdi | suite içinde | 400 mü, sessiz truncate mi? **davranışı yaz** |

## C. Gateway — LiteLLM (`:4000`)

> Sanal anahtar olmadan yapılamaz. Anahtar alındığında bu bölüm çalıştırılacak.

| ☐ | # | Ne | Beklenen / kaydedilecek |
| --- | --- | --- | --- |
| ☐ | C.1 | Sağlık kontrolü | 6/6 |
| ☐ | C.2 | Model listesi | **alias'lar mı, upstream adlar mı?** |
| ☐ | C.3 | `--probe` | listede olup route edilmeyen alias var mı — bu yardımcının varlık sebebi |
| ☐ | C.4 | Path önekli endpoint | `.../team-x/v1` biçimi korunuyor mu |
| ☐ | C.5 | Yanlış anahtar | 401 ve exit 1 |
| ☐ | C.6 | `--raw \| jq .model` | gateway hangi modele yönlendirdi |

## D. Rerank

> GTR9'da reranker yok; `bge-reranker-v2-m3` (TEI ya da Infinity) kurulduktan
> sonra çalıştırılacak. Bugüne kadar yalnızca sahte sunucuya karşı doğrulandı.

| ☐ | # | Ne | Beklenen / kaydedilecek |
| --- | --- | --- | --- |
| ☐ | D.1 | Basit sıralama | ilgili doküman 1. sırada · **fark kaydet** |
| ☐ | D.2 | Sağlık paketi | FAIL olmamalı |
| ☐ | D.3 | Yanıt biçimi | `relevance_score` mu `score` mu; `results` mu düz dizi mi |
| ☐ | D.4 | `top_n` | uygulanıyor mu |
| ☐ | D.5 | Kendi verinizle | gerçek RAG adaylarıyla sıralama mantıklı mı |
| ☐ | D.6 | Benchmark | **doküman/s kaydet** |

## E. Windows — gerçek makine

> CI, Windows Server üzerinde koşuyor. Bunlar bir kullanıcının gerçekten
> karşılaşacağı şeyler ve CI'da görünmez.

| ☐ | # | Ne | Beklenen |
| --- | --- | --- | --- |
| ☐ | E.1 | Execution policy | `Unblock-File` / `-ExecutionPolicy Bypass` yönergesi işe yarıyor mu |
| ☐ | E.2 | PowerShell 5.1 · sağlık | 6/6 |
| ☐ | E.3 | PowerShell 5.1 · streaming | parça parça geliyor mu |
| ☐ | E.4 | PowerShell 7 · aynısı | 5.1 ile aynı sonuç |
| ☐ | E.5 | Konsol kodlaması | Türkçe karakterler bozuk mu; `[Console]::OutputEncoding` çözüyor mu |
| ☐ | E.6 | Dosyaya yönlendirme | `> cevap.txt` içeriği bozulmuyor mu |
| ☐ | E.7 | Python betikleri | `python`/`py -3` ile çalışıyor mu |
| ☐ | E.9 | Parametrelerle (ortam değişkeni olmadan) | `-e -k -m` ile üç betik de çalışıyor mu |
| ☐ | E.10 | `Get-Help` | `Get-Help .\Test-LlmEndpoint.ps1 -Detailed` anlamlı çıktı veriyor mu |
| ☐ | E.8 | Kurumsal proxy | varsa: takılıyor mu, `NO_PROXY` çözüyor mu |

## F. Hata ve kenar durumlar

| ☐ | # | Ne | Beklenen |
| --- | --- | --- | --- |
| ☐ | F.1 | Kapalı port | `endpoint erişilemiyor` · exit 1 · gerisini denemiyor |
| ☐ | F.2 | Yanlış anahtar (anahtar zorunlu bir sunucuda) | 401 · `erişim` ve `kimlik doğrulama` FAIL |
| ☐ | F.3 | Var olmayan model | sunucuya göre 404/400 **ya da** model alanı yok sayılıyor — hangisi olduğu yazılacak |
| ☐ | F.4 | Zaman aşımı | `--timeout 1` ile yavaş bir istek | temiz hata, asılı kalma yok |
| ☐ | F.5 | Self-signed TLS | `-i` olmadan hata, `-i` ile geçiyor mu |
| ☐ | F.6 | `max_tokens` sınırı | `-n 8` ile `finish=length` |
| ☐ | F.7 | Boş / çok uzun prompt | anlamlı hata |
| ☐ | F.8 | CI kullanımı | `llm-check.sh -q && echo TAMAM \|\| echo SORUN` | exit kodu doğru dallanıyor |

## G. Doküman doğruluğu

En kritik bölüm: **dokümanda yazan her çıktı gerçekten üretiliyor mu?**

| ☐ | # | Ne | Nasıl |
| --- | --- | --- | --- |
| ☐ | G.1 | Linux runbook B1–B4 | sahte sunucuya karşı tek tek çalıştır, çıktıyı karşılaştır |
| ☐ | G.2 | Linux runbook L01–L18 | aynısı |
| ☐ | G.3 | Linux runbook R1–R4 | aynısı |
| ☐ | G.4 | Linux runbook E01–E06 | aynısı |
| ☐ | G.5 | Windows runbook B1–B4, W01–W16, R1 | Windows makinesinde |
| ☐ | G.6 | README örnekleri | kopyala-yapıştır çalışıyor mu |
| ☐ | G.7 | İç bağlantılar | `python3 -c` link kontrolü (CI dışı, elle) |
| ☐ | G.8 | Sözlükteki terimler | çıktılarda geçen her terim sözlükte var mı |

## H. Kabul kriterleri

Bunların hepsi ✅ olmadan başkalarına önermeyelim:

- [ ] CI'nın beş işi de yeşil ve sayılar dokümanda yazanla aynı
- [ ] **En az iki farklı gerçek backend'de** tüm paket çalıştırıldı (llama.cpp ✅ · gateway ☐)
- [ ] Reranker en az bir gerçek sunucuda doğrulandı
- [ ] Windows'ta **gerçek bir makinede** (CI değil) çalıştırıldı
- [ ] Her runbook örneği birebir üretildi
- [ ] `compatibility.md` yalnızca doğrulanmış sonuçları "doğrulanmış" diye etiketliyor; gerisi açıkça "API yüzeyinden derlendi" diyor
- [ ] Hiçbir betik yanlış alarm üretmiyor (gerçek sunucuda beklenen davranış FAIL sayılmıyor)
- [ ] Anahtar/hostname sızıntısı yok: `grep -rniE "sk-[a-z0-9]{8}|192\.168\.|10\.[0-9]+\.[0-9]+\.[0-9]+:" --exclude-dir=.git .` (örnek adresler `10.0.0.10` ve `example.com` olmalı)

---

## Bugüne kadar doğrulananlar

| Tarih | Ne | Sonuç |
| --- | --- | --- |
| 2026-09-01 | llama.cpp chat (Qwen3-30B) | 6/6 sağlıklı · TTFT p50 42ms · ITL 13.7ms · 138 token/s |
| 2026-09-01 | llama.cpp embeddings (Qwen3-Embedding) | 5/7 + 2 uyarı · paraphrase/alakasız farkı 0.61 |
| 2026-09-01 | CI: ubuntu · macOS · windows · PowerShell 5.1 | 57/57 · 57/57 · 38/38 · 38/38 |

Ayrıntılar: [compatibility.md](compatibility.md#doğrulanmış-gerçek-backend-sonuçları).
