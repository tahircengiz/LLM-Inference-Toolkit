# Yük testi ve TTFT

[`python/chat-loadtest.py`](../python/chat-loadtest.py) bir chat endpoint'ine
eşzamanlı yük uygular ve serving tarafında gerçekten önem taşıyan dört sayıyı
ölçer. Yalnızca standart kütüphane kullanır; Linux, macOS ve Windows'ta aynı
dosya çalışır (`python3` / `py -3`).

```
./chat-loadtest.py [seçenekler]

  -e/--endpoint URL      temel URL (env: LLM_ENDPOINT)
  -k/--api-key KEY       bearer token (env: LLM_API_KEY)
  -m/--model AD          model adı (env: LLM_MODEL)
  -n/--requests N        toplam istek sayısı (varsayılan 20)
  -c/--concurrency C     eşzamanlı istek sayısı (varsayılan 4)
  --duration S           istek sayısı yerine S saniye boyunca yük uygula
  -p/--prompt METİN      prompt (varsayılan sabit bir Türkçe prompt)
  --prompt-file DOSYA    prompt'u dosyadan oku
  --max-tokens N         varsayılan 128
  --temperature N        varsayılan 0.0
  --warmup N             ölçüme dahil edilmeyen ısınma isteği (varsayılan 1)
  --no-stream            stream kapalı: TTFT ölçülemez, sadece uçtan uca süre
  --stream-usage         stream_options.include_usage gönder
  --csv DOSYA            istek başına satır yaz
  --json                 özeti JSON olarak yazdır
  --max-ttft-p95 MS      SLO: TTFT p95 aşılırsa exit 1
  --max-error-rate YÜZDE SLO: hata oranı aşılırsa exit 1 (varsayılan 0)
  --timeout S            varsayılan 300
  -i/--insecure          TLS doğrulamasını atla
  -v/--verbose
```

