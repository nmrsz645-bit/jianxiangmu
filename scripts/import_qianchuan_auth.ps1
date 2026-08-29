param(
    [string]$BaseDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"

function Find-InterfaceFile([string]$Root) {
    $match = Get-ChildItem -LiteralPath $Root -Filter "*.txt" |
        Where-Object {
            -not $_.PSIsContainer -and
            [System.IO.File]::ReadAllText($_.FullName, [System.Text.Encoding]::UTF8) -match "APP_ID" -and
            [System.IO.File]::ReadAllText($_.FullName, [System.Text.Encoding]::UTF8) -match "Secret"
        } |
        Select-Object -First 1 -ExpandProperty FullName
    if (-not $match) {
        throw "missing interface txt with APP_ID and Secret"
    }
    return $match
}

function Extract-CallbackUrl([string]$Text) {
    $matches = [regex]::Matches($Text, "https?://[^\s\]\)]+auth_code=[^\s\]\)]+")
    if ($matches.Count -eq 0) {
        return ""
    }
    return $matches[$matches.Count - 1].Value.Trim()
}

function Replace-AuthCode([string]$CallbackUrl, [string]$AuthCode) {
    if (-not $CallbackUrl) {
        throw "auth_code only is allowed only when interface txt already has a callback URL"
    }
    return [regex]::Replace($CallbackUrl, "([?&]auth_code=)[^&]+", "`$1$AuthCode")
}

function Resolve-CallbackInput([string]$InputText, [string]$ExistingText) {
    $input = $InputText.Trim()
    $existingUrl = Extract-CallbackUrl $ExistingText
    if (-not $input) {
        return $existingUrl
    }
    $url = Extract-CallbackUrl $input
    if ($url) {
        return $url
    }
    if ($input -match "^[A-Za-z0-9_-]{16,}$") {
        return Replace-AuthCode $existingUrl $input
    }
    return $input
}

function Update-CallbackUrl([string]$Path, [string]$CallbackUrl) {
    $text = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
    if ($text -notmatch "APP_ID" -or $text -notmatch "Secret") {
        throw "interface txt must include APP_ID and Secret"
    }
    if ($CallbackUrl -notmatch "^https?://.+[?&]auth_code=") {
        throw "callback URL must be a full URL containing auth_code"
    }

    $lines = @($text -split "`r?`n")
    $updated = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "callback|auth_code|https?://") {
            $lines[$i] = "callback_url: $CallbackUrl"
            $updated = $true
            break
        }
    }
    if (-not $updated) {
        $lines += "callback_url: $CallbackUrl"
    }
    [System.IO.File]::WriteAllText($Path, ($lines -join "`r`n"), (New-Object System.Text.UTF8Encoding($false)))
}

$interfacePath = Find-InterfaceFile $BaseDir
$interfaceText = [System.IO.File]::ReadAllText($interfacePath, [System.Text.Encoding]::UTF8)
"interface_file=$interfacePath"
$callbackUrl = Extract-CallbackUrl $interfaceText
if ($callbackUrl) {
    "using_callback_from_txt=true"
} else {
    "Paste full callback URL and press Enter."
    "If APP_ID or Secret changed, edit the interface txt first, then run this again."
    $callbackInput = Read-Host "callback_url"
    $callbackUrl = Resolve-CallbackInput $callbackInput $interfaceText
}
Update-CallbackUrl $interfacePath $callbackUrl
"callback_saved=true"

& (Join-Path $PSScriptRoot "probe_qianchuan.ps1") -BaseDir $BaseDir
if (-not $?) {
    exit 1
}
"auth_import_done=true"
