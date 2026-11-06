$ErrorActionPreference = 'Stop'
Set-Location 'C:/LocalWorkspace/ai-flux-gateway-public'
$name = 'poc-recovery-readonly-20261029-' + (Get-Date).ToUniversalTime().ToString('HHmmssfffffff') + '-' + $PID
$folder = Join-Path (Join-Path $PWD '.deployment') $name
if (Test-Path $folder) { throw 'exclusive_evidence_required' }
New-Item -ItemType Directory -Path $folder | Out-Null
$identity = whoami /user /fo csv /nh
$sid = [regex]::Match(($identity | Out-String), 'S-1-5-[0-9-]+').Value
if (-not $sid) { throw 'local_identity_required' }
icacls $folder /inheritance:r /grant:r ('*' + $sid + ':(OI)(CI)F') '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'evidence_acl_failed' }
function Read-RecoveryWorkers {
    Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python|terraform|pwsh|powershell|bash' } | ForEach-Object {
        @{
            pid = $_.ProcessId
            name = $_.Name
            this_collector = ([string]$_.CommandLine -match 'poc_recovery_readonly_oct29')
            mutation_worker = ([string]$_.CommandLine -match 'poc_activation_publish|poc_publisher_reliability|terraform.*apply|poc_activation_release (apply|plan)|customer_login_release (apply|plan)|poc_activation_prepare (build|prepare)')
        }
    }
}
$before = @(Read-RecoveryWorkers)
$before | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 (Join-Path $folder 'workers-before.json')
if (@($before | Where-Object { $_.mutation_worker -and -not $_.this_collector }).Count -gt 0) { throw 'mutation_worker_review_required' }
$env:PYTHONPATH = "$PWD;$PWD/services/control-plane/src;$PWD/.venv/Lib/site-packages"
$env:PYTHONDONTWRITEBYTECODE = '1'
& 'C:/Program Files/Python313/python.exe' -X utf8 -u -m scripts.deployment.poc_recovery_readonly_oct29 $folder
$result = $LASTEXITCODE
$after = @(Read-RecoveryWorkers)
$after | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 (Join-Path $folder 'workers-after.json')
$conflicts = @($before + $after | Where-Object { $_.mutation_worker -and -not $_.this_collector })
@{ evidence_directory = ('.deployment/' + $name); mutation_worker_count = $conflicts.Count; collector_exit_code = $result } | ConvertTo-Json -Compress
if ($conflicts.Count -gt 0) { exit 3 }
exit $result