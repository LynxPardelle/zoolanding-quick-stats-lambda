Param(
  [switch]$VerboseLogs
)

$env:DRY_RUN = "1"
if ($VerboseLogs) { $env:LOG_LEVEL = "DEBUG" }

Write-Host "Running unit tests (DRY_RUN=1)" -ForegroundColor Cyan
python -m unittest discover -s "$PSScriptRoot\..\tests" -p "test_*.py"
