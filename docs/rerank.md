# Rerank — `/v1/rerank`

Reranker, bir sorgu ve bir doküman listesi alıp **her dokümana o sorguyla ne
kadar ilgili olduğunu söyleyen bir skor** verir. RAG hatlarında embedding
aramasının getirdiği 50 adayı 5'e indirmek için kullanılır; cevabın kalitesini
en çok değiştiren adımlardan biridir.

[`python/rerank-test.py`](../python/rerank-test.py) bu endpoint'i test eder.
Yalnızca standart kütüphane; Linux, macOS ve Windows'ta aynı dosya çalışır
(`python3` / `py -3`). Ayrı bir PowerShell sürümü yoktur.

```
./rerank-test.py [sorgu] [doküman ...] [-e URL] [-k KEY] [-m MODEL]
                 [-q SORGU] [-f DOSYA] [--top-n N]
                 [--suite] [--bench N] [--concurrency C] [--docs N]
                 [--timeout S] [-i] [-v]
```

Model adı sırası: `-m` → `$LLM_RERANK_MODEL` → `$LLM_MODEL`.

---

## Basit: çalışıyor mu, ayırt ediyor mu?

Parametresiz çalıştırın. Yerleşik bir örnek kullanılır: bir soru, bir doğru
cevap, iki alakasız ve bir kısmen ilgili doküman.

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

### Sonucu nasıl okumalı

Bakılacak **iki** şey var:

1. **Doğru doküman ilk sırada mı?** Yukarıda öyle: `kubectl label` içeren
   cümle 1. sırada. Değilse model ya yanlış yüklenmiş ya da bu dil/alan için
   uygun değil.
2. **Birinci ile ikinci arasındaki fark ne kadar?** Asıl kritik sayı budur,
   çünkü RAG'de "kaç dokümanı bağlama koyacağım" kararını bu belirler:

| Fark | Ne anlama gelir | Ne yapmalı |
| --- | --- | --- |
| **≥ 0.20** | Model neyin ilgili olduğundan emin | Eşik koyup gerisini atabilirsiniz |
| **0.05 – 0.20** | Ayrım var ama dar | Eşiği kendi verinizle kalibre edin; sabit `top_n` daha güvenli |
| **< 0.05** | Model bu dokümanları ayırt edemiyor | Skorlara güvenmeyin; başka model deneyin |

Skorların **mutlak değeri modeller arasında karşılaştırılamaz.** Kimi model
0–1 arası olasılık verir, kimi ham logit döndürür (negatif olabilir). Anlamlı
olan sıralama ve aradaki farktır.

### Kendi verinizle

```bash
python3 python/rerank-test.py "disk alarmı nasıl kurulur" \
  "Prometheus ile disk doluluk alarmı kurma adımları." \
  "Balık ızgara tarifi." --top-n 2
```

```
Sorgu   disk alarmı nasıl kurulur
Model   mock-rerank · 2 doküman · 5ms

  #  skor    doküman
  1  0.7300  Prometheus ile disk doluluk alarmı kurma adımları.
  2  0.4900  Balık ızgara tarifi.

Yorum   birinci ile ikinci arasındaki fark 0.2400 — ayrım net
```

İlk pozisyonel değer sorgu, kalanlar dokümandır. Çok doküman varsa:
`-q "sorgu" -f dokumanlar.txt` (satır başına bir doküman).

---

## Gelişmiş: `--suite`

Sekiz kontrol, tek geçiş. Biri bile düşerse exit 1 — deploy kapısı olarak
kullanılabilir.

```bash
python3 python/rerank-test.py --suite
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
```

Her kontrol neyi koruyor:

| Kontrol | Düşerse ne olmuş demektir |
| --- | --- |
| **her doküman puanlandı** | Sunucu listeyi kırpıyor. 50 aday gönderip 10 skor alırsanız gerisi sessizce kaybolur |
| **index'ler geçerli ve benzersiz** | `index` alanı doküman listenize denk gelmiyor — yanlış dokümanı bağlama koyarsınız. Bu, rerank entegrasyonlarındaki en sinsi hatadır |
| **sonuçlar skora göre azalan sıralı** | Sunucu sıralamıyor; istemcinizin kendisi sıralamak zorunda. Bilmeden `results[0]`'ı kullanırsanız rastgele bir doküman alırsınız |
| **ilgili doküman ilk sırada** | Model yüklenmiş ama iş görmüyor: ya yanlış model ya da bu dil için uygun değil |
| **çağrılar arası deterministik** | Aynı sorgu her seferinde farklı sıralama veriyor — sonuçlarınız tekrarlanamaz, A/B testi yapamazsınız |
| **doküman sırası sonucu değiştirmiyor** | Sunucuda pooling/batching hatası. Aday listesinin sırası cevabı değiştiriyorsa üretimde açıklanamayan farklar görürsünüz. **Blocker sayın** |
| **top_n uygulanıyor** | `top_n` yok sayılıyor; bant genişliği ve gecikme boşa gidiyor |
| **uzun doküman işlendi** | Sunucu uzun dokümanı sessizce kırpıyor mu yoksa 4xx mi veriyor? İkisi de olabilir, ama hangisi olduğunu bilmeniz gerekir |

