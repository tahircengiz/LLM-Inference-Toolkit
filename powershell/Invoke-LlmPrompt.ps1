#Requires -Version 5.1
<#
.SYNOPSIS
    Sends a single prompt to an OpenAI-compatible /v1/chat/completions endpoint
    (vLLM, TGI-OpenAI shim, llama.cpp server, Ollama, OpenAI, Azure-compatible
    gateways) using .NET only - no curl / curl.exe dependency.

.DESCRIPTION
    The PowerShell counterpart of bash/llm-prompt.sh. Handles the two things
    that usually break on Windows PowerShell 5.1: TLS 1.2 negotiation and UTF-8
    request/response encoding (Turkish characters).

.PARAMETER Endpoint
    Base URL (http://host:8000), .../v1, or the full .../v1/chat/completions.
    Falls back to $env:LLM_ENDPOINT.

.PARAMETER Stream
    Stream tokens as they arrive (SSE). Uses HttpClient instead of
    Invoke-WebRequest, which cannot read a response incrementally.

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

    # Base URL (http://host:8000), .../v1 or the full .../v1/chat/completions
    [string]$Endpoint = $env:LLM_ENDPOINT,

    [string]$ApiKey = $env:LLM_API_KEY,

    [string]$Model = $env:LLM_MODEL,

    [string]$SystemPrompt,

    [double]$Temperature = 0.0,

    [int]$MaxTokens = 512,

    [int]$TimeoutSec = 300,

    # Stream tokens as they arrive instead of waiting for the full answer
    [switch]$Stream,

    # Print the full JSON response instead of just the assistant message
    [switch]$Raw,

    # Skip TLS certificate validation (self-signed internal endpoints)
    [switch]$Insecure
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

foreach ($p in 'Endpoint', 'ApiKey', 'Model') {
    if ([string]::IsNullOrWhiteSpace((Get-Variable $p -ValueOnly))) {
        [Console]::Error.WriteLine("-$p is required (or set `$env:LLM_$($p.ToUpper())`).")
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
    # Bash-equivalent failure output: a plain stderr line, then exit 1. Avoids
    # PowerShell's multi-line error block so both scripts can be diffed.
    param([string]$Message)
    [Console]::Error.WriteLine($Message)
    exit 1
}

function Test-HasProperty {
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $false }
    return $null -ne $Object.PSObject.Properties[$Name]
}

$uri = Resolve-ChatUri $Endpoint
$isPS5 = $PSVersionTable.PSVersion.Major -lt 6

if ($isPS5) {
    # 5.1 defaults to SSL3/TLS1.0 on some hosts
    [Net.ServicePointManager]::SecurityProtocol =
        [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    if ($Insecure) { [Net.ServicePointManager]::ServerCertificateValidationCallback = { $true } }
}

$messages = @()
if (-not [string]::IsNullOrWhiteSpace($SystemPrompt)) {
    $messages += @{ role = 'system'; content = $SystemPrompt }
}
$messages += @{ role = 'user'; content = $Prompt }

$payload = [ordered]@{
    model       = $Model
    messages    = $messages
    temperature = $Temperature
    max_tokens  = $MaxTokens
    stream      = [bool]$Stream
}

$json = $payload | ConvertTo-Json -Depth 6 -Compress
# Send raw UTF-8 bytes: PS 5.1 would otherwise encode the body as ISO-8859-1
# and mangle Turkish characters.
$body = [Text.Encoding]::UTF8.GetBytes($json)

Write-Verbose "POST $uri"
Write-Verbose "Body: $json"

# --- streaming path ---------------------------------------------------------
# Invoke-WebRequest buffers the whole response, so SSE needs HttpClient.
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
            # A usage-only or finish chunk carries no choices / an empty delta,
            # and StrictMode turns a blind property access into a hard error.
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
        Write-Fail ("Streaming request failed for {0}: {1}" -f $uri, $_.Exception.Message)
    }
    finally {
        if ($reader) { $reader.Dispose() }
        elseif ($responseStream) { $responseStream.Dispose() }
        $client.Dispose()
    }
    exit 0
}

# --- non-streaming path -----------------------------------------------------
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
        $errBody = $_.ErrorDetails.Message
    }
    elseif ($isPS5 -and $_.Exception.Response) {
        $reader = New-Object IO.StreamReader($_.Exception.Response.GetResponseStream(), [Text.Encoding]::UTF8)
        $errBody = $reader.ReadToEnd()
        $reader.Dispose()
    }
    if ($status) {
        Write-Fail ("HTTP {0} from {1}`n{2}" -f $status, $uri, $errBody)
    }
    Write-Fail ("Request failed for {0}: {1}" -f $uri, $_.Exception.Message)
}
$sw.Stop()

# Decode explicitly: PS 5.1 assumes ISO-8859-1 when the server omits charset.
$text = [Text.Encoding]::UTF8.GetString($resp.RawContentStream.ToArray())

if ($Raw) { $text; exit 0 }

try { $obj = $text | ConvertFrom-Json }
catch { Write-Fail "Non-JSON response:`n$text" }

if (-not (Test-HasProperty $obj 'choices') -or -not $obj.choices) {
    Write-Fail "Unexpected response body:`n$text"
}

$obj.choices[0].message.content

if ((Test-HasProperty $obj 'usage') -and $obj.usage) {
    $sec = [math]::Round($sw.Elapsed.TotalSeconds, 2)
    $tps = if ($sw.Elapsed.TotalSeconds -gt 0) {
        [math]::Round($obj.usage.completion_tokens / $sw.Elapsed.TotalSeconds, 1)
    } else { 0 }
    # InvariantCulture: a tr-TR host would otherwise print "0,02s" and break
    # anything downstream that parses this line.
    Write-Verbose ([string]::Format([cultureinfo]::InvariantCulture,
        "prompt={0} completion={1} total={2} | {3}s | {4} tok/s | finish={5}",
        $obj.usage.prompt_tokens, $obj.usage.completion_tokens, $obj.usage.total_tokens,
        $sec, $tps, $obj.choices[0].finish_reason))
}
