# Embeddings

[`python/embed-test.py`](../python/embed-test.py) OpenAI uyumlu bir
`/v1/embeddings` endpoint'iyle **yalnızca Python standart kütüphanesini**
kullanarak konuşur — `requests` yok, `numpy` yok, kurulacak hiçbir şey yok. Aynı
dosya Linux, macOS ve Windows'ta (`python3` / `py -3`) çalışır.

```
./embed-test.py [metin ...] [-e URL] [-k KEY] [-m MODEL]
                [-f DOSYA] [--pair A B] [--suite] [--bench N]
                [--concurrency C] [--batch-size B]
                [--dimensions D] [--encoding-format float|base64]
                [--timeout S] [-i] [-v]
```

Model adı sırası: `-m` → `$LLM_EMBED_MODEL` → `$LLM_MODEL`. Böylece chat modeli
için ayarlanmış bir kabuk, tek bir ek değişkenle embedding servisine de çalışır.

---

## Modlar

### Varsayılan — vektörü incele

```bash
./embed-test.py -m BAAI/bge-m3 "Kubernetes GPU node etiketleme"
```

```
[0] Kubernetes GPU node etiketleme                     dim=1024  |v|=1.000000  min=-0.0731 max=+0.0645
     head=[+0.0121, -0.0304, +0.0088, -0.0155, +0.0210, ...]
gecikme=48ms  metin=1  prompt_tokens=9  total_tokens=9
```

`|v|` L2 normudur — 1.0 civarında değilse, dot product'ı cosine benzerliği gibi
kullanmadan önce vektörleri kendiniz normalize etmeniz gerekir. Girdi
`-f dosya.txt` (satır başına bir metin) ya da stdin ile de verilebilir.

### `--pair` — iki metin ne kadar yakın?

```bash
./embed-test.py --pair "GPU node nasıl etiketlenir?" "K8s'te GPU sunucuya label"
# cosine=0.741215  dim=1024  gecikme=52ms
```

Modeli bir RAG hattına bağlamadan önce, kendi korpusunuzdan gerçek örneklerle
retrieval eşiğini kalibre etmek için birebir.

### `--suite` — bu model doğru bağlanmış mı?

Tek geçişte yedi kontrol. Biri bile başarısız olursa exit 1 verir, yani deploy
kapısı olarak çalışır.

| Kontrol | Neyi yakalar |
| --- | --- |
| **batch içinde dim tutarlı** | Sessizce model değiştiren ya da batch'i kırpan bir sunucu |
| **vektörler L2-normalize** | Cosine/dot product karışıklığı — "sıralama rastgele görünüyor" şikayetinin bir numaralı sebebi |
| **çağrılar arası deterministik** | Deterministik olmayan pooling ya da farklı yapılandırılmış replica'lara dağıtan bir load balancer |
| **cos(paraphrase) > cos(alakasız)** | Yüklenmiş ama sizin sandığınız olmayan bir model — ya da retrieval için hiç eğitilmemiş bir model |
| **cos(aynı metin) ≈ 1.0** | Bozuk normalizasyon ya da istek başına rastgele seed |
| **batch pozisyonu vektörü değiştirmiyor** | Padding/pooling hatası: bir metnin, batch'teki diğer metinlere göre farklı embed edilmesi. Üretimde canınızı yakan budur, çünkü indexlemeyi büyük batch'lerle yapıp sorguyu tek metinle atarsınız |
| **uzun girdi işlendi** | `max-model-len` üzerinde sunucunun sessizce truncate mi ettiği yoksa 4xx mi döndüğü. İkisi de savunulabilir — ama hangisi olduğunu bilmeniz gerekir |

```
PASS   batch içinde dim tutarlı               dim=1024
PASS   vektörler L2-normalize                 norms=1.000000, 1.000000, 1.000000
PASS   çağrılar arası deterministik           max|delta|=0.000e+00 cos=1.00000000
PASS   cos(paraphrase) > cos(alakasız)        para=0.7412 alakasız=0.2688 fark=0.4724
PASS   cos(aynı metin) ~= 1.0                 cos=1.00000000
PASS   batch pozisyonu vektörü değiştirmiyor  cos(pos0)=1.00000000 cos(pos3)=1.00000000
PASS   uzun girdi (~264000 karakter) işlendi  sessizce truncate edildi, prompt_tokens=8192

7/7 geçti  (dim=1024, ilk çağrı 61ms, prompt_tokens=36)
```

