param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $BenchmarkArguments
)

$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $workspace 'benchmark\.venv\Scripts\python.exe'

function Find-FreePython {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
        (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')
    )
    foreach ($name in @('py.exe', 'python.exe')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) {
            $candidates += $command.Source
        }
    }
    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            continue
        }
        & $candidate -c 'import sys; print(sys.version_info[:2])' *> $null
        if ($LASTEXITCODE -eq 0) {
            return $candidate
        }
    }
    throw 'No usable free Python 3 was found. Install Python 3.11+ from python.org and rerun this command.'
}

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    $basePython = Find-FreePython
    & $basePython -m venv (Join-Path $workspace 'benchmark\.venv')
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to create benchmark/.venv.'
    }
}

& $venvPython -c 'import unicorn, elftools' *> $null
if ($LASTEXITCODE -ne 0) {
    & $venvPython -m pip install --disable-pip-version-check -r (Join-Path $workspace 'benchmark\requirements.txt')
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to install the free Unicorn and pyelftools benchmark dependencies.'
    }
}

if (-not $BenchmarkArguments -or $BenchmarkArguments.Count -eq 0) {
    throw 'Usage: .\benchmark.ps1 baseline   (or: .\benchmark.ps1 matrix)'
}

$driver = Join-Path $workspace 'bench.py'
$driverArguments = $BenchmarkArguments
if ($BenchmarkArguments[0] -eq 'matrix') {
    $driver = Join-Path $workspace 'matrix.py'
    if ($BenchmarkArguments.Count -gt 1) {
        $driverArguments = @($BenchmarkArguments[1..($BenchmarkArguments.Count - 1)])
    } else {
        $driverArguments = @()
    }
}

& $venvPython $driver @driverArguments
exit $LASTEXITCODE
