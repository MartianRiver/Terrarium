# Sets Catch them! up on a Windows machine (docs/kids.md): uv and Node if they're missing, the sim with CPU torch,
# the built viewer, a folder for the games kept, and a Catch them! shortcut on the desktop. Run it from the repo:
#   powershell -ExecutionPolicy Bypass -File kids\setup.ps1
# Then copy the runner brain to %USERPROFILE%\terrarium-kids\brain.pt.

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host 'Installing uv...'
    powershell -ExecutionPolicy ByPass -c 'irm https://astral.sh/uv/install.ps1 | iex'
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host 'Installing Node...'
    winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
    $env:Path = "$env:ProgramFiles\nodejs;$env:Path"
}

Push-Location (Join-Path $repo 'sim')
uv sync --extra cpu
Pop-Location

Push-Location (Join-Path $repo 'viewer')
npm ci
npm run build
Pop-Location

$keep = Join-Path $env:USERPROFILE 'terrarium-kids'
New-Item -ItemType Directory -Force $keep | Out-Null

$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Catch them!.lnk'))
$link.TargetPath = Join-Path $repo 'kids\play.cmd'
$link.WorkingDirectory = Join-Path $repo 'kids'
$link.WindowStyle = 7
$link.Save()

if (Test-Path (Join-Path $keep 'brain.pt')) {
    Write-Host 'Ready: double-click Catch them! on the desktop.'
} else {
    Write-Host "Nearly: copy the runner brain to $keep\brain.pt, then double-click Catch them! on the desktop."
}
