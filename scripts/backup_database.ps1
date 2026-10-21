$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
& "$raiz\venv\Scripts\python.exe" manage.py backup_database
if ($LASTEXITCODE -ne 0) {
    throw "El backup de TecnoCorte terminó con código $LASTEXITCODE"
}
