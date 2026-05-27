# szpeter2026 开发环境一键启动（带磁盘容错）
# 用法: .\scripts\start-dev.ps1
# 自动检测 D/E 盘，不存在则回退到 C 盘

$ErrorActionPreference = "Continue"

Write-Host ""
Write-Host "╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  szpeter2026 智能启动 v2               ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ============================================
# 阶段 0：磁盘扫描 & 路径解析
# ============================================
Write-Host "[扫描] 检测可用磁盘..." -ForegroundColor Yellow

$driveD = Test-Path "D:\"
$driveE = Test-Path "E:\"

Write-Host "       D: $($driveD ? '已连接' : '未连接')" -ForegroundColor $(if($driveD){'Green'}else{'DarkGray'})
Write-Host "       E: $($driveE ? '已连接' : '未连接')" -ForegroundColor $(if($driveE){'Green'}else{'DarkGray'})
Write-Host ""

# --- Docker Desktop 路径（优先 D 盘，回退 C 盘） ---
$dockerPaths = @(
    "D:\ProgramFiles\Docker\Docker\Docker Desktop.exe",
    "C:\Program Files\Docker\Docker\Docker Desktop.exe"
)
$dockerExe = $null
foreach ($p in $dockerPaths) {
    if (Test-Path $p) { $dockerExe = $p; break }
}

# --- 项目根路径（优先 E 盘，回退 C 盘） ---
# 如果从项目内运行脚本，优先使用当前脚本所在项目
$scriptDir = Split-Path -Parent $PSScriptRoot
$projectPaths = @(
    $scriptDir,                     # 脚本所在的项目目录
    "E:\szpeter2026",              # 外挂 E 盘
    "C:\szpeter2026"               # 系统 C 盘兜底
) | Select-Object -Unique

$projectRoot = $null
foreach ($p in $projectPaths) {
    if ($p -and (Test-Path $p) -and (Test-Path "$p\requirements.txt")) {
        $projectRoot = $p
        break
    }
}

if (-not $projectRoot) {
    Write-Host "[错误] 未找到项目目录！请确认项目存在于以下路径之一：" -ForegroundColor Red
    foreach ($p in $projectPaths) { Write-Host "       $p" -ForegroundColor DarkGray }
    exit 1
}

Set-Location $projectRoot
Write-Host "[模式]" -ForegroundColor Yellow
Write-Host "       项目:  $projectRoot" -ForegroundColor Green
Write-Host "       Docker: $($dockerExe ? $dockerExe : '未找到，跳过容器')" -ForegroundColor $(if($dockerExe){'Green'}else{'DarkGray'})
Write-Host ""

# ============================================
# 阶段 1：环境变量（pip 缓存等）
# ============================================
Write-Host "[1/4] 环境变量..." -ForegroundColor Yellow
if ($driveD) {
    $env:PIP_CACHE_DIR = "D:\pip-cache"
    Write-Host "       pip 缓存 → D:\pip-cache" -ForegroundColor Green
} else {
    Write-Host "       pip 缓存 → 默认（C 盘）" -ForegroundColor DarkGray
}

# ============================================
# 阶段 2：Docker
# ============================================
Write-Host "[2/4] Docker..." -ForegroundColor Yellow

$dockerAvailable = $false
$useDocker = $dockerExe -ne $null

if ($useDocker) {
    # 检查 Docker 是否已在运行
    try {
        $null = docker info 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "       已运行" -ForegroundColor Green
            $dockerAvailable = $true
        }
    } catch {}

    # 没跑就启动它
    if (-not $dockerAvailable) {
        Write-Host "       启动 Docker Desktop..." -ForegroundColor Yellow
        Start-Process $dockerExe -WindowStyle Hidden

        Write-Host "       等待就绪（最多 60s）..." -ForegroundColor Yellow
        $timeout = 60
        while ($timeout -gt 0) {
            try {
                $null = docker info 2>$null
                if ($LASTEXITCODE -eq 0) { break }
            } catch {}
            Start-Sleep -Seconds 2
            $timeout -= 2
        }
        if ($timeout -le 0) {
            Write-Host "       超时，跳过容器" -ForegroundColor Red
        } else {
            Write-Host "       就绪" -ForegroundColor Green
            $dockerAvailable = $true
        }
    }

    # 启动向量数据库容器
    if ($dockerAvailable) {
        Write-Host "       启动 Chroma + pgvector..." -ForegroundColor Yellow
        docker compose up -d 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "       容器已启动" -ForegroundColor Green
        } else {
            Write-Host "       容器启动失败（将继续，RAG 回退 SQLite）" -ForegroundColor DarkYellow
        }
    }
} else {
    Write-Host "       Docker 未安装，跳过（RAG 使用 SQLite 兜底）" -ForegroundColor DarkGray
}

# ============================================
# 阶段 3：Python 虚拟环境
# ============================================
Write-Host "[3/4] Python 环境..." -ForegroundColor Yellow

$venvPath = Join-Path $projectRoot ".venv"
if (-not (Test-Path $venvPath)) {
    Write-Host "       创建虚拟环境..."
    python -m venv .venv 2>&1 | Out-Null
}

$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"
if (Test-Path $activateScript) {
    . $activateScript
    Write-Host "       虚拟环境已激活" -ForegroundColor Green
} else {
    Write-Host "       使用系统 Python" -ForegroundColor DarkYellow
}

pip install -r requirements.txt -q 2>&1 | Out-Null
Write-Host "       依赖就绪" -ForegroundColor Green

# ============================================
# 阶段 4：启动
# ============================================
Write-Host "[4/4] 启动面板..." -ForegroundColor Yellow
Write-Host ""
Write-Host "       http://127.0.0.1:5200" -ForegroundColor Cyan
Write-Host "       按 Ctrl+C 停止" -ForegroundColor DarkGray
Write-Host ""

python src/web_dashboard.py
