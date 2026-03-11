<#
  Windows 启动脚本（PowerShell）
  用法: powershell -ExecutionPolicy Bypass -File .\start_all.ps1 [all|fastapi|streamlit|telegram|tunnel|restart <服务名>]
#>

param(
    [string]$Mode = "all",
    [string]$Service = ""
)

$ErrorActionPreference = "Continue"

# 脚本所在目录 = 项目根目录
$ProjectRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Path $MyInvocation.MyCommand.Path -Parent }
Set-Location -Path $ProjectRoot

function Write-Info($msg)  { Write-Host $msg -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host $msg -ForegroundColor Green }
function Write-Warn($msg)   { Write-Host $msg -ForegroundColor Yellow }
function Write-Err($msg)   { Write-Host $msg -ForegroundColor Red }

# Python：优先 venv
$pythonExe = $null
if ($env:VIRTUAL_ENV) {
    $pythonExe = Join-Path $env:VIRTUAL_ENV "Scripts\python.exe"
}
if (-not $pythonExe -and (Test-Path ".\venv\Scripts\python.exe")) {
    $pythonExe = (Resolve-Path ".\venv\Scripts\python.exe").Path
}
if (-not $pythonExe) {
    $p = Get-Command python -ErrorAction SilentlyContinue
    if ($p) { $pythonExe = $p.Source } else { $pythonExe = "python" }
}

if (-not $pythonExe -or ($pythonExe -eq "python" -and -not (Get-Command python -ErrorAction SilentlyContinue))) {
    Write-Err "未找到 Python，请先创建 venv 或安装 Python"
    exit 1
}

New-Item -ItemType Directory -Path ".\logs" -Force | Out-Null

# 检测端口是否在监听（兼容无 Get-NetTCPConnection 的环境）
function Test-PortListening([int]$Port) {
    try {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        return ($null -ne $conn -and @($conn).Count -gt 0)
    } catch {
        try {
            $line = netstat -an 2>$null | Select-String ":\s*$Port\s+.*LISTENING"
            return ($null -ne $line)
        } catch {}
    }
    return $false
}

# 按端口结束进程
function Stop-ByPort([int]$Port, [string]$name) {
    try {
        $pids = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($pid in $pids) {
            try {
                Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
                Write-Warn "已停止 $name (PID: $pid)"
            } catch {}
        }
    } catch {
        $line = netstat -ano 2>$null | Select-String ":\s*$Port\s+.*LISTENING"
        if ($line) {
            $parts = $line -split '\s+'
            $pid = $parts[-1]
            if ($pid -match '^\d+$') {
                Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
                Write-Warn "已停止 $name (PID: $pid)"
            }
        }
    }
}

# 按命令行匹配结束进程（用于 telegram / cloudflared）
function Stop-ByCommandLine([string]$substr, [string]$name) {
    try {
        $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -and $_.CommandLine -like "*$substr*" }
        foreach ($p in $procs) {
            try {
                Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
                Write-Warn "已停止 $name (PID: $($p.ProcessId))"
            } catch {}
        }
    } catch {}
}

function Stop-FastAPI { Stop-ByPort -Port 8000 -name "FastAPI" }
function Stop-Streamlit { Stop-ByPort -Port 8501 -name "Streamlit" }
function Stop-Telegram { Stop-ByCommandLine -substr "start_telegram_bot.py" -name "Telegram Bot" }
function Stop-Tunnel { Stop-ByCommandLine -substr "cloudflared" -name "Tunnel" }

function Start-FastAPI {
    Write-Info "启动 FastAPI (端口8000)..."
    Start-Process -FilePath $pythonExe -ArgumentList "main.py" -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput ".\logs\fastapi.log" -RedirectStandardError ".\logs\fastapi.log" -WindowStyle Hidden
    Start-Sleep -Seconds 3
    if (Test-PortListening -Port 8000) { Write-Ok "✅ FastAPI 已启动"; return $true }
    Write-Err "❌ FastAPI 启动失败，查看 logs\fastapi.log"; return $false
}

