# Computer-Safe'i tek dosyalık Windows exe'sine derler: dist\ComputerSafe.exe
#
# Kullanım (proje klasöründe):
#   powershell -ExecutionPolicy Bypass -File .\build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Sanal ortam oluşturuluyor..."
    python -m venv .venv
}

& $python -m pip install --quiet --upgrade pip
& $python -m pip install --quiet -r requirements-dev.txt

Write-Host "Testler çalıştırılıyor..."
& $python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Testler başarısız, derleme durduruldu." }

Write-Host "Exe derleniyor..."
& $python -m PyInstaller `
    --noconfirm --clean `
    --onefile --windowed `
    --name ComputerSafe `
    --add-data "assets;assets" `
    --hidden-import keyring.backends.Windows `
    koruma.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller başarısız oldu." }

Write-Host "Hazır: $(Resolve-Path dist\ComputerSafe.exe)"
