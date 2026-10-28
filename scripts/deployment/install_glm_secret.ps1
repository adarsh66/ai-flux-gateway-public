param([string]$CaBundlePath = $env:REQUESTS_CA_BUNDLE)
# Interactive launcher only. Do not run in a transcript/captured agent terminal.
# No credential parameters, environment variables, temporary files or logs.
$ErrorActionPreference = 'Stop'
if (!$CaBundlePath -or !(Test-Path -LiteralPath $CaBundlePath)) {
    throw 'Provide the existing approved CA bundle using -CaBundlePath (not a credential).'
}
$root = (Resolve-Path "$PSScriptRoot/../..").Path
$env:REQUESTS_CA_BUNDLE = $CaBundlePath
$env:SSL_CERT_FILE = $CaBundlePath
$previousPythonPath = $env:PYTHONPATH
Push-Location $root
try {
    $env:PYTHONPATH = "$root;$root/services/control-plane/src;$root/.venv/Lib/site-packages"
    & 'C:/Program Files/Python313/python.exe' -m scripts.deployment.install_glm_secret
    if ($LASTEXITCODE -ne 0) { throw 'Credential installation not confirmed; no exception details logged.' }
} finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}