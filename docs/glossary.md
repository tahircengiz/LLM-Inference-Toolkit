# Sözlük — çıktılardaki terimler

Betiklerin bastığı her terim, ne anlama geldiği ve **hangi değeri görünce ne
düşünmeniz gerektiği**.

## Gecikme ve hız

| Terim | Ne demek | Nasıl okunur |
| --- | --- | --- |
| **TTFT** | Time to first token — isteği gönderdikten ilk kelimenin gelmesine kadar geçen süre | Kullanıcının "takıldı mı?" dediği an. Sohbet arayüzünde algılanan hızın çoğu budur. Uzun prompt'ta büyür (prefill) |
| **ITL** | Inter-token latency — ardışık token'lar arasındaki süre | Okuma hızı. `1 / ITL` ≈ saniyedeki token. 25 ms ≈ 40 tok/s |
| **E2E** | Uçtan uca: istekten son token'a | Batch işler ve API zincirleri için asıl sayı. Kabaca `TTFT + (token sayısı × ITL)` |
| **tok/s** | Saniyedeki çıktı token'ı | Tek istek için `-v` çıktısındaki değer kabadır (ağ + kuyruk dahil); kapasite için yük testindeki `çıktı token/s` kullanılır |
| **throughput** | Birim zamanda tamamlanan iş | Kapasite planlaması buna bakar. Eşzamanlılığı artırın, artmayı bıraktığı yer sunucunun sınırıdır |
| **p50 / p95 / p99** | Yüzdelikler: isteklerin %50/%95/%99'u bu sürenin altında kaldı | Ortalama yalan söyler, p95 söylemez. p99 ≫ p50 ise sunucu kuyruğa giriyordur |
| **prefill** | Prompt'un işlenip ilk token'ın üretilmesi | Uzun prompt = uzun prefill = yüksek TTFT |
| **decode** | Kalan token'ların tek tek üretilmesi | ITL'yi belirleyen aşama |

## İstek ve yanıt

| Terim | Ne demek | Nasıl okunur |
| --- | --- | --- |
| **streaming / SSE** | Yanıtın parça parça (`data: ...` satırları) gelmesi | Çalışmıyorsa ya sunucu yok sayıyordur ya araya giren proxy tamponluyordur |
| **finish_reason** | Üretimin neden bittiği | `stop` = model kendi bitirdi · `length` = `max_tokens` sınırına çarptı, cevap yarım · `content_filter` = engellendi |
| **usage** | Sunucunun bildirdiği token sayıları | Faturalandırma ve kapasite için tek güvenilir kaynak. Streaming sırasında çoğu sunucu göndermez |
| **max_tokens** | Üretilecek en fazla token | `finish=length` görüyorsanız bu değeri artırın |
| **temperature** | Örneklemedeki rastgelelik | 0 en tutarlı sonucu verir ama batch'li GPU'larda birebir aynılık garantisi değildir |
| **context / max_model_len** | Modelin alabileceği en fazla token | Aşarsanız ya 4xx alırsınız ya girdiniz sessizce kırpılır |

## Embedding ve rerank

| Terim | Ne demek | Nasıl okunur |
| --- | --- | --- |
| **embedding** | Metnin sayı vektörüne çevrilmiş hali | Arama, benzerlik ve RAG'in temeli |
| **dim** | Vektörün uzunluğu | Modelin sabiti (bge-m3: 1024). Beklediğinizden farklıysa yanlış model yüklüdür |
| **L2 norm (`\|v\|`)** | Vektörün büyüklüğü | 1.0 ise vektör normalize edilmiştir ve dot product = cosine. Değilse önce siz normalize etmelisiniz, yoksa sıralamayı vektör büyüklüğü ele geçirir |
| **cosine** | İki vektör arasındaki açının kosinüsü, −1…1 | Anlamsal yakınlık. Mutlak değeri modeller arası karşılaştırılamaz; **fark** önemlidir |
| **rerank** | Sorgu–doküman çiftini doğrudan puanlama | Embedding aramasından gelen adayları yeniden sıralar. Skorun mutlak değeri değil, sıralama ve aradaki fark önemlidir |
| **top_n** | Sunucudan yalnızca ilk N sonucu isteme | Bant genişliği ve gecikme tasarrufu |
| **truncation** | Uzun girdinin kırpılması | Sessizce kırpan sunucu, hiç uyarmadan yanlış sonuç üretebilir |

## Test çıktıları

| İşaret | Anlamı |
| --- | --- |
| **PASS** | Kontrol geçti |
| **FAIL** | Kontrol düştü — exit kodu `1` olur, düzeltilmesi gerekir |
| **UYARI** | Dikkate değer ama sağlıksız saymayan durum (ör. `/v1/models` uygulamayan tek modelli sunucu). Exit kodunu **değiştirmez** |
| **SKIP** | Gerekli çalışma ortamı kurulu değil (ör. Windows'ta `bash`). Hata sayılmaz |
| **exit 0 / 1** | `0` = her şey yolunda, `1` = en az bir sorun. Betikleri CI ve cron'da bu yüzden doğrudan kullanabilirsiniz |

## Altyapı

| Terim | Ne demek |
| --- | --- |
| **endpoint** | Servisin adresi (`http://host:8000/v1`) |
| **bearer token** | `Authorization: Bearer sk-...` başlığıyla gönderilen anahtar |
| **gateway** | Birden çok modeli tek adres arkasında toplayan ara katman (LiteLLM gibi). Model adları genelde sizin verdiğiniz alias'lardır |
| **OpenAI uyumlu** | OpenAI'nin HTTP arayüzünü taklit eden servis. Aynı yolları sunar ama [her şeyi garanti etmez](compatibility.md#openai-uyumlu-olmak-neyi-garanti-etmez) |
| **batching** | Sunucunun birden çok isteği birlikte işlemesi | 
| **cold start** | İlk isteğin ağırlık yükleme yüzünden yavaş olması |
