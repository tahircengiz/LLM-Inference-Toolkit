#Requires -Version 5.1
<#
.SYNOPSIS
    Tek komutla endpoint sağlık kontrolü: erişim, kimlik doğrulama, model, chat,
    UTF-8 ve streaming. -Full ile model yoklama, embeddings ve rerank sağlık
    paketleri ve kısa bir yük testi de çalıştırılır.

.DESCRIPTION
    bash/llm-check.sh betiğinin PowerShell karşılığı. Yalnızca .NET kullanır -
    curl.exe gerekmez. -Full modu aynı klasördeki Get-LlmModels.ps1 ile
    ..\python\embed-test.py ve ..\python\chat-loadtest.py betiklerini kullanır;
    bulunmayanlar atlanır.

.EXAMPLE
    .\Test-LlmEndpoint.ps1
    .\Test-LlmEndpoint.ps1 -Full
    .\Test-LlmEndpoint.ps1 -Quiet
#>
[CmdletBinding()]
param(
    # Kısa biçimler Bash betiğiyle aynı: -e, -k, -m, -q, -i
    [Alias('e')]
    [string]$Endpoint = $env:LLM_ENDPOINT,

    [Alias('k')]
    [string]$ApiKey = $env:LLM_API_KEY,

    [Alias('m')]
    [string]$Model = $env:LLM_MODEL,

    [string]$EmbedModel = $env:LLM_EMBED_MODEL,
    [string]$RerankModel = $env:LLM_RERANK_MODEL,

    # Embedding / rerank ayrı bir adreste servis ediliyorsa
    [string]$EmbedEndpoint = $env:LLM_EMBED_ENDPOINT,
    [string]$RerankEndpoint = $env:LLM_RERANK_ENDPOINT,

    # Gelişmiş kontroller: model yoklama, embeddings ve rerank paketleri, kısa yük testi
    [switch]$Full,

    # Yalnızca son satırı yazdır (cron / CI için)
    [Alias('q')]
    [switch]$Quiet,

    [Alias('timeout')]
    [ValidateRange(1, 86400)]
    [int]$TimeoutSec = 60,

    # TLS sertifika doğrulamasını atla (self-signed iç endpoint'ler)
    [Alias('i')]
    [switch]$Insecure
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ProbePrompt = 'Şu kelimeyi aynen tekrar et: çğışöü'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Test-HasProperty {
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $false }
    return $null -ne $Object.PSObject.Properties[$Name]
}

function Expand-JsonEscapes {
    param([string]$Text)
    if ($Text -and $Text -match '\\u[0-9a-fA-F]{4}') {
        try { return [Regex]::Unescape($Text) } catch { return $Text }
    }
    return $Text
}

$required = [ordered]@{ Endpoint = 'LLM_ENDPOINT'; ApiKey = 'LLM_API_KEY'; Model = 'LLM_MODEL' }
foreach ($p in $required.Keys) {
    if ([string]::IsNullOrWhiteSpace((Get-Variable $p -ValueOnly))) {
        [Console]::Error.WriteLine("-$p parametresi gerekli (ya da `$env:$($required[$p]) ayarlayın).")
        exit 1
    }
}

function Resolve-BaseUri {
    param([string]$Base)
    $u = $Base.TrimEnd('/')
    if ($u -match '/chat/completions$') { return $u -replace '/chat/completions$', '' }
    if ($u -match '/models$')           { return $u -replace '/models$', '' }
    if ($u -match '/v1$')               { return $u }
    return "$u/v1"
}

$baseUri = Resolve-BaseUri $Endpoint
$isPS5 = $PSVersionTable.PSVersion.Major -lt 6

