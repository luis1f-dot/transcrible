# create_shortcut.ps1 -- Cria atalho do Escriba na Area de Trabalho
# Uso: powershell -ExecutionPolicy Bypass -File create_shortcut.ps1

$projectRoot  = Split-Path -Parent $MyInvocation.MyCommand.Path
$batPath      = Join-Path $projectRoot "run.bat"
$desktop      = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Escriba.lnk"

$iconPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $iconPath)) {
    $iconPath = "C:\Windows\System32\shell32.dll,22"
}

$shell    = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath       = $batPath
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description      = "Escriba"
$shortcut.IconLocation     = "$iconPath,0"
$shortcut.WindowStyle      = 1
$shortcut.Save()

Write-Host ""
Write-Host "Atalho criado:" -ForegroundColor Green
Write-Host "  $shortcutPath" -ForegroundColor Cyan