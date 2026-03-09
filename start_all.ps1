<#
  Windows 启动脚本（PowerShell）
  用途：在 Windows 环境下一键启动 / 停止本项目的各个服务。

  用法示例：
    # 启动全部服务（FastAPI + Streamlit + Telegram Bot + 可选 Tunnel）
    powershell -ExecutionPolicy Bypass -File .\start_all.ps1

    # 仅启动某个服务
    powershell -ExecutionPolicy Bypass -File .\start_all.ps1 fastapi
    powershell -ExecutionPolicy Bypass -File .\start_all.ps1 streamlit
    powershell -ExecutionPolicy Bypass -File .\start_all.ps1 telegram
    powershell -ExecutionPolicy Bypass -File .\start_all.ps1 tunnel

    # 重启单个服务
    powershell -ExecutionPolicy Bypass -File .\start_all.ps1 restart telegram

  说明：
    - 逻辑尽量与 start_all.sh 保持一致，但使用 PowerShell / Windows 的进程与端口管理方式。
    - 依赖：
        * 已在当前目录创建 Python 虚拟环境 venv（或系统 PATH 中有 python）
        *（可选）已安装 cloudflared，并能在 PATH 中找到
#>

param(
    [string]$Mode = "all",          # all | fastapi | streamlit | telegram | tunnel | restart
    [string]$Service = ""           # restart 时的服务名
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# 颜色输出辅助函数
function Write-Info($msg)  { Write-Host $msg -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host $msg -ForegroundColor Green }
function Write-Warn($msg)  { Write-Host $msg -ForegroundColor Yellow }
function Write-Err($msg)   { Write-Host $msg -ForegroundColor Red }

# 进入脚本所在目录
Set-Location -Path (Split-Path -Path $MyInvocation.MyCommand.Path -Parent)

# 选择 Python 解释器（优先 venv）
if ($env:VIRTUAL_ENV) {
    $python = Join-Path $env:VIRTUAL_ENV "Scripts\python.exe"
} elseif (Test-Path ".\venv\Scripts\python.exe") {
    $python = ".\venv\Scripts\python.exe"
} else {
    $python = "python"
}

if (-not (Get-Command $python -ErrorAction SilentlyContinue)) {
    Write-Err "未找到 Python 解释器：$python"
    exit 1
}

New-Item -ItemType Directory -Path ".\logs" -Force | Out-Null

# ---------- 通用进程/端口操作 ----------
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
    } catch {}
}

function Stop-ByName([string]$pattern, [string]$name) {
    $procs = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*$pattern*" -or $_.Name -like "*$pattern*" }
    foreach ($p in $procs) {
        try {
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
            Write-Warn "已停止 $name (PID: $($p.Id))"
        } catch {}
    }
}

# ---------- 启停单个服务 ----------
function Stop-FastAPI { Stop-ByPort -Port 8000 -name "FastAPI" }
function Stop-Streamlit { Stop-ByPort -Port 8501 -name "Streamlit" }
function Stop-Telegram { Stop-ByName -pattern "start_telegram_bot.py" -name "Telegram Bot" }
function Stop-Tunnel { Stop-ByName -pattern "cloudflared" -name "Cloudflare Tunnel" }

function Start-FastAPI {
    Write-Info "启动 FastAPI (端口8000)..."
    Start-Process $python "main.py" -RedirectStandardOutput ".\logs\fastapi.log" -RedirectStandardError ".\logs\fastapi.log" -WindowStyle Hidden
    Start-Sleep -Seconds 3
    $ok = (Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue) -ne $null
    if ($ok) { Write-Ok "✅ FastAPI 已启动"; return $true }
    Write-Err "❌ FastAPI 启动失败，查看 logs\fastapi.log"; return $false
}

