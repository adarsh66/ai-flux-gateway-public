#requires -Version 5.1
<#
Updates existing Linux App Services only. No Terraform, local Docker/npm, SQL DDL,
identity grants, registry credentials, resource creation, or network changes.
See docs/existing-app-deployment.md for permissions and operator attestations.
#>
[CmdletBinding()]
param(
    [ValidateSet("validate-apps", "build-apps", "deploy-apps")]
    [string]$Action = "validate-apps",
    [string]$ResourceGroup = "IDS-TOKEN-EXCHANGE-POC",
    [string]$Registry = "pocidstokenexacr",
    [string]$SubscriptionId = "aa28274d-fea0-46d4-b9c8-30f3ef0a0e52",
    [string]$TenantId = "beb276ac-6e9f-498e-8e31-019ee666decd",
    [string]$ExpectedAccount = "",
    [string]$Tag = "",
    [string]$GatewayUrl = "",
    [string]$ControlApiBase = "https://poc-ids-token-ex-api.azurewebsites.net/api",
    [string]$ApiApp = "poc-ids-token-ex-api",
    [string]$CustomerApp = "poc-ids-token-ex-customer",
    [string]$AdminApp = "poc-ids-token-ex-admin",
    [string]$SqlServer = "poc-ids-token-ex-sql",
    [string]$SqlDatabase = "aiflux",
    [switch]$SqlInitialized,
    [switch]$ApprovedPrivateTopology,
    [string]$PythonExecutable = "C:\Program Files\Python313\python.exe"
)
$ErrorActionPreference = "Stop"

# The approved split topology is not a public-network exception. The fixed-scope
# Python implementation proves exact Approved sites endpoints, subnet, DNS zone
# groups, VNet link/A records, public-customer-only ingress and denied SCM.
# It also supports distinct existing release tags and in-memory secret settings.
if ($ApprovedPrivateTopology) {
    if ($Action -eq "build-apps" -or
        $ResourceGroup -ne "IDS-TOKEN-EXCHANGE-POC" -or $Registry -ne "pocidstokenexacr" -or
        $SubscriptionId -ne "aa28274d-fea0-46d4-b9c8-30f3ef0a0e52" -or
        $TenantId -ne "beb276ac-6e9f-498e-8e31-019ee666decd" -or
        $ExpectedAccount -ne "xv.puneet.devadiga@singtel.com" -or
        $ApiApp -ne "poc-ids-token-ex-api" -or $CustomerApp -ne "poc-ids-token-ex-customer" -or
        $AdminApp -ne "poc-ids-token-ex-admin" -or $SqlServer -ne "poc-ids-token-ex-sql" -or
        $SqlDatabase -ne "aiflux" -or
        $GatewayUrl -ne "https://poc-ids-token-ex-apim.azure-api.net") {
        throw "ApprovedPrivateTopology only supports the reviewed existing POC targets and gateway; it is not a general network bypass."
    }
    if ($Action -eq "deploy-apps" -and !$SqlInitialized) {
        throw "Verified private SQL initialization must be attested before deployment."
    }
    $root = Split-Path $PSScriptRoot -Parent
    $helperAction = "validate"
    if ($Action -eq "deploy-apps") { $helperAction = "deploy" }
    Push-Location $root
    $previousPythonPath = $env:PYTHONPATH
    try {
        $env:PYTHONPATH = "$root\services\control-plane\src;$root;$root\.venv\Lib\site-packages"
        & $PythonExecutable -m scripts.deployment.deploy_portals $helperAction
        if ($LASTEXITCODE -ne 0) { throw "Fixed private-topology checks/deployment failed; no public restrictions were changed." }
    } finally {
        $env:PYTHONPATH = $previousPythonPath
        Pop-Location
    }
    return
}