> Bu betik Python olduğu için Windows'ta da aynı şekilde çalışır; ayrı bir
> PowerShell sürümü yoktur. Windows kullanımı için
> [runbook-windows.md](runbook-windows.md#yük-testi) bölümüne bakın.

---

## Ölçülen dört sayı

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

### TTFT — time to first token

İstek gönderildikten **ilk içerik token'ı gelene kadar** geçen süre. Kullanıcının
"takıldı mı?" diye düşündüğü an budur; sohbet arayüzlerinde algılanan hızın
neredeyse tamamını belirler.

TTFT şunları içerir: kuyrukta bekleme + prefill (prompt'un işlenmesi) + ağ.
Uzun prompt'larda prefill baskındır, bu yüzden `--prompt-file` ile gerçek
prompt uzunluğunuzu kullanmak önemlidir — 20 token'lık bir test prompt'u ile
4000 token'lık bir RAG prompt'unun TTFT'si aynı sunucuda kat kat farklıdır.

**Önemli ayrıntı:** ölçüm, ilk *içerik* parçasına göre yapılır. Sunucuların çoğu
ilk chunk'ta yalnızca `delta.role` gönderir; onu saymak TTFT'yi olduğundan iyi
gösterirdi.

### ITL — inter-token latency

Ardışık token'lar arasındaki süre; okunma hızını belirler. `1 / ITL` saniyedeki
token sayısını verir (ör. 25 ms ITL ≈ 40 tok/s).

**Uyarı:** ölçüm aslında ardışık *SSE chunk'ları* arasındadır. Sunucuların çoğu
chunk başına bir token gönderir, ama bazıları token'ları gruplayabilir; bu
durumda ITL "chunk başına" okunmalıdır.

### E2E — uçtan uca süre

İstekten son token'a kadar geçen toplam süre. Yaklaşık olarak
`TTFT + (çıktı token sayısı × ITL)`. Batch işlerde ve API zincirlerinde asıl
bakılacak sayı budur.

### Throughput

`istek/s` ve `çıktı token/s`. Kapasite planlaması için asıl anlamlı olan ikincisidir:
GPU'nuzun saniyede kaç token ürettiğini söyler. `-c` değerini artırdıkça çıktı
token/s bir yere kadar artar, sonra doyar — orası sunucunun batching tatlı noktasıdır.
Aynı noktadan sonra TTFT p95 hızla bozulmaya başlar; ikisine birlikte bakın.

---

## Kullanım kalıpları

### Batching tatlı noktasını bulmak

```bash
for c in 1 2 4 8 16 32; do
  echo "== eşzamanlılık $c"
  python3 python/chat-loadtest.py -n $((c * 10)) -c $c | grep -E "Throughput|TTFT"
done
```

Çıktı token/s'in artmayı bıraktığı ve TTFT p95'in fırladığı yer, o modelin o
donanımdaki pratik sınırıdır.

### Gerçek prompt uzunluğuyla ölçmek

```bash
python3 python/chat-loadtest.py --prompt-file gercek_rag_prompt.txt -n 50 -c 8
```

Prefill maliyeti prompt uzunluğuyla büyür. Kısa prompt'la ölçüp uzun prompt'la
servis etmek, kapasite planını sistematik olarak yanlış yapar.

### Deploy sonrası SLO kapısı

```bash
python3 python/chat-loadtest.py -n 30 -c 8 --max-ttft-p95 800 || {
    echo "TTFT bütçesi aşıldı, deploy geri alınıyor"; exit 1
}
```

```
SLO         TTFT p95 72ms <= 2000ms ✓
```

İhlal halinde stderr'e tek satır yazar ve exit 1 verir:

```
SLO ihlali: TTFT p95 73ms > 10ms
```

`--max-error-rate` varsayılan olarak 0'dır: tek bir başarısız istek bile exit 1
demektir. Kısmi hataya izin vermek isterseniz `--max-error-rate 1` gibi bir değer
verin.

### Sonuçları saklamak ve karşılaştırmak

```bash
python3 python/chat-loadtest.py -n 100 -c 16 --json > sonuc-$(date +%F).json
python3 python/chat-loadtest.py -n 100 -c 16 --csv istekler.csv
```

`--json` özeti makine okunur biçimde verir (dashboard ya da regresyon takibi
için), `--csv` her isteği ayrı satır olarak yazar (`ttft_ms`, `e2e_ms`,
`itl_ort_ms`, `cikti_token`, `hata`) — kuyruk davranışını incelemek için birebir.

### Streaming olmadan

```bash
python3 python/chat-loadtest.py -n 20 -c 4 --no-stream
```

```
TTFT  (ms)  ölçülmedi (--no-stream)
E2E   (ms)  ort=1 p50=1 p95=1 p99=1 maks=1
```

Streaming kapalıyken ilk token'ın ne zaman geldiği bilinemez, bu yüzden TTFT
raporlanmaz. Bloklayan istemcilerin gördüğü gecikmeyi ölçmek için kullanışlıdır.

### Süreye göre yük

```bash
python3 python/chat-loadtest.py --duration 60 -c 16
```

Sabit sayıda istek yerine 60 saniye boyunca yük uygular. Otomatik ölçeklenen ya
da ısındıkça hızlanan servisleri gözlemlemek için daha gerçekçidir.

---

## Hatalar

Başarısız istekler status'a göre gruplanır ve sunucunun kendi mesajıyla yazılır:

```
Hatalar     4× HTTP 503: 'error-503' modeli için enjekte edilmiş hata
```

Hiç başarılı istek olmadıysa TTFT satırı bunu açıkça söyler:

```
TTFT  (ms)  ölçülemedi (başarılı istek yok)
```

## Exit kodları

| Kod | Anlamı |
| --- | --- |
| `0` | Tüm istekler başarılı ve verilen SLO'lar sağlandı |
| `1` | Eksik parametre, hiç istek tamamlanamaması, hata oranı `--max-error-rate` üzerinde ya da TTFT p95 `--max-ttft-p95` üzerinde |
| `2` | Parametre hatası (argparse) |

## Ölçümün kendisi nasıl doğrulanıyor?

Sahte sunucu ilk token'dan önce bilerek bekler (`--prefill`), sonra her chunk
arasında çok daha kısa bir gecikme koyar. Yani doğru çalışan bir ölçümde TTFT,
ITL'nin kat kat üstünde çıkmak zorundadır. `tests/smoke_test.py` bunu 400ms
prefill + 10ms chunk ayarlı ayrı bir sunucuyla her koşumda kontrol eder:

```
PASS  python: TTFT, ITL'den ayrı ölçülüyor       ttft_p50=407ms itl_p50=12ms (sunucu 400ms prefill + 10ms chunk)
```

Bu, "betik çalıştı" demekten farklı bir şeydir: iki metriğin birbirine
karışmadığını kanıtlar.

## Dürüst sınırlar

- **Ölçüm istemci tarafındadır.** Ağ gidiş-dönüşü ve istemcinin kendi yükü
  sayılara dahildir. Sunucuya yakın bir makineden çalıştırın ve sonuçları mutlak
  değer olarak değil, konfigürasyonlar arası karşılaştırma olarak kullanın.
- **Yük üreteci Python thread havuzudur.** İş G/Ç ağırlıklı olduğu için bu
  yeterlidir, ama çok yüksek eşzamanlılıkta istemci darboğaz olabilir. GPU boşken
  throughput doyuyorsa önce istemciden şüphelenin.
- **Sunucunun kendi metrikleri daha kesindir.** vLLM `/metrics` altında kuyruk
  derinliği ve gerçek prefill/decode sürelerini verir. Bu betik dışarıdan
  bakılan resmi ölçer; ikisi birbirini tamamlar.
