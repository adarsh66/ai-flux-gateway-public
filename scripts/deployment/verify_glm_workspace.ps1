param([switch]$MetadataOnly)
$ErrorActionPreference = 'Stop'
Set-Location (Resolve-Path "$PSScriptRoot/../..")
$root = (Get-Location).Path
$env:Path = 'C:\Program Files\Terraform;C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin;' + $env:Path
$env:PYTHONPATH = "$root;$root/services/control-plane/src;$root/.venv/Lib/site-packages"
$env:TF_CLI_CONFIG_FILE = "$root/.deployment/terraform.rc"
$ca = $env:REQUESTS_CA_BUNDLE
if (!$ca) { $ca = "$HOME/.azure/ca-bundle-zscaler.pem" }
if (Test-Path $ca) {
    $env:REQUESTS_CA_BUNDLE = $ca
    $env:SSL_CERT_FILE = $ca
    $env:NODE_EXTRA_CA_CERTS = $ca
}
if ($MetadataOnly) { throw 'Use the separate metadata-only verifier.' }
$log = "$root/gateway/validation/glm-workspace-tests-20261026.txt"
Start-Transcript -Path $log -Force
try {
    Write-Output ('Verification UTC: ' + [DateTime]::UtcNow.ToString('o'))
    git status --short
    & 'C:/Program Files/Python313/python.exe' -c 'import sys, azure.identity, requests; print(sys.version); print(azure.identity.__file__); print(requests.__file__)'
    if ($LASTEXITCODE -ne 0) { throw 'Python SDK import failed' }
    & 'C:/Program Files/Python313/python.exe' -m pytest tests/unit/test_glm_secret_installer.py tests/unit/test_external_inventory.py tests/unit/test_project_route_external.py tests/unit/test_foundry_inventory.py tests/unit/test_project_route_models.py -q --junitxml=gateway/validation/glm-focused-tests-20261026.xml
    $pythonExit = $LASTEXITCODE
    & terraform '-chdir=infra/project-route' validate -no-color
    $validateExit = $LASTEXITCODE
    & terraform '-chdir=infra/project-route' test -no-color '-filter=tests\external.tftest.hcl'
    $mockExit = $LASTEXITCODE
    & terraform '-chdir=infra/project-route' test -no-color '-filter=tests\defaults.tftest.hcl'
    $defaultMockExit = $LASTEXITCODE
    & terraform '-chdir=infra/project-route' fmt -check external.tf tests/external.tftest.hcl
    $fmtExit = $LASTEXITCODE
    $ts = @{}
    foreach ($project in @('apps/admin-portal', 'apps/customer-portal', 'packages/ui')) {
        & node node_modules/typescript/bin/tsc --noEmit -p "$project/tsconfig.json"
        $ts[$project] = $LASTEXITCODE
        Write-Output "TypeScript $project exit: $LASTEXITCODE"
    }
    & node node_modules/vitest/vitest.mjs run packages/ui/src/external-provider.test.tsx --reporter=dot
    $uiExit = $LASTEXITCODE
    # Keep unrelated pre-existing disabled.tftest.hcl EOF whitespace separate.
    git diff --check -- infra/project-route/external.tf infra/project-route/tests/external.tftest.hcl scripts/deployment/glm_apim_secret.py scripts/deployment/install_glm_secret.py scripts/deployment/install_glm_secret.ps1 scripts/deployment/check_glm_secret.py scripts/deployment/project_route_external.py scripts/deployment/verify_glm_workspace.ps1 tests/unit/test_glm_secret_installer.py tests/unit/test_project_route_external.py docs/glm-external-provider.md
    $diffExit = $LASTEXITCODE
    $result = [ordered]@{utc=[DateTime]::UtcNow.ToString('o'); python=$pythonExit; terraform_validate=$validateExit; terraform_external_mock=$mockExit; terraform_default_mock=$defaultMockExit; terraform_fmt=$fmtExit; typescript=$ts; external_ui=$uiExit; scoped_diff_check=$diffExit}
    $result | ConvertTo-Json -Depth 8 | Set-Content gateway/validation/glm-workspace-test-status-20261026.json
    $result | ConvertTo-Json -Depth 8 | Write-Output
    $exits = @($pythonExit, $validateExit, $mockExit, $defaultMockExit, $fmtExit, $uiExit, $diffExit) + @($ts.Values)
    if (@($exits | Where-Object { $_ -ne 0 }).Count -gt 0) { throw 'GLM verification is not fully passed; see recorded per-check statuses.' }
} finally { Stop-Transcript }