function Invoke-Az {
    param([string[]]$Arguments, [switch]$Json)
    # Capture both streams; CLI errors can contain settings. Never echo raw output
    # or arguments. Explicitly check native exit codes (PS 5.1 does not do this).
    $format = "none"
    if ($Json) { $format = "json" }
    $contextArguments = @("--subscription", $SubscriptionId)
    # account show must inspect the ACTIVE account, not select the requested one.
    if ($Arguments[0] -eq "account") { $contextArguments = @() }
    try {
        # PS 5.1 otherwise promotes redirected native stderr into a terminating
        # NativeCommandError before we can redact it and check the exit code.
        $ErrorActionPreference = "Continue"
        $output = & az @Arguments @contextArguments --only-show-errors --output $format 2>&1
        $code = $LASTEXITCODE
    } catch { throw "Azure CLI could not be executed; raw diagnostics suppressed." }
    finally { $ErrorActionPreference = "Stop" }
    if ($code -ne 0) { throw "Azure CLI operation failed (exit $code). Raw output suppressed; check scoped permissions and prerequisites." }
    if ($Json) {
        try { return (($output -join "`n") | ConvertFrom-Json -ErrorAction Stop) }
        catch { throw "Azure CLI returned invalid JSON; output suppressed." }
    }
}

function Get-HttpsOrigin {
    param([string]$Value, [string]$Label)
    # Operator/regex-only validation: no Uri constructors or .NET method calls,
    # compatible with Windows PowerShell 5.1 ConstrainedLanguage.
    if ($Value -cnotmatch '^https://([a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?(?::[0-9]{1,5})?)(/[^\s"''<>;`$\\?#]*)?$') {
        throw "$Label must be an explicit HTTPS URL without credentials, query, fragment, or CSP metacharacters."
    }
    return "https://$($Matches[1])"
}

function Assert-AppNetwork {
    param($App, $Configuration)
    if ($App.publicNetworkAccess -eq "Disabled") {
        throw "Network blocker for $($App.name): public access is disabled. Obtain a reviewed private access route; this script never changes networking."
    }
    $allows = @($Configuration.ipSecurityRestrictions | Where-Object { $_.action -eq "Allow" })
    $denyAll = @($Configuration.ipSecurityRestrictions | Where-Object {
        $_.action -eq "Deny" -and $_.ipAddress -in @("Any", "0.0.0.0/0", "::/0")
    })
    if ($denyAll.Count -gt 0 -or ($Configuration.ipSecurityRestrictionsDefaultAction -eq "Deny" -and $allows.Count -eq 0)) {
        throw "Network deny-all blocker for $($App.name). A network owner must approve access separately; no restrictions were changed."
    }
}

function Assert-LockedImage {
    param([string]$Repository)
    $metadata = Invoke-Az -Arguments @("acr", "repository", "show", "--name", $Registry, "--image", "${Repository}:$Tag") -Json
    if ($metadata.changeableAttributes.writeEnabled -ne $false -or $metadata.changeableAttributes.deleteEnabled -ne $false -or
        $metadata.digest -cnotmatch '^sha256:[a-f0-9]{64}$') {
        throw "Image ${Repository}:$Tag must exist with a valid digest and write/delete disabled."
    }
    return "$($script:registryHost)/${Repository}@$($metadata.digest)"
}

if (!$ExpectedAccount -or !$SubscriptionId -or !$TenantId -or !$ResourceGroup -or !$Registry) {
    throw "ExpectedAccount, SubscriptionId, TenantId, ResourceGroup and Registry must be explicit nonempty values."
}
$gatewayOrigin = Get-HttpsOrigin -Value $GatewayUrl -Label "GatewayUrl"
$controlOrigin = Get-HttpsOrigin -Value $ControlApiBase -Label "ControlApiBase"
if ($Action -eq "deploy-apps" -and !$Tag) { throw "deploy-apps requires the explicit immutable Tag produced by build-apps." }
if ($Action -eq "build-apps" -and !$Tag) { $Tag = Get-Date -Format "yyyyMMddHHmmssfff" }
if ($Tag -and ($Tag -cnotmatch '^[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}$' -or $Tag -in @("latest", "stable", "main", "master", "dev", "production"))) {
    throw "Tag must be a unique release tag, not a mutable channel name."
}
if ($Action -eq "deploy-apps" -and !$SqlInitialized) {
    throw "Deployment blocked: pass SqlInitialized only after the SQL operator verifies migrations, identity DML grants and secure account initialization. This is an attestation, not a live SQL check."
}
if (@($ApiApp, $CustomerApp, $AdminApp | Select-Object -Unique).Count -ne 3) { throw "Three distinct App Service names are required." }
Get-Command az -ErrorAction Stop | Out-Null
$root = Split-Path $PSScriptRoot -Parent
$targets = @(
    @{ Name = $ApiApp; Repository = "aiflux-api"; Dockerfile = "services/control-plane/Dockerfile"; Port = "8000" },
    @{ Name = $CustomerApp; Repository = "aiflux-customer"; Dockerfile = "apps/customer-portal/Dockerfile"; Port = "8080" },
    @{ Name = $AdminApp; Repository = "aiflux-admin"; Dockerfile = "apps/admin-portal/Dockerfile"; Port = "8080" }
)
foreach ($target in $targets) {
    if (!(Test-Path (Join-Path $root $target.Dockerfile) -PathType Leaf)) { throw "Required Dockerfile is missing." }
}

