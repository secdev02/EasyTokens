#Requires -Version 5.1
<#
.SYNOPSIS
    Adds DemoTokens campaign and operator-panel hostnames to the Windows hosts file.

.DESCRIPTION
    Writes entries for campaign1 through campaign10 and the operator app panel
    to C:\Windows\System32\drivers\etc\hosts, all pointing to the configured IP.
    Existing entries for the same hostnames are updated in place.
    Must be run as Administrator.

.NOTES
    Edit the CONFIG section below — change $ServerIP and $BaseDomain to match
    your demo environment.  Everything else is automatic.
#>

# ============================================================
# CONFIG — change these two values before running
# ============================================================
$ServerIP   = "192.168.1.100"          # IP of the DemoTokens server
$BaseDomain = "example.com"            # Base domain  (e.g. contoso.com)
# ============================================================

# Operator panel subdomain — matches the /app routes in DemoTokens
$AppSubdomain = "app"

# ---------------------------------------------------------------------------
# Require elevation
# ---------------------------------------------------------------------------
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Warning "This script must be run as Administrator.  Re-launching elevated..."
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" `
        -Verb RunAs
    exit
}

# ---------------------------------------------------------------------------
# Build the full list of hostnames to register
# ---------------------------------------------------------------------------
$Hostnames = @()
for ($i = 1; $i -le 10; $i++) {
    $Hostnames += "campaign$i.$BaseDomain"
}
$Hostnames += "$AppSubdomain.$BaseDomain"

# ---------------------------------------------------------------------------
# Read the current hosts file
# ---------------------------------------------------------------------------
$HostsPath = "$env:SystemRoot\System32\drivers\etc\hosts"
$Lines     = [System.IO.File]::ReadAllLines($HostsPath)

# ---------------------------------------------------------------------------
# Upsert — update existing lines or collect new ones to append
# ---------------------------------------------------------------------------
$ToAppend = [System.Collections.Generic.List[string]]::new()

foreach ($Hostname in $Hostnames) {
    # Match lines like:  <any-ip>   hostname   (with optional inline comment)
    $Pattern = "(?i)^\s*[\d\.]+\s+$([regex]::Escape($Hostname))(\s|$)"
    $Matched = $false

    for ($i = 0; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i] -match $Pattern) {
            # Replace the whole line with the updated entry
            $Lines[$i] = "$ServerIP`t$Hostname"
            Write-Host "  UPDATED  $ServerIP  $Hostname"
            $Matched = $true
            break
        }
    }

    if (-not $Matched) {
        $ToAppend.Add("$ServerIP`t$Hostname")
        Write-Host "  ADDED    $ServerIP  $Hostname"
    }
}

# ---------------------------------------------------------------------------
# Write back (existing lines updated) + append new entries
# ---------------------------------------------------------------------------
$NewContent = $Lines

if ($ToAppend.Count -gt 0) {
    # Ensure a blank separator line before the new block
    if ($NewContent[-1] -ne "") {
        $NewContent += ""
    }
    $NewContent += "# DemoTokens — $BaseDomain  (added $(Get-Date -Format 'yyyy-MM-dd'))"
    $NewContent += $ToAppend
}

[System.IO.File]::WriteAllLines($HostsPath, $NewContent)

Write-Host ""
Write-Host "Done.  $($Hostnames.Count) hostname(s) now point to $ServerIP"
Write-Host ""
Write-Host "Victim pages   : http://campaign1.$BaseDomain  ..  http://campaign10.$BaseDomain"
Write-Host "Operator panel : http://$AppSubdomain.$BaseDomain/app"
