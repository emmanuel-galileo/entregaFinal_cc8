$ErrorActionPreference='Stop'
$appDir=Split-Path -Parent $PSScriptRoot
$environmentDir=Join-Path $PSScriptRoot '.venv'
$runtimePython=Join-Path $environmentDir 'Scripts\python.exe'
if(-not (Test-Path -LiteralPath $runtimePython)){
    $launcher=Get-Command py.exe -ErrorAction SilentlyContinue
    if($launcher){
        & $launcher.Source -3 -m venv $environmentDir
    }else{
        $pythonCommand=Get-Command python.exe -ErrorAction SilentlyContinue
        if(-not $pythonCommand){throw 'Instala Python de 64 bits (3.10 o posterior), luego abre Iniciar_CC8.cmd otra vez.'}
        & $pythonCommand.Source -m venv $environmentDir
    }
    if($LASTEXITCODE -ne 0){throw 'No se pudo crear el entorno de Python.'}
}
$probeCode=@'
import sys
try:
    from PySide6 import QtCore, QtWidgets, QtSerialPort
except Exception:
    sys.exit(1)
'@
& $runtimePython -c $probeCode
if($LASTEXITCODE -ne 0){
    Write-Host 'Preparando la interfaz CC8. La primera vez se descargan sus dependencias.'
    & $runtimePython -m pip install --index-url https://pypi.org/simple -r (Join-Path $PSScriptRoot 'requirements.txt') --disable-pip-version-check
    if($LASTEXITCODE -ne 0){throw 'No se completó la instalación de dependencias.'}
}
$guiPython=Join-Path $environmentDir 'Scripts\pythonw.exe'
Start-Process -FilePath $guiPython -ArgumentList ('"'+(Join-Path $appDir 'app.py')+'"') -WorkingDirectory $appDir