# Check the current account, not an implicitly selected account or an account set.
$account = Invoke-Az -Arguments @("account", "show") -Json
if ($account.id -ne $SubscriptionId -or $account.tenantId -ne $TenantId -or
    $account.user.name -ne $ExpectedAccount -or $account.state -ne "Enabled") {
    throw "Azure account, tenant, subscription or subscription state does not match the requested context. No account switching is performed."
}
$group = Invoke-Az -Arguments @("group", "show", "--name", $ResourceGroup) -Json
if (!$group.id) { throw "Existing resource group could not be verified." }
$registryInfo = Invoke-Az -Arguments @("acr", "show", "--name", $Registry, "--resource-group", $ResourceGroup) -Json
if (!$registryInfo.id -or $registryInfo.loginServer -cnotmatch '^[a-zA-Z0-9.-]+$') { throw "Existing registry could not be verified." }
$script:registryHost = $registryInfo.loginServer
if ($registryInfo.roleAssignmentMode -eq "AbacRepositoryPermissions") { throw "Registry ABAC mode is not supported by this AcrPull-only path; request a separately reviewed repository-role implementation." }
if ($registryInfo.publicNetworkAccess -eq "Disabled" -or $registryInfo.networkRuleSet.defaultAction -eq "Deny") {
    throw "Registry network blocker: restricted ACR needs a reviewed private build/pull route. This path does not create agents or change network rules."
}
$server = Invoke-Az -Arguments @("sql", "server", "show", "--resource-group", $ResourceGroup, "--name", $SqlServer) -Json
$database = Invoke-Az -Arguments @("sql", "db", "show", "--resource-group", $ResourceGroup, "--server", $SqlServer, "--name", $SqlDatabase) -Json
if (!$server.fullyQualifiedDomainName -or !$database.id) { throw "Existing SQL server/database could not be verified." }

