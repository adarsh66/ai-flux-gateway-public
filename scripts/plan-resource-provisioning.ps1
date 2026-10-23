[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$VarFile,
    [string]$PlanFile = '.deployment/resource-provisioning.tfplan'
)

# Deliberately PLAN ONLY. Never use a full prerequisite apply on shared app state.
# Terraform is the only resource writer; no role writes, CLI mutations, or secrets.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$inputPath = (Resolve-Path $VarFile).Path
$config = Get-Content $inputPath -Raw | ConvertFrom-Json
$subscription = 'aa28274d-fea0-46d4-b9c8-30f3ef0a0e52'
$resourceGroup = 'IDS-TOKEN-EXCHANGE-POC'
if ($config.subscription_id -ne $subscription -or $config.resource_group_name -ne $resourceGroup) {
    throw 'Provisioning inputs must target the approved subscription and resource group.'
}
if (@(Get-Process -Name terraform -ErrorAction SilentlyContinue).Count -gt 0) {
    throw 'Terraform is already running. Wait for completion before planning.'
}
$env:TF_CLI_CONFIG_FILE = Join-Path $root '.deployment/terraform.rc'
if (!(Test-Path $env:TF_CLI_CONFIG_FILE)) { throw 'Trusted Terraform provider configuration is missing.' }
$planPath = Join-Path $root $PlanFile
if (Test-Path $planPath) { throw 'Refusing to overwrite a saved plan. Choose a fresh PlanFile.' }
$targets = @(
    'azurerm_user_assigned_identity.identity',
    'azurerm_postgresql_flexible_server.main',
    'azurerm_postgresql_flexible_server_database.main',
    'azurerm_postgresql_flexible_server_active_directory_administrator.main',
    'azapi_resource.turnstile_ledger', 'azapi_resource.model_routes',
    'azurerm_eventhub_namespace.main', 'azurerm_eventhub.token_usage',
    'azurerm_private_endpoint.data', 'azurerm_private_dns_zone_virtual_network_link.data',
    'azurerm_private_endpoint.eventhub', 'azurerm_private_dns_zone_virtual_network_link.eventhub',
    'azurerm_network_security_group.app_service_integration',
    'azurerm_subnet_network_security_group_association.app_service_integration'
)
$arguments = @('plan', '-input=false', '-no-color', "-var-file=$inputPath",
    "-var=subscription_id=$subscription", "-var=resource_group_name=$resourceGroup",
    '-var=deployment_stage=prerequisites', '-var=database_engine=postgresql',
    '-var=turnstile_platform_enabled=true', '-var=retain_legacy_mssql=true',
    '-var=manual_rbac_verified=false', '-var=local_auth_enabled=false',
    '-var=private_api_enabled=true', '-var=hybrid_private_data_enabled=true',
    '-var=sql_public_network_access_enabled=false',
    '-var=key_vault_public_network_access_enabled=false',
    '-var=function_storage_public_network_access_enabled=false',
    '-var=dev_openai_inference_enabled=false', '-var=dev_unified_inference_enabled=false',
    '-var=dev_admin_settings_enabled=false', '-var=ingestion_enabled=false',
    '-var=ingestion_timer_enabled=false', '-var=control_plane_worker_enabled=false',
    '-var=mise_sidecar_enabled=false', '-var=operator_ip=167.103.66.114', "-out=$planPath")
