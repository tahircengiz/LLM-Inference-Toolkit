#Requires -Version 5.1
<#
.SYNOPSIS
    Discover what an OpenAI-compatible endpoint actually serves: list
    /v1/models, filter it, assert a model is present, and optionally probe each
    one with a single-token request to see which are really usable.

.DESCRIPTION
    The PowerShell counterpart of bash/llm-models.sh. Uses .NET only - no
    curl.exe - and emits objects, so the output composes with Where-Object,
    Sort-Object and Export-Csv instead of needing to be parsed.

.PARAMETER Pattern
    Case-insensitive substring filter on the model id.

.PARAMETER Has
    Exit 0 only if this exact model id is served, 1 otherwise. Quiet, like
    "grep -q" - meant for deployment gates.

.PARAMETER Probe
    Send a 1-token chat request to every listed model and report which answer.
    Exits 1 if any of them fail.

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

    # Base URL (http://host:8000), .../v1 or the full .../v1/models
    [string]$Endpoint = $env:LLM_ENDPOINT,

    [string]$ApiKey = $env:LLM_API_KEY,

    # Emit id, owner, created and context length instead of ids only
    [switch]$Long,

    # Print the raw JSON response
    [switch]$Json,

    [string]$Has,

    [switch]$Probe,

    [int]$TimeoutSec = 60,

    # Skip TLS certificate validation (self-signed internal endpoints)
    [switch]$Insecure
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-Fail {
    param([string]$Message)
    [Console]::Error.WriteLine($Message)
    exit 1
}

function Test-HasProperty {
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $false }
    return $null -ne $Object.PSObject.Properties[$Name]
}

$required = [ordered]@{ Endpoint = 'LLM_ENDPOINT'; ApiKey = 'LLM_API_KEY' }
foreach ($p in $required.Keys) {
    if ([string]::IsNullOrWhiteSpace((Get-Variable $p -ValueOnly))) {
        [Console]::Error.WriteLine("-$p is required (or set `$env:$($required[$p])).")
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
    # PS 7 puts the response body in ErrorDetails; 5.1 needs the raw stream.
    param($ErrorRecord)
    if ($ErrorRecord.ErrorDetails -and $ErrorRecord.ErrorDetails.Message) {
        return $ErrorRecord.ErrorDetails.Message
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

# --- fetch ------------------------------------------------------------------
Write-Verbose "GET $modelsUri"
try {
    $resp = Invoke-WebRequest @common -Uri $modelsUri -Method Get
}
catch {
    $status = Get-HttpStatus $_
    $body = Get-ErrorBody $_
    if ($status) { Write-Fail ("HTTP {0} from {1}`n{2}" -f $status, $modelsUri, $body) }
    Write-Fail ("Request failed for {0}: {1}" -f $modelsUri, $_.Exception.Message)
}

$text = [Text.Encoding]::UTF8.GetString($resp.RawContentStream.ToArray())
if ($Json) { $text; exit 0 }

try { $obj = $text | ConvertFrom-Json }
catch { Write-Fail "Non-JSON response:`n$text" }

if (-not (Test-HasProperty $obj 'data') -or -not $obj.data) {
    Write-Fail "No 'data' array in response:`n$text"
}

$models = foreach ($m in $obj.data) {
    $created = if ((Test-HasProperty $m 'created') -and $m.created) {
        [DateTimeOffset]::FromUnixTimeSeconds([int64]$m.created).UtcDateTime.
            ToString('yyyy-MM-ddTHH:mm:ssZ', [cultureinfo]::InvariantCulture)
    } else { '-' }

    $context = '-'
    foreach ($field in 'max_model_len', 'context_length', 'max_input_tokens') {
        if ((Test-HasProperty $m $field) -and $m.$field) { $context = [string]$m.$field; break }
    }

    [pscustomobject]@{
        Model   = [string]$m.id
        Owner   = if ((Test-HasProperty $m 'owned_by') -and $m.owned_by) { [string]$m.owned_by } else { '-' }
        Created = $created
        Context = $context
    }
}

if ($Pattern) {
    $models = @($models | Where-Object { $_.Model.ToLowerInvariant().Contains($Pattern.ToLowerInvariant()) })
}

# --- -Has -------------------------------------------------------------------
if ($Has) {
    if ($models | Where-Object { $_.Model -ceq $Has }) { exit 0 }
    Write-Fail ("model '{0}' is not served by {1}" -f $Has, $modelsUri)
}

if (-not $models -or $models.Count -eq 0) {
    Write-Fail ("no model matches {0}" -f $Pattern)
}

# --- -Probe -----------------------------------------------------------------
if ($Probe) {
    $failed = 0
    $results = foreach ($m in $models) {
        $payload = @{
            model       = $m.Model
            messages    = @(@{ role = 'user'; content = 'ping' })
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
                               Ms = [int]$sw.Elapsed.TotalMilliseconds; Note = '' }
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
                Note   = $note
            }
        }
    }

    $results | Format-Table -AutoSize | Out-String | ForEach-Object { $_.TrimEnd() } | Write-Output
    [Console]::Error.WriteLine(("{0}/{1} models answered" -f ($models.Count - $failed), $models.Count))
    if ($failed -gt 0) { exit 1 }
    exit 0
}

# --- list -------------------------------------------------------------------
if ($Long) { $models } else { $models | ForEach-Object { $_.Model } }