Sondaj metinleri bilerek Türkçedir (bir paraphrase çifti ve alakasız bir cümle) —
çok dilli embedding modellerinin çoğu İngilizce dışında gözle görülür biçimde
zayıflar ve buradaki dar bir fark, üstüne index kurmadan önce bilinmesi gereken
bir sinyaldir. Kendi alanınızdan cümleler kullanmak için dosyanın başındaki
`IDENT` / `PARA` / `UNREL` değerlerini değiştirin.

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

### `--bench` — throughput ve gecikme

```bash
./embed-test.py --bench 200 --concurrency 16 --batch-size 8
```

```
istek=25  batch_size=8  eşzamanlılık=16  metin=200
süre=1.84s  throughput=108.7 metin/s  13.6 istek/s
gecikme ms: ort=1043 p50=1010 p95=1580 p99=1720 maks=1733
```

`--bench N` bir **metin** sayısıdır: `--concurrency` işçilik bir havuz üzerinden
`N ÷ batch-size` istek gönderir.

Nasıl okunur:

- **`throughput`** kapasite planlamasının ilgilendiği sayıdır. İyileşme durana
  kadar `--batch-size` değerini artırın — orası sunucunuzun batching tatlı noktasıdır.
- **`p95` / `p99`** kullanıcının hissettiğidir. p99, p50'nin katları kadarsa
  sunucu kuyruğa giriyordur: eşzamanlılığı düşürün ya da replica ekleyin.
- Gecikme **istemci tarafında** ölçülür, yani ağ gidiş-dönüşünü içerir. Sunucuya
  yakın bir makineden çalıştırın ve mutlak değer yerine konfigürasyonlar arası
  karşılaştırma aracı olarak kullanın.
- Yük üreteci bir Python thread havuzudur. İş G/Ç ağırlıklı olduğu için bu
  yeterlidir; ama çok yüksek eşzamanlılıkta istemcinin kendisi darboğaz olabilir.
  GPU boşken `throughput` doyuyorsa önce istemciden şüphelenin.

---

## Bilinmesi gereken seçenekler

**`--dimensions D`** — Matryoshka kırpması. Yalnızca bazı modeller destekler
(`text-embedding-3-*`, bazı dağıtımlarda `bge-m3`). Verildiğinde sağlık paketi
sekizinci bir kontrol ekleyip sunucunun bunu gerçekten uygulayıp uygulamadığını
doğrular; sessizce tam genişlikte vektör dönmesini yakalar.

Ölçülmüş iki davranış (2026-09-02): doğrudan llama.cpp parametreyi **kabul edip
yok sayıyor** (1024 boyut dönüyor), LiteLLM gateway ise **400 ile reddediyor**.
Yani "hata almadım" demek "uygulandı" demek değil — dönen `dim` değerine bakın.

**`--encoding-format base64`** — JSON sayı dizisi yerine little-endian float32
blob ister. Büyük batch'lerde hat üzerinde kabaca 3–4 kat daha az bayt demektir;
betik bunu şeffaf biçimde çözer, çıktı aynıdır. Bir istemci kütüphanesini bu
formata geçirmeden önce sunucunun desteklediğini doğrulamanın iyi bir yolu.

**`-i` / `--insecure`** — self-signed iç endpoint'ler için TLS doğrulamasını atlar.

**`-v`** — giden isteği (girdi gizlenmiş halde) stderr'e yazar.

---

## Exit kodları

| Kod | Anlamı |
| --- | --- |
| `0` | Başarılı (ya da: tüm sağlık kontrolleri geçti) |
| `1` | En az bir sağlık kontrolü başarısız; ya da bağlantı hatası, 2xx olmayan status, `data` dizisi olmayan yanıt |
| `2` | Parametre hatası (argparse) |

`--suite` hata halinde sıfırdan farklı döndüğü için doğrudan hatta girer:

```bash
python3 python/embed-test.py --suite || { echo "embedding endpoint sağlıksız"; exit 1; }
```