$arguments += $targets | ForEach-Object { "-target=$_" }
Push-Location (Join-Path $root 'infra/terraform')
try {
    # Windows PowerShell 5.1 turns native stderr into ErrorRecords. Let Terraform
    # finish and check its exit code rather than terminating on its first line.
    $ErrorActionPreference = 'Continue'
    & terraform @arguments 2>&1 | ForEach-Object { "$_" }
    $ErrorActionPreference = 'Stop'
    if ($LASTEXITCODE -ne 0) { throw 'Provisioning plan failed; do not apply its partial artifact.' }
    $ErrorActionPreference = 'Continue'
    $json = & terraform show -json $planPath
    $ErrorActionPreference = 'Stop'
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect plan; do not apply.' }
    $plan = $json | ConvertFrom-Json
    # Targeted plans normally report complete=false because untargeted resources
    # are excluded. Reject deferred/errored plans, then enforce the exact boundary.
    if (!$plan.applyable -or $plan.errored -or $plan.deferred_changes) {
        throw 'Plan is not applyable or contains errors/deferred changes. Do not apply.'
    }
    $allowed = @(
        'terraform_data.approval',
        'azurerm_user_assigned_identity.identity',
        'azurerm_postgresql_flexible_server.main',
        'azurerm_postgresql_flexible_server_database.main',
        'azurerm_postgresql_flexible_server_active_directory_administrator.main',
        'azapi_resource.turnstile_ledger', 'azapi_resource.model_routes',
        'azurerm_eventhub_namespace.main', 'azurerm_eventhub.token_usage',
        'azurerm_private_dns_zone.data', 'azurerm_private_dns_zone_virtual_network_link.data',
        'azurerm_private_endpoint.data', 'azurerm_private_dns_zone.eventhub',
        'azurerm_private_dns_zone_virtual_network_link.eventhub', 'azurerm_private_endpoint.eventhub',
        'azurerm_network_security_group.app_service_integration',
        'azurerm_subnet_network_security_group_association.app_service_integration'
    )
    foreach ($resource in $plan.resource_changes) {
        $actions = @($resource.change.actions)
        if ($resource.mode -eq 'data' -or ($actions.Count -eq 1 -and $actions[0] -eq 'no-op')) { continue }
        $address = ($resource.address -split '\[')[0]
        if ($actions -contains 'delete' -or $allowed -notcontains $address) {
            throw "Unsafe change at $($resource.address): $($actions -join ','). Do not apply."
        }
        if ($resource.type -eq 'azurerm_user_assigned_identity' -and $actions -contains 'update') {
            throw 'Existing identity changes require separate review. Do not apply.'
        }
        if ($resource.type -in @('azurerm_private_endpoint', 'azurerm_private_dns_zone', 'azurerm_private_dns_zone_virtual_network_link') -and $actions -contains 'update') {
            throw 'Existing private network changes require separate review. Do not apply.'
        }
        if ($resource.type -in @('azurerm_postgresql_flexible_server', 'azurerm_eventhub_namespace') -and $resource.change.after.public_network_access_enabled -ne $false) {
            throw 'Public data service exposure is forbidden. Do not apply.'
        }
        if ($resource.type -eq 'azurerm_network_security_group') {
            $rules = @($resource.change.after.security_rule)
            $allow = @($rules | Where-Object { $_.name -eq 'PrivateSqlProxyAndHttps' })
            $deny = @($rules | Where-Object { $_.name -eq 'DenyOtherPrivateDataPorts' })
            if ($rules.Count -ne 2 -or $allow.Count -ne 1 -or $deny.Count -ne 1) {
                throw 'Unexpected private-data NSG rules. Do not apply.'
            }
            foreach ($rule in $rules) {
                if ($rule.direction -ne 'Outbound' -or
                    $rule.source_address_prefix -ne $config.network.app_service_integration_subnet -or
                    $rule.destination_address_prefix -ne $config.network.private_endpoint_subnet -or
                    $rule.source_port_range -ne '*' -or $rule.source_port_ranges -or
                    $rule.source_address_prefixes -or $rule.destination_address_prefixes -or
                    $rule.source_application_security_group_ids -or $rule.destination_application_security_group_ids) {
                    throw 'NSG change widens the reviewed private-subnet boundary. Do not apply.'
                }
            }
            if ($allow[0].access -ne 'Allow' -or $allow[0].protocol -ne 'Tcp' -or
                $allow[0].priority -ne 100 -or $allow[0].destination_port_range -or
                (Compare-Object @('1433', '443', '5432') @($allow[0].destination_port_ranges)) -or
                $deny[0].access -ne 'Deny' -or $deny[0].protocol -ne '*' -or
                $deny[0].priority -ne 110 -or $deny[0].destination_port_range -ne '*' -or
                $deny[0].destination_port_ranges) {
                throw 'NSG must retain the deny rule and allow only private SQL/HTTPS ports. Do not apply.'
            }
        }
    }
    $plan.resource_changes | Where-Object { $_.mode -ne 'data' -and $_.change.actions -ne 'no-op' } |
        Select-Object address, @{Name='actions'; Expression={ $_.change.actions -join ',' }} | Format-Table -AutoSize
    Write-Output "Resource-only plan passed boundary checks: $planPath"
    Write-Output 'No apply performed. Review all diffs, quota/cost, and the separate deploy approval gate.'
} finally {
    Pop-Location
}