if ($isPS5) {
    [Net.ServicePointManager]::SecurityProtocol =
        [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    if ($Insecure) { [Net.ServicePointManager]::ServerCertificateValidationCallback = { $true } }
}

$common = @{
    Headers         = @{ Authorization = "Bearer $ApiKey"; Accept = 'application/json' }
    TimeoutSec      = $TimeoutSec
    UseBasicParsing = $true
}
if ($Insecure -and -not $isPS5) { $common['SkipCertificateCheck'] = $true }

# --- rapor ------------------------------------------------------------------
$script:Passed = 0
$script:Failed = 0
$script:Warned = 0

function Write-Satir {
    param([string]$Durum, [string]$Ad, [string]$Detay)
    switch ($Durum) {
        'PASS'  { $script:Passed++ }
        'FAIL'  { $script:Failed++ }
        'UYARI' { $script:Warned++ }
    }
    if (-not $Quiet) {
        Write-Output ("{0}{1}{2}" -f $Durum.PadRight(6), $Ad.PadRight(18), $Detay)
    }
}

function Get-ApiMessage {
    param($ErrorRecord)
    $body = $null
    if ($ErrorRecord.ErrorDetails -and $ErrorRecord.ErrorDetails.Message) {
        $body = Expand-JsonEscapes $ErrorRecord.ErrorDetails.Message
    }
    if (-not $body) { return $ErrorRecord.Exception.Message }
    try { $o = $body | ConvertFrom-Json } catch { return ($body -replace '\s+', ' ').Trim() }
    if ((Test-HasProperty $o 'error') -and $o.error) {
        if (Test-HasProperty $o.error 'message') { return [string]$o.error.message }
    }
    return ($body -replace '\s+', ' ').Trim()
}

function Get-HttpStatus {
    param($ErrorRecord)
    if ((Test-HasProperty $ErrorRecord.Exception 'Response') -and $ErrorRecord.Exception.Response) {
        try { return [int]$ErrorRecord.Exception.Response.StatusCode } catch { }
    }
    return $null
}

if (-not $Quiet) {
    Write-Output "Endpoint  $baseUri"
    Write-Output "Model     $Model"
    Write-Output ""
}

$sw = [Diagnostics.Stopwatch]::StartNew()

# --- 1/2/3: erişim, kimlik doğrulama, model listede mi ----------------------
$modelIds = @()
try {
    $resp = Invoke-WebRequest @common -Uri "$baseUri/models" -Method Get
    $text = [Text.Encoding]::UTF8.GetString($resp.RawContentStream.ToArray())
    $obj = $text | ConvertFrom-Json
    if ((Test-HasProperty $obj 'data') -and $obj.data) {
        $modelIds = @($obj.data | ForEach-Object { [string]$_.id })
    }
    Write-Satir 'PASS' 'erişim' ("HTTP 200 · {0} model listeleniyor" -f $modelIds.Count)
    Write-Satir 'PASS' 'kimlik doğrulama' 'bearer token kabul edildi'
}
catch {
    $status = Get-HttpStatus $_
    if ($status -eq 401 -or $status -eq 403) {
        Write-Satir 'FAIL' 'erişim' "HTTP $status"
        Write-Satir 'FAIL' 'kimlik doğrulama' (Get-ApiMessage $_)
    }
    elseif ($status -eq 404) {
        Write-Satir 'UYARI' 'erişim' '/v1/models yok (tek modelli sunucu olabilir)'
        Write-Satir 'UYARI' 'kimlik doğrulama' 'chat isteğinden anlaşılacak'
    }
    elseif ($status) {
        Write-Satir 'UYARI' 'erişim' ("HTTP {0} · {1}" -f $status, (Get-ApiMessage $_))
    }
    else {
        Write-Satir 'FAIL' 'erişim' ("bağlantı kurulamadı: {0}" -f $baseUri)
        if (-not $Quiet) { Write-Output "" }
        Write-Output ("Sonuç: endpoint erişilemiyor · {0}" -f $baseUri)
        exit 1
    }
}

if ($modelIds.Count -gt 0) {
    if ($modelIds -ccontains $Model) {
        Write-Satir 'PASS' 'model' 'listede var'
    } else {
        Write-Satir 'FAIL' 'model' ("'{0}' listede yok" -f $Model)
    }
} else {
    Write-Satir 'UYARI' 'model' 'liste alınamadı, chat isteğiyle denenecek'
}

# --- 4/5: chat yanıtı ve UTF-8 ----------------------------------------------
$payload = [ordered]@{
    model       = $Model
    messages    = @(@{ role = 'user'; content = $ProbePrompt })
    max_tokens  = 32
    temperature = 0
    stream      = $false
}
$json = $payload | ConvertTo-Json -Depth 6 -Compress
$body = [Text.Encoding]::UTF8.GetBytes($json)

$icerik = ''
$chatOk = $false
try {
    $resp = Invoke-WebRequest @common -Uri "$baseUri/chat/completions" -Method Post `
        -ContentType 'application/json; charset=utf-8' -Body $body
    $text = [Text.Encoding]::UTF8.GetString($resp.RawContentStream.ToArray())
    $obj = $text | ConvertFrom-Json
    $secim = $obj.choices[0]
    $icerik = [string]$secim.message.content
    $finish = if (Test-HasProperty $secim 'finish_reason') { [string]$secim.finish_reason } else { '?' }
    $tokenlar = if ((Test-HasProperty $obj 'usage') -and $obj.usage) { $obj.usage.completion_tokens } else { 0 }
    if ($icerik) {
        $chatOk = $true
        Write-Satir 'PASS' 'chat' ("yanıt geldi · {0} token · finish={1}" -f $tokenlar, $finish)
    } else {
        Write-Satir 'FAIL' 'chat' 'HTTP 200 ama içerik boş'
    }
}
catch {
    $status = Get-HttpStatus $_
    $etiket = if ($status) { "HTTP $status · " } else { '' }
    Write-Satir 'FAIL' 'chat' ("{0}{1}" -f $etiket, (Get-ApiMessage $_))
}

if ($chatOk) {
    if ($icerik.Contains([char]0xFFFD)) {
        Write-Satir 'FAIL' 'UTF-8' 'yanıtta bozuk karakter (U+FFFD) var'
    } else {
        $onizleme = $icerik -replace '\s+', ' '
        if ($onizleme.Length -gt 42) { $onizleme = $onizleme.Substring(0, 42) }
        Write-Satir 'PASS' 'UTF-8' ("geçerli · ""{0}""" -f $onizleme)
    }
} else {
    Write-Satir 'UYARI' 'UTF-8' 'chat başarısız olduğu için kontrol edilemedi'
}

# --- 6: streaming -----------------------------------------------------------
if ($isPS5) { Add-Type -AssemblyName System.Net.Http -ErrorAction SilentlyContinue }
$payload['stream'] = $true
$streamJson = $payload | ConvertTo-Json -Depth 6 -Compress
$streamBody = [Text.Encoding]::UTF8.GetBytes($streamJson)

$handler = [Net.Http.HttpClientHandler]::new()
if ($Insecure -and -not $isPS5) {
    $handler.ServerCertificateCustomValidationCallback =
        [Net.Http.HttpClientHandler]::DangerousAcceptAnyServerCertificateValidator
}
$client = [Net.Http.HttpClient]::new($handler)
$client.Timeout = [TimeSpan]::FromSeconds($TimeoutSec)
$reader = $null
$streamSw = [Diagnostics.Stopwatch]::StartNew()
try {
    $req = [Net.Http.HttpRequestMessage]::new([Net.Http.HttpMethod]::Post, "$baseUri/chat/completions")
    $req.Headers.Authorization = [Net.Http.Headers.AuthenticationHeaderValue]::new('Bearer', $ApiKey)
    $req.Headers.Accept.Add([Net.Http.Headers.MediaTypeWithQualityHeaderValue]::new('text/event-stream'))
    $req.Content = [Net.Http.ByteArrayContent]::new($streamBody)
    $req.Content.Headers.ContentType =
        [Net.Http.Headers.MediaTypeHeaderValue]::Parse('application/json; charset=utf-8')

    $sresp = $client.SendAsync($req, [Net.Http.HttpCompletionOption]::ResponseHeadersRead).
        GetAwaiter().GetResult()
    if (-not $sresp.IsSuccessStatusCode) {
        Write-Satir 'FAIL' 'streaming' ("HTTP {0}" -f [int]$sresp.StatusCode)
    } else {
        $chunkAdet = 0
        $responseStream = $sresp.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $reader = [IO.StreamReader]::new($responseStream, [Text.Encoding]::UTF8)
        while (-not $reader.EndOfStream) {
            $line = $reader.ReadLine()
            if (-not $line.StartsWith('data:')) { continue }
            $data = $line.Substring(5).Trim()
            if ($data -eq '[DONE]') { break }
            try { $chunk = $data | ConvertFrom-Json } catch { continue }
            if (-not (Test-HasProperty $chunk 'choices')) { continue }
            foreach ($secim in $chunk.choices) {
                if (-not (Test-HasProperty $secim 'delta')) { continue }
                $delta = $secim.delta
                if (-not (Test-HasProperty $delta 'content')) { continue }
                if ($delta.content) { $chunkAdet++ }
            }
        }
        $streamSw.Stop()
        if ($chunkAdet -gt 0) {
            Write-Satir 'PASS' 'streaming' ("{0} chunk · {1}ms" -f $chunkAdet, [int]$streamSw.Elapsed.TotalMilliseconds)
        } elseif ($chatOk) {
            Write-Satir 'UYARI' 'streaming' 'sunucu stream isteğini yok saymış olabilir'
        } else {
            Write-Satir 'FAIL' 'streaming' 'yanıt alınamadı'
        }
    }
}
catch {
    Write-Satir 'FAIL' 'streaming' $_.Exception.Message
}
finally {
    if ($reader) { $reader.Dispose() }
    $client.Dispose()
}

# --- gelişmiş kontroller ----------------------------------------------------
function Get-PythonExe {
    foreach ($ad in 'python3', 'python', 'py') {
        $cmd = Get-Command $ad -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

if ($Full) {
    if (-not $Quiet) { Write-Output "" }

    # Windows PowerShell 5.1, harici bir programın stderr'ine yazdığı her satırı
    # ErrorRecord'a çevirir; $ErrorActionPreference='Stop' ile bu, alt betiğin
    # tamamen normal olan özet satırını ölümcül hataya dönüştürür. Gelişmiş
    # kontroller boyunca gevşetiyoruz.
    $eskiEAP = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'

    $env:LLM_ENDPOINT = $baseUri
    $env:LLM_API_KEY = $ApiKey
    $env:LLM_MODEL = $Model

    $modelsBetik = Join-Path $ScriptDir 'Get-LlmModels.ps1'
    if (Test-Path $modelsBetik) {
        # Alt süreç olarak çağırıyoruz: Get-LlmModels.ps1 özet satırını doğrudan
        # konsol stderr'ine yazar, aynı süreç içinde çağrılınca yakalanamaz.
        $psExe = (Get-Process -Id $PID).Path
        if (-not $psExe) { $psExe = if ($isPS5) { 'powershell' } else { 'pwsh' } }
        $probe = & $psExe -NoProfile -File $modelsBetik -Probe 2>&1 | Out-String
        $satirlar = $probe -split "`r?`n" | Where-Object { $_ -match 'model cevap verdi' }
        if ($satirlar) {
            $ozet = ($satirlar | Select-Object -Last 1).Trim()
            $oran = ($ozet -split ' ')[0]
            $parcalar = $oran -split '/'
            if ($parcalar.Count -eq 2 -and $parcalar[0] -eq $parcalar[1]) {
                Write-Satir 'PASS' 'model yoklama' $ozet
            } else {
                Write-Satir 'UYARI' 'model yoklama' ("{0} (detay: Get-LlmModels.ps1 -Probe)" -f $ozet)
            }
        } else {
            Write-Satir 'UYARI' 'model yoklama' 'çalıştırılamadı'
        }
    } else {
        Write-Satir 'UYARI' 'model yoklama' 'Get-LlmModels.ps1 bulunamadı'
    }

    $py = Get-PythonExe
    $embedBetik = Join-Path $ScriptDir '..\python\embed-test.py'
    if ([string]::IsNullOrWhiteSpace($EmbedModel)) {
        Write-Satir 'UYARI' 'embeddings' 'LLM_EMBED_MODEL tanımlı değil, atlandı'
    } elseif (-not $py) {
        Write-Satir 'UYARI' 'embeddings' 'python bulunamadı, atlandı'
    } elseif (-not (Test-Path $embedBetik)) {
        Write-Satir 'UYARI' 'embeddings' 'embed-test.py bulunamadı'
    } else {
        $env:LLM_EMBED_MODEL = $EmbedModel
        if ($EmbedEndpoint) { $env:LLM_ENDPOINT = (Resolve-BaseUri $EmbedEndpoint) }
        # Alt paketin metnini değil exit kodunu esas alıyoruz: UYARI'lı geçiş
        # exit 0 döner ve bu "sağlıksız" demek değildir.
        $cikti = & $py $embedBetik --suite 2>&1 | Out-String
        $kod = $LASTEXITCODE
        $env:LLM_ENDPOINT = $baseUri
        $son = ($cikti -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -Last 1)
        if ($son) { $son = $son.Trim() } else { $son = 'yanıt yok' }
        if ($son.Length -gt 72) { $son = $son.Substring(0, 72) }
        if ($kod -eq 0 -and $son -match 'uyarı') {
            Write-Satir 'UYARI' 'embeddings' $son
        } elseif ($kod -eq 0) {
            Write-Satir 'PASS' 'embeddings' $son
        } else {
            Write-Satir 'FAIL' 'embeddings' ("{0} (detay: embed-test.py --suite)" -f $son)
        }
    }

    $rerankBetik = Join-Path $ScriptDir '..\python\rerank-test.py'
    if ([string]::IsNullOrWhiteSpace($RerankModel)) {
        Write-Satir 'UYARI' 'rerank' 'LLM_RERANK_MODEL tanımlı değil, atlandı'
    } elseif (-not $py) {
        Write-Satir 'UYARI' 'rerank' 'python bulunamadı, atlandı'
    } elseif (-not (Test-Path $rerankBetik)) {
        Write-Satir 'UYARI' 'rerank' 'rerank-test.py bulunamadı'
    } else {
        $env:LLM_RERANK_MODEL = $RerankModel
        if ($RerankEndpoint) { $env:LLM_ENDPOINT = (Resolve-BaseUri $RerankEndpoint) }
        # Alt paketin metnini değil exit kodunu esas alıyoruz: UYARI'lı geçiş
        # exit 0 döner ve bu "sağlıksız" demek değildir.
        $cikti = & $py $rerankBetik --suite 2>&1 | Out-String
        $kod = $LASTEXITCODE
        $env:LLM_ENDPOINT = $baseUri
        $son = ($cikti -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -Last 1)
        if ($son) { $son = $son.Trim() } else { $son = 'yanıt yok' }
        if ($son.Length -gt 72) { $son = $son.Substring(0, 72) }
        if ($kod -eq 0 -and $son -match 'uyarı') {
            Write-Satir 'UYARI' 'rerank' $son
        } elseif ($kod -eq 0) {
            Write-Satir 'PASS' 'rerank' $son
        } else {
            Write-Satir 'FAIL' 'rerank' ("{0} (detay: rerank-test.py --suite)" -f $son)
        }
    }

    $yukBetik = Join-Path $ScriptDir '..\python\chat-loadtest.py'
    if (-not $py) {
        Write-Satir 'UYARI' 'yük' 'python bulunamadı, atlandı'
    } elseif (-not (Test-Path $yukBetik)) {
        Write-Satir 'UYARI' 'yük' 'chat-loadtest.py bulunamadı'
    } else {
        $ham = & $py $yukBetik -n 10 -c 2 --max-tokens 32 --json 2>$null | Out-String
        try {
            $ozet = $ham | ConvertFrom-Json
            $ttft = if ((Test-HasProperty $ozet 'ttft_ms') -and $ozet.ttft_ms) { $ozet.ttft_ms.p95 } else { 0 }
            $metin = [string]::Format([cultureinfo]::InvariantCulture,
                "{0}/{1} istek · TTFT p95 {2:F0}ms · {3:F0} token/s",
                $ozet.istek_basarili, $ozet.istek_toplam, $ttft, $ozet.cikti_token_per_s)
            if ($ozet.istek_hatali -eq 0) {
                Write-Satir 'PASS' 'yük' $metin
            } else {
                Write-Satir 'FAIL' 'yük' $metin
            }
        } catch {
            Write-Satir 'FAIL' 'yük' 'yük testi çalışmadı'
        }
    }
}

if ($Full) { $ErrorActionPreference = $eskiEAP }

# --- sonuç ------------------------------------------------------------------
$sw.Stop()
$sure = [string]::Format([cultureinfo]::InvariantCulture, "{0:F1}s", $sw.Elapsed.TotalSeconds)
$toplam = $script:Passed + $script:Failed + $script:Warned
if (-not $Quiet) { Write-Output "" }
if ($script:Failed -gt 0) {
    Write-Output ("Sonuç: {0}/{1} geçti · {2} hata · {3} uyarı · endpoint SAĞLIKSIZ ({4})" -f
        $script:Passed, $toplam, $script:Failed, $script:Warned, $sure)
    exit 1
}
Write-Output ("Sonuç: {0}/{1} geçti · {2} uyarı · endpoint sağlıklı ({3})" -f
    $script:Passed, $toplam, $script:Warned, $sure)
exit 0