function Start-Streamlit {
    Write-Info "启动 Streamlit (端口8501)..."
    Start-Process -FilePath $pythonExe -ArgumentList "-m","streamlit","run","app/admin/dashboard.py","--server.port","8501","--server.address","0.0.0.0" `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput ".\logs\streamlit.log" -RedirectStandardError ".\logs\streamlit.log" -WindowStyle Hidden
    Start-Sleep -Seconds 4
    if (Test-PortListening -Port 8501) { Write-Ok "✅ Streamlit 已启动"; return $true }
    Write-Warn "⚠️ Streamlit 启动失败，查看 logs\streamlit.log"; return $false
}

function Start-Telegram {
    Write-Info "启动 Telegram Bot..."
    Start-Process -FilePath $pythonExe -ArgumentList "start_telegram_bot.py" -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput ".\logs\telegram_bot.log" -RedirectStandardError ".\logs\telegram_bot.log" -WindowStyle Hidden
    $ok = $true
    for ($i = 0; $i -lt 10; $i++) {
        Start-Sleep -Seconds 2
        $found = $false
        try {
            $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
                Where-Object { $_.CommandLine -like "*start_telegram_bot.py*" }
            $found = ($procs -and @($procs).Count -gt 0)
        } catch {}
        if (-not $found) {
            Write-Err "❌ Telegram Bot 启动失败或已退出，查看 logs\telegram_bot.log"
            $ok = $false
            break
        }
        if (Test-Path ".\logs\telegram_bot.log") {
            $content = Get-Content ".\logs\telegram_bot.log" -Raw -ErrorAction SilentlyContinue
            if ($content -match "Telegram Bot运行错误|Timed out|未配置或初始化失败|连接验证失败") {
                Write-Err "❌ Telegram Bot 启动失败（网络/配置异常），查看 logs\telegram_bot.log"
                $ok = $false
                break
            }
        }
    }
    if ($ok) { Write-Ok "✅ Telegram Bot 已启动"; return $true }
    return $false
}

function Start-Tunnel {
    Write-Info "启动 Cloudflare Tunnel..."
    $cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
    if (-not $cloudflared) {
        Write-Warn "⚠️ 未找到 cloudflared，请安装后再使用 Tunnel"
        return $false
    }
    Start-Process -FilePath "cloudflared" -ArgumentList "tunnel","--url","http://localhost:8000" -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput ".\logs\tunnel.log" -RedirectStandardError ".\logs\tunnel.log" -WindowStyle Hidden
    Start-Sleep -Seconds 6
    if (Test-Path ".\logs\tunnel.log") {
        $log = Get-Content ".\logs\tunnel.log" -Raw -ErrorAction SilentlyContinue
        if ($log -match "https://[a-z0-9\-]+\.trycloudflare\.com") {
            $url = $Matches[0]
            Write-Ok "✅ Cloudflare Tunnel 已启动：$url"
            Write-Info "Webhook: $url/api/teams/messages"
            return $true
        }
    }
    Write-Warn "⚠️ Tunnel 可能仍在启动，请查看 logs\tunnel.log"; return $false
}

# ---------- 参数分发 ----------
switch ($Mode.ToLower()) {
    "restart" {
        if (-not $Service) {
            Write-Err "用法: .\start_all.ps1 restart <fastapi|streamlit|telegram|tunnel>"
            exit 1
        }
        switch ($Service.ToLower()) {
            "fastapi"   { Stop-FastAPI;   Start-FastAPI   | Out-Null }
            "api"      { Stop-FastAPI;   Start-FastAPI   | Out-Null }
            "streamlit"{ Stop-Streamlit; Start-Streamlit | Out-Null }
            "st"       { Stop-Streamlit; Start-Streamlit | Out-Null }
            "telegram" { Stop-Telegram;  Start-Telegram  | Out-Null }
            "tg"       { Stop-Telegram;  Start-Telegram  | Out-Null }
            "tunnel"   { Stop-Tunnel;    Start-Tunnel    | Out-Null }
            default    { Write-Err "未知服务: $Service"; exit 1 }
        }
        exit 0
    }
    "fastapi"   { Start-FastAPI   | Out-Null; exit 0 }
    "streamlit" { Start-Streamlit | Out-Null; exit 0 }
    "telegram"  { Start-Telegram  | Out-Null; exit 0 }
    "tunnel"    { Start-Tunnel    | Out-Null; exit 0 }
    default { }
}

# ---------- 启动全部 ----------
Write-Host ""
Write-Host "IntelliKnow KMS - 启动所有服务" -ForegroundColor Green

Write-Info "`n[1/4] FastAPI..."
if (-not (Start-FastAPI)) { exit 1 }

Write-Info "`n[2/4] Streamlit..."
Start-Streamlit | Out-Null

Write-Info "`n[3/4] Telegram Bot..."
Start-Telegram | Out-Null

Write-Info "`n[4/4] Cloudflare Tunnel（可选）..."
$answer = Read-Host "是否启动 Tunnel？(y/n，默认 n)"
if ($answer -match '^[Yy]') {
    Start-Tunnel | Out-Null
} else {
    Write-Info "跳过 Tunnel 启动"
}

Write-Ok "`n✅ 所有服务已启动"
Write-Host "  FastAPI:   http://localhost:8000"
Write-Host "  Streamlit: http://localhost:8501"
Write-Host "  日志目录:  .\logs"
