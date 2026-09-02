#Requires -Version 5.1
<#
.SYNOPSIS
    OpenAI uyumlu bir /v1/chat/completions endpoint'ine tek prompt gönderir
    (vLLM, TGI-OpenAI shim, llama.cpp server, Ollama, OpenAI, Azure uyumlu
    gateway'ler). Yalnızca .NET kullanır - curl / curl.exe gerekmez.

.DESCRIPTION
    bash/llm-prompt.sh betiğinin PowerShell karşılığı. Windows PowerShell 5.1
    üzerinde işleri bozan iki şeyi çözer: TLS 1.2 anlaşması ve istek/yanıtın
    UTF-8 kodlaması (Türkçe karakterler).

.PARAMETER Endpoint
    Temel URL (http://host:8000), .../v1 ya da tam .../v1/chat/completions.
    Verilmezse $env:LLM_ENDPOINT kullanılır.

.PARAMETER Stream
    Token'ları geldikçe yazdırır (SSE). Invoke-WebRequest yanıtı parça parça
    okuyamadığı için bu modda HttpClient kullanılır.

.EXAMPLE
    .\Invoke-LlmPrompt.ps1 "Merhaba, kendini tanit" `
        -Endpoint http://10.0.0.10:8000 `
        -ApiKey sk-xxx `
        -Model Qwen/Qwen2.5-7B-Instruct

.EXAMPLE
    $env:LLM_ENDPOINT = 'https://api.example.com/v1'
    $env:LLM_API_KEY  = 'sk-xxx'
    $env:LLM_MODEL    = 'my-model'
    .\Invoke-LlmPrompt.ps1 "2+2 kac?" -Verbose

.EXAMPLE
    .\Invoke-LlmPrompt.ps1 "Bir haiku yaz" -Stream
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory, Position = 0)]
    [string]$Prompt,

    # Temel URL (http://host:8000), .../v1 ya da tam .../v1/chat/completions
    # Kısa biçimler Bash betiğiyle aynı: -e, -k, -m, -s, -t, -n, -i
    [Alias('e')]
    [string]$Endpoint = $env:LLM_ENDPOINT,

    [Alias('k')]
    [string]$ApiKey = $env:LLM_API_KEY,

    [Alias('m')]
    [string]$Model = $env:LLM_MODEL,

    [Alias('s')]
    [string]$SystemPrompt,

    [Alias('t')]
    [ValidateRange(0.0, 2.0)]
    [double]$Temperature = 0.0,

    [Alias('n')]
    [ValidateRange(1, 1000000)]
    [int]$MaxTokens = 512,

    [Alias('timeout')]
    [ValidateRange(1, 86400)]
    [int]$TimeoutSec = 300,

    # Yanıtın tamamını beklemek yerine token'ları geldikçe yazdır
    [switch]$Stream,

    # Sadece asistan mesajı yerine tam JSON yanıtını yazdır
    [switch]$Raw,

    # TLS sertifika doğrulamasını atla (self-signed iç endpoint'ler)
    [Alias('i')]
    [switch]$Insecure
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$required = [ordered]@{ Endpoint = 'LLM_ENDPOINT'; ApiKey = 'LLM_API_KEY'; Model = 'LLM_MODEL' }
foreach ($p in $required.Keys) {
    if ([string]::IsNullOrWhiteSpace((Get-Variable $p -ValueOnly))) {
        [Console]::Error.WriteLine("-$p parametresi gerekli (ya da `$env:$($required[$p]) ayarlayın).")
        exit 1
    }
}

function Resolve-ChatUri {
    param([string]$Base)
    $u = $Base.TrimEnd('/')
    if ($u -match '/chat/completions$') { return $u }
    if ($u -match '/v1$') { return "$u/chat/completions" }
    return "$u/v1/chat/completions"
}

function Write-Fail {
    # Bash betiğiyle aynı hata çıktısı: düz bir stderr satırı, sonra exit 1.
    # PowerShell'in çok satırlı hata bloğunu kullanmayız ki iki betiğin çıktısı
    # birebir karşılaştırılabilsin.
    param([string]$Message)
    [Console]::Error.WriteLine($Message)
    exit 1
}