foreach ($target in $targets) {
    $name = $target.Name
    $app = Invoke-Az -Arguments @("webapp", "show", "--resource-group", $ResourceGroup, "--name", $name) -Json
    if (!$app.id -or $app.kind -notmatch "linux" -or $app.kind -match "functionapp") { throw "$name must be an existing Linux Web App." }
    $configuration = Invoke-Az -Arguments @("webapp", "config", "show", "--resource-group", $ResourceGroup, "--name", $name) -Json
    # Source builds are safe before runtime settings and private ingress exist.
    # Validation/deployment still fail closed on every runtime prerequisite.
    if ($Action -ne "build-apps") { Assert-AppNetwork -App $app -Configuration $configuration }
    # Keep only the non-secret image reference; never request container credentials.
    $previous = $configuration.linuxFxVersion
    if ($previous -and $previous -cnotmatch '^DOCKER\|[a-zA-Z0-9._/-]+(?::[a-zA-Z0-9_.-]+)?(?:@sha256:[a-f0-9]{64})?$') {
        throw "$name is not a supported credential-free legacy single-container Linux app; image reference not displayed."
    }
    $target.PreviousLinuxFxVersion = $previous
    $target.App = $app
    $settings = @{}
    $entries = Invoke-Az -Arguments @("webapp", "config", "appsettings", "list", "--resource-group", $ResourceGroup, "--name", $name) -Json
    foreach ($entry in $entries) { $settings[$entry.name] = $entry.value }
    $attached = @($app.identity.userAssignedIdentities.PSObject.Properties)
    $selected = @($attached | Where-Object {
        (!$settings["AZURE_CLIENT_ID"] -and $attached.Count -eq 1) -or $_.Value.clientId -eq $settings["AZURE_CLIENT_ID"]
    })
    if ($selected.Count -ne 1) { throw "$name needs one unambiguous attached user-assigned identity (or a matching AZURE_CLIENT_ID)." }
    $identity = Invoke-Az -Arguments @("identity", "show", "--ids", $selected[0].Name) -Json
    if (!$identity.clientId -or !$identity.principalId -or $identity.clientId -ne $selected[0].Value.clientId) { throw "Attached identity could not be verified for $name." }
    $target.ClientId = $identity.clientId
    $roles = @(Invoke-Az -Arguments @("role", "assignment", "list", "--assignee-object-id", $identity.principalId,
        "--scope", $registryInfo.id, "--include-inherited") -Json)
    $pull = @($roles | Where-Object {
        $_.principalId -eq $identity.principalId -and $_.roleDefinitionId -like "*/7f951dda-4ed3-4680-a7ca-43fe172d538d" -and !$_.condition
    })
    if ($pull.Count -eq 0) { throw "Missing unconditional AcrPull for $name identity at the registry or an ancestor scope. Ask the RBAC owner; no role changes are performed." }
    if ($name -eq $ApiApp -and $Action -ne "build-apps") {
        $sqlUrl = $settings["AIFLUX_DATABASE_URL"]
        if ($settings["AIFLUX_ENVIRONMENT"] -ne "production" -or
            $sqlUrl -notmatch '^mssql\+pyodbc://@?([a-zA-Z0-9.-]+)(?::1433)?/([^?]+)\?(.+)$') {
            throw "API needs production, passwordless explicit mssql+pyodbc SQL configuration; values suppressed."
        }
        $sqlHost = $Matches[1]; $sqlName = $Matches[2]; $sqlQuery = $Matches[3]
        if ($sqlHost -ne $server.fullyQualifiedDomainName -or $sqlName -ne $SqlDatabase -or
            $sqlQuery -notmatch '(^|&)driver=ODBC(\+|%20)Driver(\+|%20)18(\+|%20)for(\+|%20)SQL(\+|%20)Server(&|$)' -or
            $sqlQuery -notmatch '(^|&)Encrypt=(yes|true|mandatory|strict)(&|$)' -or
            $sqlQuery -notmatch '(^|&)TrustServerCertificate=(no|false)(&|$)' -or
            $sqlQuery -match '(?i)(password|pwd|uid|user|odbc_connect|authentication|access.?token)=') {
            throw "API SQL URL must target the existing database using ODBC 18, encryption, certificate validation and managed identity; values suppressed."
        }
        if (!$app.virtualNetworkSubnetId) { throw "API private SQL access prerequisite missing: existing VNet integration is required; no network changes are performed." }
        if ($settings["AIFLUX_HOME_TENANT_ID"] -ne $TenantId) { throw "API home tenant setting does not match TenantId." }
        $key = $settings["AIFLUX_PORTAL_LOGIN_SECRET"]
        $distinct = @($key -split '' | Where-Object { $_ -ne '' } | Sort-Object -Unique -CaseSensitive)
        # ASCII-only is a conservative >=32-byte subset; reject unresolved Key Vault
        # references rather than pretending their secret strength was verified.
        if ($settings["AIFLUX_PORTAL_LOGIN_ENABLED"] -notin @("true", "1", "yes", "on") -or
            !$key -or $key -cnotmatch '^[\x21-\x7e]{32,}$' -or $distinct.Count -lt 12 -or
            $key -match '(dev-sql-portal-secret|changeme|placeholder|@Microsoft.KeyVault)') {
            throw "API SQL portal login must be enabled with an independently generated strong signing setting (>=32 ASCII bytes, >=12 distinct characters); values suppressed."
        }
        $key = $null; $sqlUrl = $null
    }
    $settings = $null; $entries = $null
}
Write-Output "Existing-resource checks for $Action passed. SQL connectivity, migrations, grants and account readiness were NOT live-checked."
if ($Action -eq "validate-apps") { return }

