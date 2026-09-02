#Requires -Version 5.1
<#
.SYNOPSIS
    OpenAI uyumlu bir endpoint'in gerçekte ne servis ettiğini gösterir:
    /v1/models listeler, filtreler, bir modelin varlığını doğrular ve isteğe
    bağlı olarak her modele tek token'lık istek atıp hangisinin çalıştığını ölçer.

.DESCRIPTION
    bash/llm-models.sh betiğinin PowerShell karşılığı. Yalnızca .NET kullanır -
    curl.exe gerekmez - ve nesne döndürür; böylece çıktı ayrıştırılmak yerine
    Where-Object, Sort-Object ve Export-Csv ile doğrudan zincirlenebilir.

.PARAMETER Pattern
    Model id'sinde büyük/küçük harf duyarsız altdizi filtresi.

.PARAMETER Has
    Yalnızca bu model id'si birebir servis ediliyorsa exit 0, aksi halde 1.
    "grep -q" gibi sessiz çalışır - deploy kapıları için düşünülmüştür.

.PARAMETER Probe
    Listedeki her modele 1 token'lık chat isteği gönderir ve hangisinin cevap
    verdiğini yazar. Biri bile hata verirse exit 1.

.EXAMPLE
    .\Get-LlmModels.ps1
    .\Get-LlmModels.ps1 -Long
    .\Get-LlmModels.ps1 qwen
    .\Get-LlmModels.ps1 -Has 'Qwen/Qwen2.5-7B-Instruct'
    .\Get-LlmModels.ps1 -Probe

