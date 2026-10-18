# Run from a Windows PowerShell prompt. No administrator permissions required.
param([switch]$Installer,[string]$PythonExecutable='py')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location $root
try {
    if (-not (Test-Path '.venv-build/Scripts/python.exe')) {
        if ($PythonExecutable -eq 'py') { & py -3.12 -m venv .venv-build }
        else { & $PythonExecutable -m venv .venv-build }
        if ($LASTEXITCODE -ne 0) { throw 'Install 64-bit Python 3.12 with the Python launcher first.' }
    }
    $python = Join-Path $root '.venv-build/Scripts/python.exe'
    & $python -m pip install -c packaging/constraints.txt '.[package]'
    if ($LASTEXITCODE -ne 0) { throw 'Could not install build dependencies.' }
    & $python -c "from PIL import Image; Image.open('firemedia/assets/logo2k.png').save('packaging/windows/firemedia.ico',sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
    if ($LASTEXITCODE -ne 0) { throw 'Could not generate application icon.' }
    & $python -m PyInstaller --noconfirm --clean packaging/windows/FireMedia.spec
    if ($LASTEXITCODE -ne 0) { throw 'Windows packaging failed.' }
    $version = & $python -c "from firemedia import __version__; print(__version__)"
    if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?$') { throw 'Invalid app version.' }
    $version = $version.Trim()
    $bundle = Join-Path $root 'dist/FireMedia'
    & $python tools/build_source.py --output (Join-Path $bundle "FireMedia-$version-source.zip")
    if ($LASTEXITCODE -ne 0) { throw 'Could not include FireMedia source.' }
    & $python -m pip freeze | Set-Content (Join-Path $bundle 'build-environment.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Could not record build dependency versions.' }
    Compress-Archive -Path 'dist/FireMedia' -DestinationPath 'dist/FireMedia-windows-x64.zip' -Force
    if ($Installer) {
        & $python -m PyInstaller --noconfirm --clean packaging/windows/Updater.spec
        if ($LASTEXITCODE -ne 0) { throw 'Update helper packaging failed.' }
        $compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        $iscc = if ($compiler) { $compiler.Source } else { Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6/ISCC.exe' }
        if (-not (Test-Path $iscc)) { throw 'Install Inno Setup 6 to build the installer.' }
        $numericVersion = ($version -replace '(?:a|b|rc)\d+$','') + '.0'
        & $iscc "/DAppVersion=$version" "/DAppNumericVersion=$numericVersion" packaging/windows/installer.iss
        if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
    }
    Write-Host 'Ready: dist/FireMedia/FireMedia.exe and dist/FireMedia-windows-x64.zip'
    Write-Host 'Use build.ps1 -Installer to also compile the versioned setup wizard.'
} finally {
    Pop-Location
}
