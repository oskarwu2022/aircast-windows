# 打包 Windows 可执行程序 + 组装便携目录 + 压缩成 zip
# 用法： powershell -ExecutionPolicy Bypass -File build\build-exe.ps1
param(
    [string]$Python = "py",
    [switch]$NoZip
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Dist = Join-Path $RepoRoot 'dist'
$App = Join-Path $Dist 'AirCast'

if (-not (Test-Path (Join-Path $RepoRoot 'runtime\uxplay.exe'))) {
    throw "缺少 runtime\uxplay.exe，请先在 MSYS2 里跑 build/make-runtime.sh"
}

Write-Host "== 安装打包依赖 ==" -ForegroundColor Cyan
& $Python -m pip install --quiet --upgrade pyinstaller qrcode pillow

Write-Host "== PyInstaller 打包 ==" -ForegroundColor Cyan
Remove-Item $Dist -Recurse -Force -ErrorAction SilentlyContinue
& $Python -m PyInstaller --noconfirm --onedir --windowed --name AirCast `
    --icon (Join-Path $RepoRoot 'app\aircast.ico') `
    --exclude-module numpy --exclude-module PIL --exclude-module yaml --exclude-module pyreadline3 `
    --exclude-module unittest --exclude-module doctest --exclude-module pydoc --exclude-module sqlite3 `
    --distpath $Dist --workpath (Join-Path $RepoRoot '.work\pybuild') --specpath (Join-Path $RepoRoot '.work') `
    --add-data "$(Join-Path $RepoRoot 'app\aircast.ico');." `
    (Join-Path $RepoRoot 'app\aircast.py')

Write-Host "== 组装 runtime / scripts / 文档 ==" -ForegroundColor Cyan
Copy-Item (Join-Path $RepoRoot 'runtime') $App -Recurse -Force
Copy-Item (Join-Path $RepoRoot 'scripts') $App -Recurse -Force
Copy-Item (Join-Path $RepoRoot 'README.md') $App -Force
Copy-Item (Join-Path $RepoRoot 'LICENSE') $App -Force
Copy-Item (Join-Path $RepoRoot 'THIRD-PARTY.md') $App -Force
New-Item -ItemType Directory -Force -Path (Join-Path $App 'data') | Out-Null

if (-not $NoZip) {
    $zip = Join-Path $RepoRoot 'AirCast-Windows-x64.zip'
    Remove-Item $zip -Force -ErrorAction SilentlyContinue
    Write-Host "== 压缩 ==" -ForegroundColor Cyan
    Compress-Archive -Path (Join-Path $App '*') -DestinationPath $zip -CompressionLevel Optimal
    Write-Host ("输出：" + $zip + "  (" + [math]::Round((Get-Item $zip).Length / 1MB, 1) + " MB)") -ForegroundColor Green
}

Write-Host ("可执行目录：" + $App) -ForegroundColor Green
Write-Host "自检： & '$App\AirCast.exe' --selftest  （结果看 data\selftest.log）" -ForegroundColor Yellow
