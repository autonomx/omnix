[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("provision-from-container", "status", "launch")]
    [string]$Action,

    [string]$ContainerName = "omnix-postgres",

    [string]$CredentialPath = (Join-Path $env:LOCALAPPDATA "Omnix\secrets\postgresql-url.dpapi"),

    [string]$BatchPath,

    [switch]$CheckOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Set-PrivateDirectoryAcl {
    param([Parameter(Mandatory = $true)][string]$Path)

    New-Item -ItemType Directory -Path $Path -Force | Out-Null

    $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    $systemUser = New-Object System.Security.Principal.SecurityIdentifier("S-1-5-18")

    # Setting an owner requires SeRestorePrivilege on some Windows setups.
    # Avoid touching an already-correct directory so credential refresh works
    # from a normal user process as well as an elevated one.
    $existingAcl = Get-Acl -LiteralPath $Path
    $currentUserName = $currentUser.Translate([System.Security.Principal.NTAccount]).Value
    $expectedIdentities = @($currentUserName, $systemUser.Translate([System.Security.Principal.NTAccount]).Value)
    $existingRules = @($existingAcl.Access)
    $hasExpectedRules = $existingRules.Count -eq 2 -and @($existingRules | Where-Object {
        $_.AccessControlType -eq [System.Security.AccessControl.AccessControlType]::Allow -and
        $_.IsInherited -eq $false -and
        (($_.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::FullControl) -eq [System.Security.AccessControl.FileSystemRights]::FullControl) -and
        ($expectedIdentities -contains $_.IdentityReference.Translate([System.Security.Principal.NTAccount]).Value)
    }).Count -eq 2
    if (
        $existingAcl.AreAccessRulesProtected -and
        $existingAcl.Owner -eq $currentUserName -and
        $hasExpectedRules
    ) {
        return
    }

    $inheritance = [System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor `
        [System.Security.AccessControl.InheritanceFlags]::ObjectInherit
    $propagation = [System.Security.AccessControl.PropagationFlags]::None
    $allow = [System.Security.AccessControl.AccessControlType]::Allow

    $acl = New-Object System.Security.AccessControl.DirectorySecurity
    if ($existingAcl.Owner -ne $currentUserName) {
        $acl.SetOwner($currentUser)
    }
    $acl.SetAccessRuleProtection($true, $false)
    $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule(
        $currentUser,
        [System.Security.AccessControl.FileSystemRights]::FullControl,
        $inheritance,
        $propagation,
        $allow
    )))
    $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule(
        $systemUser,
        [System.Security.AccessControl.FileSystemRights]::FullControl,
        $inheritance,
        $propagation,
        $allow
    )))
    Set-Acl -LiteralPath $Path -AclObject $acl
}

function Get-ContainerDatabaseUrl {
    param([Parameter(Mandatory = $true)][string]$Name)

    $raw = & docker inspect $Name 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $raw) {
        throw "Unable to inspect PostgreSQL container '$Name'."
    }

    $container = @($raw | ConvertFrom-Json)[0]
    $values = @{}
    foreach ($entry in @($container.Config.Env)) {
        $parts = ([string]$entry).Split("=", 2)
        if ($parts.Count -eq 2) {
            $values[$parts[0]] = $parts[1]
        }
    }

    foreach ($required in @("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")) {
        if (-not $values.ContainsKey($required) -or [string]::IsNullOrWhiteSpace($values[$required])) {
            throw "Container '$Name' is missing required $required configuration."
        }
    }

    $user = [System.Uri]::EscapeDataString([string]$values["POSTGRES_USER"])
    $password = [System.Uri]::EscapeDataString([string]$values["POSTGRES_PASSWORD"])
    $database = [System.Uri]::EscapeDataString([string]$values["POSTGRES_DB"])
    return "postgresql://${user}:${password}@127.0.0.1:5432/${database}"
}

function Save-ProtectedDatabaseUrl {
    param(
        [Parameter(Mandatory = $true)][string]$DatabaseUrl,
        [Parameter(Mandatory = $true)][string]$Path
    )

    $directory = Split-Path -Parent $Path
    Set-PrivateDirectoryAcl -Path $directory
    $secureValue = ConvertTo-SecureString -String $DatabaseUrl -AsPlainText -Force
    $encryptedValue = ConvertFrom-SecureString -SecureString $secureValue
    [System.IO.File]::WriteAllText(
        $Path,
        $encryptedValue + [Environment]::NewLine,
        (New-Object System.Text.UTF8Encoding($false))
    )
}

function Read-ProtectedDatabaseUrl {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Protected PostgreSQL credential is not provisioned at '$Path'."
    }
    $encryptedValue = (Get-Content -LiteralPath $Path -Raw).Trim()
    if ([string]::IsNullOrWhiteSpace($encryptedValue)) {
        throw "Protected PostgreSQL credential is empty at '$Path'."
    }
    $secureValue = ConvertTo-SecureString -String $encryptedValue
    $credential = New-Object System.Net.NetworkCredential("", $secureValue)
    $databaseUrl = $credential.Password
    $uri = [System.Uri]$databaseUrl
    if ($uri.Scheme -notin @("postgresql", "postgres") -or -not $uri.Host -or $uri.AbsolutePath -eq "/") {
        throw "Protected PostgreSQL credential does not contain a valid PostgreSQL URL."
    }
    return $databaseUrl
}

switch ($Action) {
    "provision-from-container" {
        $databaseUrl = Get-ContainerDatabaseUrl -Name $ContainerName
        Save-ProtectedDatabaseUrl -DatabaseUrl $databaseUrl -Path $CredentialPath
        [ordered]@{
            ok = $true
            action = $Action
            credential_path = $CredentialPath
            protection = "windows_dpapi_current_user"
            source_container = $ContainerName
        } | ConvertTo-Json -Compress
        break
    }
    "status" {
        $databaseUrl = Read-ProtectedDatabaseUrl -Path $CredentialPath
        $uri = [System.Uri]$databaseUrl
        [ordered]@{
            ok = $true
            action = $Action
            credential_path = $CredentialPath
            protection = "windows_dpapi_current_user"
            host = $uri.Host
            port = $uri.Port
            database = $uri.AbsolutePath.TrimStart("/")
        } | ConvertTo-Json -Compress
        break
    }
    "launch" {
        if ([string]::IsNullOrWhiteSpace($BatchPath) -or -not (Test-Path -LiteralPath $BatchPath -PathType Leaf)) {
            throw "A valid -BatchPath is required for launch."
        }
        $databaseUrl = Read-ProtectedDatabaseUrl -Path $CredentialPath
        $env:OMNIX_DATABASE_URL = $databaseUrl
        try {
            $batchMode = if ($CheckOnly) {
                "--database-credential-injected-check"
            }
            else {
                "--database-credential-injected"
            }
            & $env:ComSpec /d /c "`"$BatchPath`" $batchMode"
            $exitCode = $LASTEXITCODE
        }
        finally {
            Remove-Item Env:OMNIX_DATABASE_URL -ErrorAction SilentlyContinue
        }
        exit $exitCode
    }
}
