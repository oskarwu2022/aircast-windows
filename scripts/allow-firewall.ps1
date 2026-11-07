# 为 AirCast（UxPlay）放行 Windows 防火墙入站规则
# 用法（需要管理员）：右键 PowerShell「以管理员身份运行」后执行本文件
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\allow-firewall.ps1
param(
    [string]$Exe = ""
)

$ErrorActionPreference = 'Stop'

function Test-Admin {
    $p = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    Write-Host "需要管理员权限，正在请求提权..." -ForegroundColor Yellow
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"")
    if ($Exe) { $argList += @('-Exe', "`"$Exe`"") }
    Start-Process powershell -Verb RunAs -ArgumentList $argList
    exit
}

if (-not $Exe) {
    $candidates = @(
        (Join-Path $PSScriptRoot '..\runtime\uxplay.exe'),
        (Join-Path $PSScriptRoot '..\app\runtime\uxplay.exe'),
        (Join-Path $PSScriptRoot '..\..\runtime\uxplay.exe')
    )
    if ($env:AIRCAST_UXPLAY_DIR) { $candidates += (Join-Path $env:AIRCAST_UXPLAY_DIR 'uxplay.exe') }
    $cmd = Get-Command uxplay.exe -ErrorAction SilentlyContinue
    if ($cmd) { $candidates += $cmd.Source }
    $Exe = $candidates | ForEach-Object { [IO.Path]::GetFullPath($_) } | Where-Object { Test-Path $_ } | Select-Object -First 1
}

Write-Host "== AirCast 防火墙配置 ==" -ForegroundColor Cyan

# 1) 程序级放行
if ($Exe -and (Test-Path $Exe)) {
    Get-NetFirewallRule -DisplayName 'AirCast (UxPlay)' -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName 'AirCast (UxPlay)' -Direction Inbound -Action Allow `
        -Program $Exe -Profile Private,Domain -Protocol Any | Out-Null
    Write-Host "  [ok] 已放行程序：$Exe"
} else {
    Write-Host "  [!!] 未找到 uxplay.exe，跳过程序级放行（可用 -Exe 指定路径）" -ForegroundColor Yellow
}

# 2) 端口级放行（mDNS 5353 + AirPlay 固定端口）
$portRules = @(
    @{ Name = 'AirCast mDNS (UDP 5353)'; Proto = 'UDP'; Port = 5353 },
    @{ Name = 'AirCast AirPlay TCP 7000'; Proto = 'TCP'; Port = 7000 },
    @{ Name = 'AirCast AirPlay TCP 7001'; Proto = 'TCP'; Port = 7001 },
    @{ Name = 'AirCast AirPlay TCP 7100'; Proto = 'TCP'; Port = 7100 },
    @{ Name = 'AirCast AirPlay UDP 6000-6001'; Proto = 'UDP'; Port = '6000-6001' },
    @{ Name = 'AirCast AirPlay UDP 7011'; Proto = 'UDP'; Port = 7011 },
    @{ Name = 'AirCast Guide 8787'; Proto = 'TCP'; Port = 8787 }
)
foreach ($r in $portRules) {
    Get-NetFirewallRule -DisplayName $r.Name -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName $r.Name -Direction Inbound -Action Allow `
        -Protocol $r.Proto -LocalPort $r.Port -Profile Private,Domain | Out-Null
    Write-Host "  [ok] 已放行 $($r.Proto) $($r.Port)（$($r.Name)）"
}

# 3) 当前网络必须是「专用网络」，否则 Windows 会拦截发现流量
$profile = Get-NetConnectionProfile -ErrorAction SilentlyContinue |
    Where-Object { $_.IPv4Connectivity -ne 'Disconnected' } | Select-Object -First 1
if ($profile) {
    Write-Host ("  当前网络：{0}  类型：{1}" -f $profile.Name, $profile.NetworkCategory)
    if ($profile.NetworkCategory -ne 'Private') {
        Set-NetConnectionProfile -InterfaceIndex $profile.InterfaceIndex -NetworkCategory Private
        Write-Host "  [ok] 已把该网络切换为「专用」" -ForegroundColor Green
    }
}

Write-Host "`n完成。可以让 iPhone 打开控制中心 → 屏幕镜像了。" -ForegroundColor Green
if ($Host.Name -eq 'ConsoleHost') { Read-Host "按回车关闭" | Out-Null }