Sondaj metinleri Türkçedir; çok dilli reranker'ların çoğu İngilizce dışında
gözle görülür şekilde zayıflar. Kendi alanınızdan cümlelerle çalışmak için
dosyanın başındaki `SORGU` / `DOKUMANLAR` / `DOGRU_INDEX` değerlerini değiştirin.

---

### PASS / UYARI / FAIL

Sağlık paketi üç durum kullanır:

| Durum | Ne demek | Exit koduna etkisi |
| --- | --- | --- |
| `PASS` | Kontrol geçti | — |
| `UYARI` | Sapma var ama pratikte önemsiz — quantize edilmiş (GGUF) ya da batch'li GPU sunucularında `cos=0.9999` civarı farklar normaldir. Ayrıca "sunucu uzun girdiyi reddetti" gibi geçerli ama bilinmesi gereken davranışlar | **etkilemez** |
| `FAIL` | Gerçek bir sorun: sapma `cos < 0.999`, sıralama bozuk ya da vektörler normalize değil | exit `1` |

Bu ayrım gerçek bir koşumdan doğdu: quantize bir embedding modeli üç kontrolü
`FAIL` veriyordu, oysa farklar dördüncü ondalık basamaktaydı. Ayrıntı ve
doğrulanmış çıktılar: [compatibility.md](compatibility.md#doğrulanmış-gerçek-backend-sonuçları).

## Gelişmiş: `--bench`

```bash
python3 python/rerank-test.py --bench 100 --concurrency 8 --docs 20
```

```
istek=24  doküman/istek=8  eşzamanlılık=4  toplam doküman=192
süre=0.02s  throughput=1106.5 istek/s  8852 doküman/s
gecikme ms: ort=3 p50=3 p95=7 p99=8 maks=8
```

**Rerank'te asıl bakılacak sayı `doküman/s`'dir**, `istek/s` değil: maliyet
doküman sayısıyla büyür. Bir RAG isteği 50 aday rerank ediyorsa, 8852 doküman/s
kapasite kabaca 177 RAG isteği/s demektir.

`--docs` değerini gerçek aday sayınıza eşitleyin; 4 dokümanla ölçüp 50 dokümanla
servis etmek kapasite planını sistematik olarak yanlış yapar. Gecikme
istemci tarafında ölçülür.

---

## Exit kodları

| Kod | Anlamı |
| --- | --- |
| `0` | Sıralama alındı · `--suite` için tüm kontroller geçti |
| `1` | En az bir sağlık kontrolü düştü; ya da bağlantı hatası, 2xx olmayan status, ayrıştırılamayan yanıt |
| `2` | Parametre hatası (argparse) |

---

## Desteklenen yanıt biçimleri

`/v1/rerank` bir OpenAI standardı değil, Cohere'in başlattığı ve yaygınlaşan bir
biçim. Betik üç şekli de tanır:

| Sunucu | Yanıt |
| --- | --- |
| Cohere · Jina · vLLM · Infinity | `{"results": [{"index": 0, "relevance_score": 0.9}, ...]}` |
| TEI (yerel `/rerank`) | `[{"index": 0, "score": 0.9}, ...]` |
| Bazı gateway'ler | `{"data": [...]}` |

Endpoint yolu da normalize edilir: temel URL, `.../v1` ya da tam `.../v1/rerank`
verebilirsiniz.

## Backend notları

| Backend | Notlar |
| --- | --- |
| **vLLM** | Bir reranker modeli servis edin (`vllm serve BAAI/bge-reranker-v2-m3`); `/rerank`, `/v1/rerank` ve `/v2/rerank` yollarını sunar |
| **TEI** | Sequence-classification reranker'ları destekler; hem yerel `/rerank` hem OpenAI/Cohere uyumlu yol |
| **Infinity** | Tek süreçte embedding + rerank birlikte servis edilebilir |
| **Jina / Cohere / Voyage** | Bulut servisleri; `relevance_score` 0–1 arasıdır |
| **Ollama** | Rerank endpoint'i yoktur — reranker için ayrı bir servis gerekir |

Doğrulanmış komut–çıktı çiftleri runbook'larda:
[Linux](runbook-linux.md#rerank) · [Windows](runbook-windows.md#rerank).
