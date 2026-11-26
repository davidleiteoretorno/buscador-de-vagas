# Execute com: powershell -ExecutionPolicy Bypass -File setup-env.ps1
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    py -m venv venv
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar o ambiente virtual.' }
}
& $python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar dependências.' }
& $python -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar o Chromium.' }
Write-Host 'Configure o arquivo .env e execute: venv\Scripts\streamlit run painel.py'