if ($Action -eq "build-apps") {
    # Precheck every tag before any build. An existing tag is never overwritten.
    $repositories = @(Invoke-Az -Arguments @("acr", "repository", "list", "--name", $Registry) -Json)
    foreach ($target in $targets) {
        if ($target.Repository -in $repositories) {
            $tags = @(Invoke-Az -Arguments @("acr", "repository", "show-tags", "--name", $Registry, "--repository", $target.Repository) -Json)
            if ($Tag -in $tags) { throw "Release tag already exists for $($target.Repository); choose a new tag for all three images." }
        }
    }
    Write-Output "Building release Tag=$Tag (retain this explicit tag for deploy-apps)."
    foreach ($target in $targets) {
        $build = @("acr", "build", "--registry", $Registry, "--file", $target.Dockerfile,
            "--image", "$($target.Repository):$Tag", "--no-logs")
        if ($target.Name -ne $ApiApp) {
            $portalApiBase = $ControlApiBase
            # Admin SQL builds always use the fixed same-origin private proxy.
            # Customer build inputs/role acceptance are deliberately unchanged.
            if ($target.Name -eq $AdminApp) { $portalApiBase = "/api" }
            $build += @("--build-arg", "VITE_PORTAL_MODE=sql", "--build-arg", "VITE_GATEWAY_URL=$GatewayUrl",
                "--build-arg", "VITE_CONTROL_API_URL=$portalApiBase")
        }
        # No --no-wait: wait synchronously, then check the remote run status as well.
        Push-Location $root
        try { $run = Invoke-Az -Arguments ($build + @(".")) -Json }
        finally { Pop-Location }
        if ($run.status -ne "Succeeded") { throw "Remote build did not succeed for $($target.Repository). Do not deploy this release." }
        Invoke-Az -Arguments @("acr", "repository", "update", "--name", $Registry, "--image", "$($target.Repository):$Tag",
            "--write-enabled", "false", "--delete-enabled", "false")
        $image = Assert-LockedImage -Repository $target.Repository
        Write-Output "Built and locked $image"
    }
    return
}

# All prerequisites and all three locked digests are checked before the first write.
foreach ($target in $targets) { $target.Image = Assert-LockedImage -Repository $target.Repository }
foreach ($target in $targets) {
    Write-Output "Rollback image: $($target.Name) linuxFxVersion=$($target.PreviousLinuxFxVersion)"
}
Write-Output "SQL initialization attested by operator; no live SQL verification is claimed."
foreach ($target in $targets) {
    $name = $target.Name
    # JSON contains only a public client ID and a boolean; never credentials.
    # @file avoids Windows az.cmd stripping JSON quotes. This temporary file has
    # no secrets, is outside the source tree, and is removed even on CLI failure.
    $configurationFile = New-TemporaryFile
    try {
        @{ acrUseManagedIdentityCreds = $true; acrUserManagedIdentityID = $target.ClientId } |
            ConvertTo-Json -Compress | Set-Content -LiteralPath $configurationFile.FullName -Encoding Ascii
        Invoke-Az -Arguments @("webapp", "config", "set", "--resource-group", $ResourceGroup, "--name", $name, "--generic-configurations", "@$($configurationFile.FullName)")
    } finally { Remove-Item -LiteralPath $configurationFile.FullName -ErrorAction Stop }
    Invoke-Az -Arguments @("webapp", "config", "container", "set", "--resource-group", $ResourceGroup, "--name", $name,
        "--container-image-name", $target.Image, "--container-registry-url", "https://$script:registryHost")
    $newSettings = @("WEBSITES_PORT=$($target.Port)", "AZURE_CLIENT_ID=$($target.ClientId)")
    if ($name -ne $ApiApp) { $newSettings += @("GATEWAY_ORIGIN=$gatewayOrigin", "CONTROL_ORIGIN=$controlOrigin") }
    Invoke-Az -Arguments (@("webapp", "config", "appsettings", "set", "--resource-group", $ResourceGroup, "--name", $name, "--settings") + $newSettings)
    $current = Invoke-Az -Arguments @("webapp", "config", "show", "--resource-group", $ResourceGroup, "--name", $name) -Json
    if ($current.linuxFxVersion -ne "DOCKER|$($target.Image)" -or $current.acrUseManagedIdentityCreds -ne $true -or
        $current.acrUserManagedIdentityID -ne $target.ClientId) { throw "Post-update image/managed-identity verification failed for $name; use captured rollback references." }
    Write-Output "Updated $name to $($target.Image). Application readiness still requires private-route smoke tests."
}