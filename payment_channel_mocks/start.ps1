$ErrorActionPreference = "Stop"
$mockPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $mockPython)) {
    throw "Install the project first; see payment_channel_mocks/README.md."
}
# The editable install resolves imports from any working directory.
& $mockPython -X utf8 -m payment_channel_mocks
exit $LASTEXITCODE