.EXAMPLE
    .\Get-LlmModels.ps1 -Long | Where-Object Context -gt 8192 | Sort-Object Model
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Pattern,

    # Temel URL (http://host:8000), .../v1 ya da tam .../v1/models
    # Kısa biçimler Bash betiğiyle aynı: -e, -k, -l, -i
    [Alias('e')]
    [string]$Endpoint = $env:LLM_ENDPOINT,

    [Alias('k')]
    [string]$ApiKey = $env:LLM_API_KEY,

    # Sadece id yerine id, sahip, oluşturulma ve context uzunluğunu yaz
    [Alias('l')]
    [switch]$Long,

    # Ham JSON yanıtını yazdır
    [switch]$Json,

    [string]$Has,

    [switch]$Probe,

    [Alias('timeout')]
    [ValidateRange(1, 86400)]
    [int]$TimeoutSec = 60,

    # TLS sertifika doğrulamasını atla (self-signed iç endpoint'ler)
    [Alias('i')]
    [switch]$Insecure
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-Fail {
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

$required = [ordered]@{ Endpoint = 'LLM_ENDPOINT'; ApiKey = 'LLM_API_KEY' }
foreach ($p in $required.Keys) {
    if ([string]::IsNullOrWhiteSpace((Get-Variable $p -ValueOnly))) {
        [Console]::Error.WriteLine("-$p parametresi gerekli (ya da `$env:$($required[$p]) ayarlayın).")
        exit 1
    }
}

function Resolve-BaseUri {
    param([string]$Base)
    $u = $Base.TrimEnd('/')
    if ($u -match '/models$')           { return $u -replace '/models$', '' }
    if ($u -match '/chat/completions$') { return $u -replace '/chat/completions$', '' }
    if ($u -match '/v1$')               { return $u }
    return "$u/v1"
}

$baseUri   = Resolve-BaseUri $Endpoint
$modelsUri = "$baseUri/models"
$chatUri   = "$baseUri/chat/completions"
$isPS5     = $PSVersionTable.PSVersion.Major -lt 6

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

function Get-ErrorBody {
    # PS 7 yanıt gövdesini ErrorDetails'e koyar; 5.1'de ham stream okunmalı.
    param($ErrorRecord)
    if ($ErrorRecord.ErrorDetails -and $ErrorRecord.ErrorDetails.Message) {
        return Expand-JsonEscapes $ErrorRecord.ErrorDetails.Message
    }
    if ((Test-HasProperty $ErrorRecord.Exception 'Response') -and $ErrorRecord.Exception.Response) {
        try {
            $reader = New-Object IO.StreamReader(
                $ErrorRecord.Exception.Response.GetResponseStream(), [Text.Encoding]::UTF8)
            $body = $reader.ReadToEnd()
            $reader.Dispose()
            return $body
        } catch { }
    }
    return $null
}

function Get-HttpStatus {
    param($ErrorRecord)
    if ((Test-HasProperty $ErrorRecord.Exception 'Response') -and $ErrorRecord.Exception.Response) {
        try { return [int]$ErrorRecord.Exception.Response.StatusCode } catch { }
    }
    return $null
}

function Get-ApiMessage {
    param([string]$Body)
    if ([string]::IsNullOrWhiteSpace($Body)) { return '' }
    try { $o = $Body | ConvertFrom-Json } catch { return ($Body -replace '\s+', ' ').Trim() }
    if ((Test-HasProperty $o 'error') -and $o.error) {
        if (Test-HasProperty $o.error 'message') { return [string]$o.error.message }
        return [string]$o.error
    }
    if (Test-HasProperty $o 'message') { return [string]$o.message }
    return ''
}

# --- istek ------------------------------------------------------------------
Write-Verbose "GET $modelsUri"
try {
    $resp = Invoke-WebRequest @common -Uri $modelsUri -Method Get
}
catch {
    $status = Get-HttpStatus $_
    $body = Get-ErrorBody $_
    if ($status) { Write-Fail ("HTTP {0} from {1}`n{2}" -f $status, $modelsUri, $body) }
    Write-Fail ("İstek başarısız: {0} - {1}" -f $modelsUri, $_.Exception.Message)
}

$text = [Text.Encoding]::UTF8.GetString($resp.RawContentStream.ToArray())
if ($Json) { $text; exit 0 }

try { $obj = $text | ConvertFrom-Json }
catch { Write-Fail "JSON olmayan yanıt:`n$text" }

if (-not (Test-HasProperty $obj 'data') -or -not $obj.data) {
    Write-Fail "Yanıtta 'data' dizisi yok:`n$text"
}

# @(...) şart: tek modelli bir sunucuda foreach skaler döndürür ve Windows
# PowerShell 5.1'de StrictMode, skalerde .Count erişimini hata sayar.
$models = @(foreach ($m in $obj.data) {
    $created = if ((Test-HasProperty $m 'created') -and $m.created) {
        [DateTimeOffset]::FromUnixTimeSeconds([int64]$m.created).UtcDateTime.
            ToString('yyyy-MM-ddTHH:mm:ssZ', [cultureinfo]::InvariantCulture)
    } else { '-' }

    $context = '-'
    foreach ($field in 'max_model_len', 'context_length', 'max_input_tokens') {
        if ((Test-HasProperty $m $field) -and $m.$field) { $context = [string]$m.$field; break }
    }

    [pscustomobject]@{
        Model       = [string]$m.id
        Sahip       = if ((Test-HasProperty $m 'owned_by') -and $m.owned_by) { [string]$m.owned_by } else { '-' }
        Olusturulma = $created
        Context     = $context
    }
})

if ($Pattern) {
    $models = @($models | Where-Object { $_.Model.ToLowerInvariant().Contains($Pattern.ToLowerInvariant()) })
}

# --- -Has -------------------------------------------------------------------
if ($Has) {
    if ($models | Where-Object { $_.Model -ceq $Has }) { exit 0 }
    Write-Fail ("'{0}' modeli {1} tarafından servis edilmiyor" -f $Has, $modelsUri)
}

if (-not $models -or $models.Count -eq 0) {
    Write-Fail ("'{0}' desenine uyan model yok" -f $Pattern)
}

# --- -Probe (model yoklama) -------------------------------------------------
if ($Probe) {
    $failed = 0
    $results = foreach ($m in $models) {
        $payload = @{
            model       = $m.Model
            messages    = @([ordered]@{ role = 'user'; content = 'ping' })
            max_tokens  = 1
            temperature = 0
        } | ConvertTo-Json -Depth 6 -Compress

        $sw = [Diagnostics.Stopwatch]::StartNew()
        try {
            $null = Invoke-WebRequest @common -Uri $chatUri -Method Post `
                -ContentType 'application/json; charset=utf-8' `
                -Body ([Text.Encoding]::UTF8.GetBytes($payload))
            $sw.Stop()
            [pscustomobject]@{ Model = $m.Model; Status = 'ok'
                               Ms = [int]$sw.Elapsed.TotalMilliseconds; Not = '' }
        }
        catch {
            $sw.Stop()
            $failed++
            $status = Get-HttpStatus $_
            $note = Get-ApiMessage (Get-ErrorBody $_)
            if (-not $status) { $note = $_.Exception.Message }
            [pscustomobject]@{
                Model  = $m.Model
                Status = if ($status) { [string]$status } else { '-' }
                Ms     = [int]$sw.Elapsed.TotalMilliseconds
                Not    = $note
            }
        }
    }

    $results | Format-Table -AutoSize | Out-String | ForEach-Object { $_.TrimEnd() } | Write-Output
    [Console]::Error.WriteLine(("{0}/{1} model cevap verdi" -f ($models.Count - $failed), $models.Count))
    if ($failed -gt 0) { exit 1 }
    exit 0
}

# --- listeleme --------------------------------------------------------------
if ($Long) { $models } else { $models | ForEach-Object { $_.Model } }
