param([Parameter(Mandatory=$true)][string]$EvidenceDirectory)
$ErrorActionPreference = 'Stop'
Set-Location 'C:/LocalWorkspace/ai-flux-gateway-public'
if (-not (Test-Path (Join-Path $EvidenceDirectory 'completion-audit.json'))) { throw 'prior_audit_required' }
$target = Join-Path $EvidenceDirectory 'workers-current.json'
if (Test-Path $target) { throw 'exclusive_current_worker_capture_required' }
$workers = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python|terraform|pwsh|powershell|bash' } | ForEach-Object {
    @{
        pid = $_.ProcessId
        name = $_.Name
        this_collector = ([string]$_.CommandLine -match 'poc_recovery_readonly')
        mutation_worker = ([string]$_.CommandLine -match 'poc_activation_publish|poc_publisher_reliability|terraform.*apply|poc_activation_release (apply|plan)|customer_login_release (apply|plan)|poc_activation_prepare (build|prepare)')
    }
})
$workers | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $target
$env:PYTHONPATH = "$PWD;$PWD/services/control-plane/src;$PWD/.venv/Lib/site-packages"
$env:PYTHONDONTWRITEBYTECODE = '1'
& 'C:/Program Files/Python313/python.exe' -X utf8 -m scripts.deployment.poc_recovery_readonly_oct29 --audit-current $EvidenceDirectory
exit $LASTEXITCODE