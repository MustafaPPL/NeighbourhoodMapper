param(
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroupName,

    [Parameter(Mandatory = $true)]
    [string]$AppName,

    [string]$PlanName = "",
    [string]$Location = "uksouth",
    [ValidateSet("F1", "B1", "B2", "P0V3")]
    [string]$Sku = "B1",
    [string]$PythonRuntime = "PYTHON:3.11",
    [string]$AuthUsername = "",
    [string]$AuthPassword = "",
    [switch]$EnableMicrosoftAuth
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($AuthUsername) -xor [string]::IsNullOrWhiteSpace($AuthPassword)) {
    throw "Provide both AuthUsername and AuthPassword, or neither."
}

if ([string]::IsNullOrWhiteSpace($PlanName)) {
    $PlanName = "$AppName-plan"
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
$stagingRoot = Join-Path $projectRoot ".azure-deploy"
$packageRoot = Join-Path $stagingRoot "package"
$zipPath = Join-Path $stagingRoot "$AppName.zip"

function Reset-Directory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Path | Out-Null
}

function Copy-ProjectItem {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath
    )

    $source = Join-Path $projectRoot $RelativePath
    $destination = Join-Path $packageRoot $RelativePath

    if (-not (Test-Path -LiteralPath $source)) {
        throw "Required deployment item not found: $RelativePath"
    }

    $destinationParent = Split-Path -Parent $destination
    if (-not [string]::IsNullOrWhiteSpace($destinationParent)) {
        New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
    }

    Copy-Item -LiteralPath $source -Destination $destination -Recurse -Force
}

function Invoke-AzCli {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    Write-Host ""
    Write-Host ("az " + ($Arguments -join " "))
    & az @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI command failed."
    }
}

function Invoke-AzJson {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $output = & az @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI command failed."
    }

    return $output | ConvertFrom-Json
}

function Test-AzCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $priorErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & az @Arguments 1>$null 2>$null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
    finally {
        $ErrorActionPreference = $priorErrorActionPreference
    }
}

function Get-Sha256Hex {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
    $hashBytes = [System.Security.Cryptography.SHA256]::HashData($bytes)
    return ([System.BitConverter]::ToString($hashBytes)).Replace("-", "").ToLowerInvariant()
}

Write-Host "Preparing deployment package for $AppName..."

Reset-Directory -Path $stagingRoot
Reset-Directory -Path $packageRoot

$itemsToCopy = @(
    "app.py",
    "project_paths.py",
    "requirements.txt",
    "data",
    "docs",
    "scripts",
    "webapp"
)

foreach ($item in $itemsToCopy) {
    Copy-ProjectItem -RelativePath $item
}

Compress-Archive -Path (Join-Path $packageRoot "*") -DestinationPath $zipPath -Force

Write-Host "Ensuring Azure resources exist..."

Invoke-AzCli -Arguments @("group", "create", "--name", $ResourceGroupName, "--location", $Location)

if (-not (Test-AzCommand -Arguments @("appservice", "plan", "show", "--name", $PlanName, "--resource-group", $ResourceGroupName))) {
    Invoke-AzCli -Arguments @("appservice", "plan", "create", "--name", $PlanName, "--resource-group", $ResourceGroupName, "--sku", $Sku, "--is-linux")
}
else {
    Write-Host "App Service plan already exists. Reusing $PlanName."
}

if (-not (Test-AzCommand -Arguments @("webapp", "show", "--name", $AppName, "--resource-group", $ResourceGroupName))) {
    Invoke-AzCli -Arguments @("webapp", "create", "--name", $AppName, "--resource-group", $ResourceGroupName, "--plan", $PlanName, "--runtime", $PythonRuntime)
}
else {
    Write-Host "Web app already exists. Reusing $AppName."
}

Invoke-AzCli -Arguments @("webapp", "update", "--name", $AppName, "--resource-group", $ResourceGroupName, "--https-only", "true")
Invoke-AzCli -Arguments @("webapp", "config", "set", "--name", $AppName, "--resource-group", $ResourceGroupName, "--startup-file", "bash scripts/deployment/startup.sh")
Invoke-AzCli -Arguments @(
    "webapp", "config", "appsettings", "set",
    "--name", $AppName,
    "--resource-group", $ResourceGroupName,
    "--settings",
    "SCM_DO_BUILD_DURING_DEPLOYMENT=true",
    "PYTHONUNBUFFERED=1"
)

if (-not [string]::IsNullOrWhiteSpace($AuthUsername)) {
    $authPasswordHash = Get-Sha256Hex -Value $AuthPassword
    Invoke-AzCli -Arguments @(
        "webapp", "config", "appsettings", "set",
        "--name", $AppName,
        "--resource-group", $ResourceGroupName,
        "--settings",
        "APP_LOGIN_USERNAME=$AuthUsername",
        "APP_LOGIN_PASSWORD_SHA256=$authPasswordHash"
    )
}

Write-Host "Deploying application package..."
Invoke-AzCli -Arguments @("webapp", "deploy", "--name", $AppName, "--resource-group", $ResourceGroupName, "--src-path", $zipPath, "--type", "zip")

if ($EnableMicrosoftAuth) {
    Write-Host "Configuring Microsoft Entra authentication for the current tenant..."

    $account = Invoke-AzJson -Arguments @("account", "show", "--output", "json")
    $tenantId = [string]$account.tenantId
    $issuer = "https://sts.windows.net/$tenantId/"
    $siteUrl = "https://$AppName.azurewebsites.net"
    $authAppDisplayName = "$AppName-auth"

    $aadApp = Invoke-AzJson -Arguments @(
        "ad", "app", "create",
        "--display-name", $authAppDisplayName,
        "--sign-in-audience", "AzureADMyOrg",
        "--web-home-page-url", $siteUrl,
        "--web-redirect-uris", "$siteUrl/.auth/login/aad/callback",
        "--output", "json"
    )

    $clientId = [string]$aadApp.appId
    $credential = Invoke-AzJson -Arguments @(
        "ad", "app", "credential", "reset",
        "--id", $clientId,
        "--append",
        "--display-name", "app-service-auth",
        "--output", "json"
    )

    $clientSecret = [string]$credential.password
    if ([string]::IsNullOrWhiteSpace($clientSecret)) {
        throw "Azure AD application secret was not returned."
    }

    Invoke-AzCli -Arguments @(
        "webapp", "auth", "update",
        "--name", $AppName,
        "--resource-group", $ResourceGroupName,
        "--enabled", "true",
        "--action", "LoginWithAzureActiveDirectory",
        "--aad-client-id", $clientId,
        "--aad-client-secret", $clientSecret,
        "--aad-token-issuer-url", $issuer,
        "--token-store", "true"
    )
}

Write-Host ""
Write-Host "Deployment complete."
Write-Host "App URL: https://$AppName.azurewebsites.net"
if (-not [string]::IsNullOrWhiteSpace($AuthUsername)) {
    Write-Host "Authentication: Shared username/password"
}
if ($EnableMicrosoftAuth) {
    Write-Host "Authentication: Microsoft Entra ID (current tenant only)"
}
