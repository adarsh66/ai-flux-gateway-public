$ErrorActionPreference = 'Stop'
Set-Location 'C:/LocalWorkspace/ai-flux-gateway-public'
$name = 'poc-publisher-recheck-20261029-' + (Get-Date).ToUniversalTime().ToString('HHmmssfffffff') + '-' + $PID
$folder = Join-Path (Join-Path $PWD '.deployment') $name
if (Test-Path $folder) { throw 'exclusive_evidence_required' }
New-Item -ItemType Directory -Path $folder | Out-Null
$identity = whoami /user /fo csv /nh
$sid = [regex]::Match(($identity | Out-String), 'S-1-5-[0-9-]+').Value
if (-not $sid) { throw 'local_identity_required' }
icacls $folder /inheritance:r /grant:r ('*' + $sid + ':(OI)(CI)F') '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'evidence_acl_failed' }

function Read-WorkerMetadata {
    Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python|terraform|azmcp|pwsh|powershell|bash' } | ForEach-Object {
        @{
            pid = $_.ProcessId
            name = $_.Name
            workspace_worker = ([string]$_.CommandLine -match 'ai-flux-gateway-public|scripts\.deployment|scripts/deployment')
            this_collector = ([string]$_.CommandLine -match 'poc_publisher_recheck_oct29')
            mutation_worker = ([string]$_.CommandLine -match 'poc_activation_publish|poc_publisher_reliability|terraform.*apply|poc_activation_release (apply|plan)|customer_login_release (apply|plan)|poc_activation_prepare (build|prepare)')
            readonly_worker = ([string]$_.CommandLine -match 'read.only|readback|recheck|snapshot|checkpoint|audit')
        }
    }
}

$before = @(Read-WorkerMetadata)
$before | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 (Join-Path $folder 'workers-before.json')
# Structural local marker reconciliation only: never invoke an old entrypoint.
$markers = @(Get-ChildItem .deployment -Directory -Filter 'poc*' | Where-Object { $_.Name -ne $name } | ForEach-Object {
    $root = $_.FullName
    @($root; (Get-ChildItem $root -Directory | Where-Object { $_.Name -notmatch 'context|infra|gateway|services|node_modules|\.terraform' }).FullName) | ForEach-Object {
        Get-ChildItem $_ -File | Where-Object { $_.Name -match 'intent|completion|verified|checkpoint|restored|failure|blocker' -and $_.Extension -eq '.json' } | ForEach-Object {
            @{ path = $_.FullName.Substring($PWD.Path.Length + 1).Replace('\', '/'); sha256 = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant(); last_write_utc = $_.LastWriteTimeUtc.ToString('o') }
        }
    }
})
$markers | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 (Join-Path $folder 'historical-marker-metadata.json')
$env:PYTHONPATH = "$PWD;$PWD/services/control-plane/src;$PWD/.venv/Lib/site-packages"
$env:PYTHONDONTWRITEBYTECODE = '1'
& 'C:/Program Files/Python313/python.exe' -X utf8 -u -m scripts.deployment.poc_publisher_recheck_oct29 $folder
$result = $LASTEXITCODE
$after = @(Read-WorkerMetadata)
$after | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 (Join-Path $folder 'workers-after.json')
$conflicts = @($before + $after | Where-Object { $_.mutation_worker -and -not $_.this_collector })
@{ evidence_directory = ('.deployment/' + $name); mutation_worker_count = $conflicts.Count; collector_exit_code = $result; workers_after_sha256 = (Get-FileHash (Join-Path $folder 'workers-after.json') -Algorithm SHA256).Hash.ToLowerInvariant() } | ConvertTo-Json -Compress
if ($conflicts.Count -gt 0) { exit 3 }
exit $result