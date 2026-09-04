param(
    [string]$InputFile = "accounts.csv",
    [switch]$Web,
    [string]$Channel = "chrome"
)
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    throw "venv missing. python -m venv .venv && .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
}
if ($Web) {
    & $py run.py --web --channel $Channel
} else {
    & $py run.py -i $InputFile --channel $Channel
}
