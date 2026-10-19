param([switch]$Demo, [int]$Port=8000)
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno Python' }
    & .venv\Scripts\python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias' }
}
if ($Demo) {
    $env:MOTOR_DB='private_data/demo.sqlite3'
    if (-not (Test-Path $env:MOTOR_DB)) {
        & .venv\Scripts\python.exe -m app.cli demo
        if ($LASTEXITCODE -ne 0) { throw 'Falló la carga de demo' }
    }
} elseif (-not $env:MOTOR_DB) {
    $env:MOTOR_DB='private_data/motor.sqlite3'
}
if (-not (Test-Path $env:MOTOR_DB)) {
    & .venv\Scripts\python.exe -m app.cli user administrador
    if ($LASTEXITCODE -ne 0) { throw 'Falló la creación del administrador' }
}
Write-Host "Abrir http://127.0.0.1:$Port"
& .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port $Port --workers 1