function Expand-JsonEscapes {
    # PowerShell 7, JSON hata gövdelerini yeniden serialize ederken ASCII dışı
    # karakterleri \uXXXX olarak kaçırır; Türkçe mesajlar okunmaz hale gelir.
    param([string]$Text)
    if ($Text -and $Text -match '\\u[0-9a-fA-F]{4}') {
        try { return [Regex]::Unescape($Text) } catch { return $Text }
    }
    return $Text
}

function Test-HasProperty {
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $false }
    return $null -ne $Object.PSObject.Properties[$Name]
}

$uri = Resolve-ChatUri $Endpoint
$isPS5 = $PSVersionTable.PSVersion.Major -lt 6

if ($isPS5) {
    # 5.1 bazı makinelerde SSL3/TLS1.0 ile başlar
    [Net.ServicePointManager]::SecurityProtocol =
        [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    if ($Insecure) { [Net.ServicePointManager]::ServerCertificateValidationCallback = { $true } }
}

# [ordered]: düz hashtable'ın anahtar sırası PowerShell'de garanti değildir ve
# istek gövdesi koşumdan koşuma farklı yazılırdı. Bash betiği her zaman
# role,content sırasıyla üretiyor; ikisinin çıktısı karşılaştırılabilir kalmalı.
$messages = @()
if (-not [string]::IsNullOrWhiteSpace($SystemPrompt)) {
    $messages += [ordered]@{ role = 'system'; content = $SystemPrompt }
}
$messages += [ordered]@{ role = 'user'; content = $Prompt }

$payload = [ordered]@{
    model       = $Model
    messages    = $messages
    temperature = $Temperature
    max_tokens  = $MaxTokens
    stream      = [bool]$Stream
}

$json = $payload | ConvertTo-Json -Depth 6 -Compress
# Ham UTF-8 byte gönder: PS 5.1 aksi halde gövdeyi ISO-8859-1 kodlar ve
# Türkçe karakterleri bozar.
$body = [Text.Encoding]::UTF8.GetBytes($json)

Write-Verbose "POST $uri"
Write-Verbose "Body: $json"

# --- streaming yolu ---------------------------------------------------------
# Invoke-WebRequest yanıtın tamamını tamponlar; SSE için HttpClient gerekir.
if ($Stream) {
    if ($isPS5) { Add-Type -AssemblyName System.Net.Http -ErrorAction SilentlyContinue }

    $handler = [Net.Http.HttpClientHandler]::new()
    if ($Insecure -and -not $isPS5) {
        $handler.ServerCertificateCustomValidationCallback =
            [Net.Http.HttpClientHandler]::DangerousAcceptAnyServerCertificateValidator
    }
    $client = [Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromSeconds($TimeoutSec)

    $req = [Net.Http.HttpRequestMessage]::new([Net.Http.HttpMethod]::Post, $uri)
    $req.Headers.Authorization = [Net.Http.Headers.AuthenticationHeaderValue]::new('Bearer', $ApiKey)
    $req.Headers.Accept.Add([Net.Http.Headers.MediaTypeWithQualityHeaderValue]::new('text/event-stream'))
    $req.Content = [Net.Http.ByteArrayContent]::new($body)
    $req.Content.Headers.ContentType =
        [Net.Http.Headers.MediaTypeHeaderValue]::Parse('application/json; charset=utf-8')

    $reader = $null
    $responseStream = $null
    try {
        $resp = $client.SendAsync($req, [Net.Http.HttpCompletionOption]::ResponseHeadersRead).
            GetAwaiter().GetResult()

        if (-not $resp.IsSuccessStatusCode) {
            $errBody = $resp.Content.ReadAsStringAsync().GetAwaiter().GetResult()
            Write-Fail ("HTTP {0} from {1}`n{2}" -f [int]$resp.StatusCode, $uri, $errBody)
        }

        $responseStream = $resp.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $reader = [IO.StreamReader]::new($responseStream, [Text.Encoding]::UTF8)
        while (-not $reader.EndOfStream) {
            $line = $reader.ReadLine()
            if (-not $line.StartsWith('data:')) { continue }
            $data = $line.Substring(5).Trim()
            if ($data -eq '[DONE]') { break }
            try { $chunk = $data | ConvertFrom-Json } catch { continue }
            # Yalnızca usage taşıyan ya da bitiş chunk'ı choices içermez veya
            # delta'sı boştur; StrictMode böyle bir erişimi hataya çevirir.
            if (-not (Test-HasProperty $chunk 'choices')) { continue }
            foreach ($choice in $chunk.choices) {
                if (-not (Test-HasProperty $choice 'delta')) { continue }
                $delta = $choice.delta
                if (-not (Test-HasProperty $delta 'content')) { continue }
                $piece = $delta.content
                if ($piece) { [Console]::Out.Write($piece); [Console]::Out.Flush() }
            }
        }
        [Console]::Out.Write("`n")
    }
    catch {
        Write-Fail ("Streaming isteği başarısız: {0} - {1}" -f $uri, $_.Exception.Message)
    }
    finally {
        if ($reader) { $reader.Dispose() }
        elseif ($responseStream) { $responseStream.Dispose() }
        $client.Dispose()
    }
    exit 0
}

# --- streaming olmayan yol --------------------------------------------------
$requestArgs = @{
    Uri             = $uri
    Method          = 'Post'
    Headers         = @{
        Authorization = "Bearer $ApiKey"
        Accept        = 'application/json'
    }
    ContentType     = 'application/json; charset=utf-8'
    Body            = $body
    TimeoutSec      = $TimeoutSec
    UseBasicParsing = $true
}
if ($Insecure -and -not $isPS5) { $requestArgs['SkipCertificateCheck'] = $true }

$sw = [Diagnostics.Stopwatch]::StartNew()
try {
    $resp = Invoke-WebRequest @requestArgs
}
catch {
    $status = $null
    $errBody = $null
    if ((Test-HasProperty $_.Exception 'Response') -and $_.Exception.Response) {
        try { $status = [int]$_.Exception.Response.StatusCode } catch { }
    }
    if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
        $errBody = Expand-JsonEscapes $_.ErrorDetails.Message
    }
    elseif ($isPS5 -and $_.Exception.Response) {
        $reader = New-Object IO.StreamReader($_.Exception.Response.GetResponseStream(), [Text.Encoding]::UTF8)
        $errBody = $reader.ReadToEnd()
        $reader.Dispose()
    }
    if ($status) {
        Write-Fail ("HTTP {0} from {1}`n{2}" -f $status, $uri, $errBody)
    }
    Write-Fail ("İstek başarısız: {0} - {1}" -f $uri, $_.Exception.Message)
}
$sw.Stop()

# Açıkça çöz: sunucu charset göndermezse PS 5.1 ISO-8859-1 varsayar.
$text = [Text.Encoding]::UTF8.GetString($resp.RawContentStream.ToArray())

if ($Raw) { $text; exit 0 }

try { $obj = $text | ConvertFrom-Json }
catch { Write-Fail "JSON olmayan yanıt:`n$text" }

if (-not (Test-HasProperty $obj 'choices') -or -not $obj.choices) {
    Write-Fail "Beklenmeyen yanıt gövdesi:`n$text"
}

$obj.choices[0].message.content

if ((Test-HasProperty $obj 'usage') -and $obj.usage) {
    $sec = [math]::Round($sw.Elapsed.TotalSeconds, 2)
    $tps = if ($sw.Elapsed.TotalSeconds -gt 0) {
        [math]::Round($obj.usage.completion_tokens / $sw.Elapsed.TotalSeconds, 1)
    } else { 0 }
    # InvariantCulture: tr-TR bir makinede aksi halde "0,02s" yazılır ve bu
    # satırı ayrıştıran her şey bozulur.
    Write-Verbose ([string]::Format([cultureinfo]::InvariantCulture,
        "prompt={0} completion={1} total={2} | {3}s | {4} tok/s | finish={5}",
        $obj.usage.prompt_tokens, $obj.usage.completion_tokens, $obj.usage.total_tokens,
        $sec, $tps, $obj.choices[0].finish_reason))
}
