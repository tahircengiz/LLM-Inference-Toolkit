# Katkı

Uğradığınız için teşekkürler. Bu depo bilinçli olarak küçük ve bağımlılıksız —
aşağıdaki kısıtlar onu kilitli bir jump host'ta kullanılabilir kılan şey.

## Temel kurallar

1. **Çalışma zamanı bağımlılığı yok.** Bash betikleri `curl` ve `jq` *ya da*
   `python3` kullanır. Python betikleri yalnızca standart kütüphaneyi kullanır.
   PowerShell betikleri yalnızca .NET kullanır — `curl.exe` yok, kurulacak modül yok.
2. **Ya çapraz platform, ya da kapsamı açıkça yazılmış.** Bash, GNU'ya özel
   parametre kullanmadan Bash 3.2'de (macOS) çalışmalı. PowerShell 5.1 ve 7+
   üzerinde çalışmalı. Python 3.8+ ile uyumlu olmalı.
3. **Tanılama stderr'e, sonuç stdout'a.** Betiği dosyaya yönlendirdiğinizde
   verbose açıkken bile çıktı temiz olmalı.
4. **Hata varsa exit kodu sıfırdan farklı.** Bu betikler deploy kapısı olarak
   kullanılıyor.
5. **Kodda, örneklerde ve dokümanda anahtar ya da iç hostname olmaz.**
   `10.0.0.10`, `example.com`, `sk-xxx` kullanın.
6. **Her betik iki seviyelidir.** Parametresiz çalıştırıldığında o alanın en
   basit sorusunu yanıtlamalı ("çalışıyor mu?"); detay parametrelerin arkasında
   durmalı. Yeni bir betik, kullanıcıyı önce kılavuz okumaya zorlamamalı.

## Dil ve kodlama

- **Dokümanlar ve kullanıcıya görünen metinler Türkçedir.** Teknik terimler
  (endpoint, token, streaming, embedding, throughput, exit code, batch…)
  İngilizce kalır — çeviri onları anlaşılmaz yapar.
- **Değişmeyenler:** parametre adları, ortam değişkenleri, JSON alanları, tablo
  başlıkları ve `prompt=… completion=… tok/s` gibi `anahtar=değer` tanılama
  satırları. Bunlar makine tarafından ayrıştırılıyor.
- **Kodlama:** `.ps1` dosyaları **UTF-8 BOM** ile kaydedilir — Windows
  PowerShell 5.1 BOM olmadan dosyayı sistem kod sayfasıyla okur ve Türkçe
  karakterleri bozar. Python betikleri açılışta stdout/stderr'i UTF-8'e sabitler,
  çünkü Windows konsolu varsayılan olarak cp1252'dir. Bash betikleri düz UTF-8'dir
  (BOM yok) ve kaynak içindeki yorumlar ASCII harflerle yazılır.

## PR açmadan önce

```bash
python3 tests/smoke_test.py       # yeşil olmalı; yeni davranış için kontrol ekleyin
bash -n bash/llm-prompt.sh
bash -n bash/llm-models.sh
python3 -m compileall -q python examples tests
```

PowerShell betiklerine dokunduysanız smoke testi `pwsh` kurulu bir makinede
çalıştırın; aksi halde PowerShell kontrolleri atlanır.

CI aynı smoke testi Ubuntu, macOS ve Windows'ta koşar; ayrıca ShellCheck ve
PSScriptAnalyzer'ı error seviyesinde çalıştırır.

## Doküman yazarken

Okuyucu dokümana baktığında iki şeyi hemen anlamalı: **ne çalıştıracağını** ve
**sonucu nasıl yorumlayacağını.** Bunun için her bölüm şu sırayla yazılır:

1. Komut (kopyala-yapıştır çalışacak halde)
2. Beklenen çıktı (gerçekten çalıştırılmış, birebir)
3. "Geçti sayılır" — neye bakarak tamam denecek
4. "Değişen" — koşumlar arasında farklılaşacak kısımlar
5. Sayı üreten bir çıktı varsa: o sayı hangi aralıkta ne anlama geliyor

Yeni bir terim geçiriyorsanız [docs/glossary.md](docs/glossary.md) dosyasına
ekleyin; sözlük "hangi değeri görünce ne düşünmeli" sorusuna cevap verir.

## Yeni betik eklerken

Betiği çalışma ortamının klasörüne koyun (`bash/`, `powershell/`, `python/`),
`--help` ekleyin, `tests/smoke_test.py` içine bağlayın ve `README.md`'deki
tabloya işleyin. Yeni bir API yüzeyini hedefliyorsa `docs/` altına bir referans
sayfası, runbook'lara da **komut + birebir beklenen çıktı** ekleyin.

Bu deponun sözü şu: dokümanda yazan her çıktı gerçekten çalıştırılıp
doğrulanmıştır. Hafızadan yazılmış örnek eklemeyin.

## Backend davranışı bildirmek

En değerli issue'lar "şu backend farklı davranıyor" diyenler. Sunucu ve
sürümünü, isteği (`-v` çıktısı) ve yanıtı (`--raw`) ekleyin. Bunlar
[docs/compatibility.md](docs/compatibility.md) dosyasına işleniyor.
