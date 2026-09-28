# scripts/allow_firewall.ps1
# Configures Windows Defender Firewall inbound rules for Nova OS Bridge
# Idempotently allows TCP 7890, TCP 7891, and UDP 5353 on all profiles
[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Nova OS — Windows AI Bridge Firewall Configuration" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# Check for Administrator elevation
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Warning "Administrator privileges are required to configure Windows Defender Firewall."
    Write-Host "Attempting to re-launch with elevated privileges..." -ForegroundColor Yellow
    try {
        Start-Process powershell.exe -ArgumentList ("-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"") -Verb RunAs -Wait
        exit 0
    } catch {
        Write-Error "Failed to elevate. Please right-click PowerShell and choose 'Run as Administrator'."
        exit 1
    }
}

$rules = @(
    @{
        Name        = "NovaOS_Bridge_HTTP_7890"
        DisplayName = "Nova OS Bridge HTTP Server (Port 7890)"
        Protocol    = "TCP"
        LocalPort   = "7890"
        Description = "Allows inbound HTTP connections (pairing, file upload, health) to Nova OS Bridge."
    },
    @{
        Name        = "NovaOS_Bridge_WS_7891"
        DisplayName = "Nova OS Bridge WebSocket (Port 7891)"
        Protocol    = "TCP"
        LocalPort   = "7891"
        Description = "Allows inbound WebSocket connections from mobile clients for real-time commands."
    },
    @{
        Name        = "NovaOS_Bridge_mDNS_5353"
        DisplayName = "Nova OS Bridge mDNS Discovery (UDP 5353)"
        Protocol    = "UDP"
        LocalPort   = "5353"
        Description = "Allows mDNS / Zeroconf auto-discovery for Nova OS Bridge companion clients."
    }
)

foreach ($rule in $rules) {
    Write-Host "Configuring rule: $($rule.DisplayName)..." -ForegroundColor White
    $configured = $false

    # Try modern NetFirewall cmdlets first
    if (Get-Command Get-NetFirewallRule -ErrorAction SilentlyContinue) {
        try {
            $existing = Get-NetFirewallRule -Name $rule.Name -ErrorAction SilentlyContinue
            if ($existing) {
                Set-NetFirewallRule -Name $rule.Name `
                    -DisplayName $rule.DisplayName `
                    -Direction Inbound `
                    -Action Allow `
                    -Protocol $rule.Protocol `
                    -LocalPort $rule.LocalPort `
                    -Profile Any `
                    -Enabled True `
                    -Description $rule.Description | Out-Null
                Write-Host "  [UPDATED] Existing rule '$($rule.Name)' refreshed on all profiles." -ForegroundColor Green
            } else {
                New-NetFirewallRule -Name $rule.Name `
                    -DisplayName $rule.DisplayName `
                    -Direction Inbound `
                    -Action Allow `
                    -Protocol $rule.Protocol `
                    -LocalPort $rule.LocalPort `
                    -Profile Any `
                    -Enabled True `
                    -Description $rule.Description | Out-Null
                Write-Host "  [CREATED] New rule '$($rule.Name)' created on all profiles." -ForegroundColor Green
            }
            $configured = $true
        } catch {
            Write-Warning "NetFirewall cmdlet error: $_. Falling back to netsh..."
        }
    }

    # Fallback to netsh if NetSecurity was unavailable or failed
    if (-not $configured) {
        try {
            & netsh advfirewall firewall delete rule name="$($rule.DisplayName)" | Out-Null
            & netsh advfirewall firewall add rule name="$($rule.DisplayName)" dir=in action=allow protocol=$($rule.Protocol) localport=$($rule.LocalPort) profile=any | Out-Null
            Write-Host "  [OK] Rule configured via netsh: $($rule.DisplayName)" -ForegroundColor Green
        } catch {
            Write-Error "Failed to configure rule via netsh: $_"
        }
    }
}

Write-Host "----------------------------------------------------------" -ForegroundColor Cyan
Write-Host "Firewall configuration complete. Inbound traffic allowed." -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