function Start-Streamlit {
    Write-Info "启动 Streamlit (端口8501)..."
    Start-Process $python "-m streamlit run app/admin/dashboard.py --server.port 8501 --server.address 0.0.0.0" `
        -RedirectStandardOutput ".\logs\streamlit.log" -RedirectStandardError ".\logs\streamlit.log" -WindowStyle Hidden
    Start-Sleep -Seconds 4
    $ok = (Get-NetTCPConnection -LocalPort 8501 -ErrorAction SilentlyContinue) -ne $null
    if ($ok) { Write-Ok "✅ Streamlit 已启动"; return $true }
    Write-Warn "⚠️ Streamlit 启动失败，查看 logs\streamlit.log"; return $false
}

function Start-Telegram {
    Write-Info "启动 Telegram Bot..."
    Start-Process $python "start_telegram_bot.py" -RedirectStandardOutput ".\logs\telegram_bot.log" -RedirectStandardError ".\logs\telegram_bot.log" -WindowStyle Hidden
    $ok = $true
    for ($i=0; $i -lt 10; $i++) {
        Start-Sleep -Seconds 2
        $procs = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*start_telegram_bot.py*" -or $_.Name -like "*python*" -and $_.StartInfo.Arguments -like "*start_telegram_bot.py*" }
        if (-not $procs) {
            Write-Err "❌ Telegram Bot 启动失败或已退出，查看 logs\telegram_bot.log"
            $ok = $false
            break
        }
        if (Select-String -Path ".\logs\telegram_bot.log" -Pattern "Telegram Bot运行错误|Timed out|未配置或初始化失败|连接验证失败" -Quiet -ErrorAction SilentlyContinue) {
            Write-Err "❌ Telegram Bot 启动失败（网络/配置异常），查看 logs\telegram_bot.log"
            $ok = $false
            break
        }
    }
    if ($ok) { Write-Ok "✅ Telegram Bot 已启动"; return $true }
    return $false
}

function Start-Tunnel {
    Write-Info "启动 Cloudflare Tunnel..."
    if (-not (Get-Command "cloudflared" -ErrorAction SilentlyContinue)) {
        Write-Warn "⚠️ 未找到 cloudflared，请安装后再使用 Tunnel 功能"
        return $false
    }
    Start-Process "cloudflared" "tunnel --url http://localhost:8000" -RedirectStandardOutput ".\logs\tunnel.log" -RedirectStandardError ".\logs\tunnel.log" -WindowStyle Hidden
    Start-Sleep -Seconds 6
    $log = Get-Content ".\logs\tunnel.log" -ErrorAction SilentlyContinue
    $url = ($log -match "https://[a-z0-9-]+\.trycloudflare\.com") | Select-Object -Last 1
    if ($url) {
        $url = $url.Trim()
        Write-Ok "✅ Cloudflare Tunnel 已启动：$url"
        Write-Info "Webhook: $url/api/teams/messages"
        return $true
    }
    Write-Warn "⚠️ Tunnel 启动可能失败，请查看 logs\tunnel.log"; return $false
}

# ---------- 参数分发 ----------
switch ($Mode) {
    "restart" {
        if (-not $Service) {
            Write-Err "用法: start_all.ps1 restart <fastapi|streamlit|telegram|tunnel>"
            exit 1
        }
        switch ($Service.ToLower()) {
            "fastapi"  { Stop-FastAPI;   Start-FastAPI  | Out-Null }
            "api"      { Stop-FastAPI;   Start-FastAPI  | Out-Null }
            "streamlit"{ Stop-Streamlit; Start-Streamlit| Out-Null }
            "st"       { Stop-Streamlit; Start-Streamlit| Out-Null }
            "telegram" { Stop-Telegram;  Start-Telegram | Out-Null }
            "tg"       { Stop-Telegram;  Start-Telegram | Out-Null }
            "tunnel"   { Stop-Tunnel;    Start-Tunnel   | Out-Null }
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

Write-Ok "`n✅ 所有服务已启动（Windows PowerShell 版本）"
Write-Host "  FastAPI:   http://localhost:8000"
Write-Host "  Streamlit: http://localhost:8501"
Write-Host "  日志目录:  .\logs"

