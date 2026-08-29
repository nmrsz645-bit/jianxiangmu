param(
    [string]$BaseDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Ensure-Dir([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Read-TextUtf8([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "missing file: $Path"
    }
    return [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
}

function Find-Value([string]$Text, [string]$Name) {
    $fullColon = [string][char]0xFF1A
    $lines = @($Text -split "`r?`n")
    for ($i = 0; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]
        $trimmed = $line.Trim()
        if (-not $trimmed.StartsWith($Name)) {
            continue
        }
        $idx = $trimmed.IndexOf(":")
        if ($idx -lt 0) {
            $idx = $trimmed.IndexOf($fullColon)
        }
        if ($idx -ge 0) {
            return $trimmed.Substring($idx + 1).Trim()
        }
        $tail = $trimmed.Substring($Name.Length).Trim()
        $tail = [regex]::Replace($tail, "^[^A-Za-z0-9]+", "")
        if (-not $tail -and ($i + 1) -lt $lines.Count) {
            $tail = $lines[$i + 1].Trim()
        }
        return $tail
    }
    return ""
}

function Extract-CallbackUrl([string]$Text) {
    $matches = [regex]::Matches($Text, "https?://[^\s\]\)]+auth_code=[^\s\]\)]+")
    if ($matches.Count -eq 0) {
        return ""
    }
    return $matches[$matches.Count - 1].Value.Trim()
}

function Read-AccountOverrideIds([string]$Root) {
    $ids = @()
    foreach ($file in (Get-ChildItem -LiteralPath $Root -Filter "*.txt")) {
        if ($file.PSIsContainer) {
            continue
        }
        $content = [System.IO.File]::ReadAllText($file.FullName, [System.Text.Encoding]::UTF8)
        if ($content -match "APP_ID|Secret|auth_code|callback") {
            continue
        }
        foreach ($match in [regex]::Matches($content, "\b\d{10,}\b")) {
            $ids += $match.Value
        }
    }
    $seen = @{}
    $out = @()
    foreach ($id in $ids) {
        if (-not $seen.ContainsKey($id)) {
            $seen[$id] = $true
            $out += $id
        }
    }
    return $out
}

function Invoke-JsonPost([string]$Url, [hashtable]$Body, [hashtable]$Headers = @{}) {
    $json = $Body | ConvertTo-Json -Depth 10 -Compress
    return Invoke-RestMethod -Method Post -Uri $Url -Headers $Headers -ContentType "application/json" -Body $json -TimeoutSec 60
}

function Invoke-JsonGet([string]$Url, [hashtable]$Headers) {
    return Invoke-RestMethod -Method Get -Uri $Url -Headers $Headers -TimeoutSec 80
}

function Save-Json($Object, [string]$Path) {
    $json = $Object | ConvertTo-Json -Depth 20
    [System.IO.File]::WriteAllText($Path, $json, (New-Object System.Text.UTF8Encoding($false)))
}

$configDir = Join-Path $BaseDir "config"
$dataDir = Join-Path $BaseDir "data"
$logDir = Join-Path $BaseDir "logs"
Ensure-Dir $configDir
Ensure-Dir $dataDir
Ensure-Dir $logDir

$interfacePath = Get-ChildItem -LiteralPath $BaseDir -Filter "*.txt" |
    Where-Object {
        -not $_.PSIsContainer -and
        [System.IO.File]::ReadAllText($_.FullName, [System.Text.Encoding]::UTF8) -match "APP_ID" -and
        [System.IO.File]::ReadAllText($_.FullName, [System.Text.Encoding]::UTF8) -match "auth_code"
    } |
    Select-Object -First 1 -ExpandProperty FullName
if (-not $interfacePath) {
    throw "missing Qianchuan interface txt file with APP_ID and auth_code"
}
$raw = Read-TextUtf8 $interfacePath
$appId = Find-Value $raw "APP_ID"
$secret = Find-Value $raw "Secret"
$callbackUrl = Extract-CallbackUrl $raw
if (-not $appId -or -not $secret -or -not $callbackUrl) {
    throw "Qianchuan interface txt must include APP_ID, Secret, and callback URL with auth_code"
}

$authMatch = [regex]::Match($callbackUrl, "(?:\?|&)auth_code=([^&]+)")
$authCode = ""
if ($authMatch.Success) {
    $authCode = [Uri]::UnescapeDataString($authMatch.Groups[1].Value)
}
if (-not $authCode) {
    throw "callback URL has no auth_code"
}

$config = [ordered]@{
    app_id = $appId
    secret = $secret
    callback_url = $callbackUrl
    auth_code_present = $true
    imported_at = (Get-Date).ToString("s")
}
Save-Json $config (Join-Path $configDir "qianchuan_config.json")

$tokensPath = Join-Path $dataDir "tokens.json"
$tokenResult = $null
$tokenMode = ""
$resp = Invoke-JsonPost "https://api.oceanengine.com/open_api/oauth2/access_token/" @{
    app_id = $appId
    secret = $secret
    grant_type = "auth_code"
    auth_code = $authCode
}
if ($resp.code -ne 0) {
    throw "auth exchange failed: $($resp.message)"
}
$tokenResult = $resp.data
$tokenMode = "auth_code"

$now = [int][double]::Parse((Get-Date -UFormat %s))
$authorizedAdvertiserIds = @()
if ($tokenResult.advertiser_ids) {
    foreach ($item in $tokenResult.advertiser_ids) {
        $authorizedAdvertiserIds += [string]$item
    }
}
$advertiserIds = @($authorizedAdvertiserIds)
$overrideAdvertiserIds = Read-AccountOverrideIds $BaseDir
if ($overrideAdvertiserIds.Count -gt 0) {
    $advertiserIds = $overrideAdvertiserIds
}
if ($advertiserIds.Count -eq 0) {
    $tokenForQuery = [Uri]::EscapeDataString($tokenResult.access_token)
    $accountResult = Invoke-JsonGet "https://api.oceanengine.com/open_api/oauth2/advertiser/get/?access_token=$tokenForQuery" @{ "Access-Token" = $tokenResult.access_token }
    if ($accountResult.code -eq 0 -and $accountResult.data -and $accountResult.data.list) {
        foreach ($account in @($accountResult.data.list)) {
            if ($account.advertiser_id) {
                $advertiserIds += [string]$account.advertiser_id
            } elseif ($account.account_id) {
                $advertiserIds += [string]$account.account_id
            }
        }
    }
}
$tokenStore = [ordered]@{
    app_id = $appId
    access_token = $tokenResult.access_token
    refresh_token = $tokenResult.refresh_token
    expires_at = $now + [int]$tokenResult.expires_in
    refresh_expires_at = $now + [int]$tokenResult.refresh_token_expires_in
    advertiser_ids = $advertiserIds
    authorized_advertiser_ids = $authorizedAdvertiserIds
    updated_at = $now
    token_mode = $tokenMode
}
Save-Json $tokenStore $tokensPath

$allProjects = @()
foreach ($advertiserId in $advertiserIds) {
    $page = 1
    $accountProjects = @()
    $accountError = ""
    try {
        while ($true) {
            $url = "https://api.oceanengine.com/open_api/v3.0/project/list/?advertiser_id=$advertiserId&page=$page&page_size=100"
            $result = Invoke-JsonGet $url @{ "Access-Token" = $tokenResult.access_token }
            if ($result.code -ne 0) {
                throw "project list failed for $advertiserId`: $($result.message)"
            }
            $list = @()
            if ($result.data -and $result.data.list) {
                $list = @($result.data.list)
            }
            foreach ($project in $list) {
                $accountProjects += $project
            }
            if ($list.Count -lt 100) {
                break
            }
            $page += 1
        }
    } catch {
        $accountError = $_.Exception.Message
    }
    $allProjects += [ordered]@{
        advertiser_id = $advertiserId
        count = $accountProjects.Count
        error = $accountError
        projects = $accountProjects
    }
}

$report = [ordered]@{
    app_id = $appId
    token_mode = $tokenMode
    advertiser_count = $advertiserIds.Count
    advertisers = $allProjects
    generated_at = (Get-Date).ToString("s")
}
Save-Json $report (Join-Path $dataDir "qianchuan_projects.json")

"app_id=$appId"
"token_mode=$tokenMode"
"authorized_advertiser_ids=$($authorizedAdvertiserIds -join ',')"
"override_advertiser_ids=$($overrideAdvertiserIds -join ',')"
"advertiser_ids=$($advertiserIds -join ',')"
foreach ($account in $allProjects) {
    "account $($account.advertiser_id) projects=$($account.count)"
    if ($account.error) {
        "  ERROR $($account.error)"
    }
    foreach ($project in $account.projects) {
        $name = $project.name
        if (-not $name) { $name = $project.project_name }
        "  - $name | id=$($project.project_id)"
    }
}
