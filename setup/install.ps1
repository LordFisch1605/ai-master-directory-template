# Windows bootstrap: installs Python 3 if it is missing, then runs the interactive setup.
#   powershell -ExecutionPolicy Bypass -File setup\install.ps1
$ErrorActionPreference = "Stop"

function Find-Python {
    foreach ($cmd in @("py", "python")) {
        $c = Get-Command $cmd -ErrorAction SilentlyContinue
        # the Microsoft Store stub "python" exists without Python; it fails on --version
        try { if ($c -and (& $c.Source --version 2>$null)) { return $c.Source } } catch { }
    }
    return $null
}

$python = Find-Python
if (-not $python) {
    $answer = Read-Host "Python 3 is missing. Install it with winget? [Y/n]"
    if ($answer -match "^[nN]") { Write-Host "Install Python 3, then run this again."; exit 1 }
    winget install -e --id Python.Python.3.13
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
    $python = Find-Python
    if (-not $python) { Write-Host "Python not found after install. Open a new terminal and run this again."; exit 1 }
}
& $python "$PSScriptRoot\setup.py"
