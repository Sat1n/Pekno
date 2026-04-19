$ErrorActionPreference = "Stop"

function Import-PeknoEnv {
    param(
        [string]$EnvFile = ".env"
    )

    $env:PYTHONPATH = "."

    if (Test-Path $EnvFile) {
        Get-Content $EnvFile | ForEach-Object {
            if ($_ -match '^([^=]+)=(.*)$') {
                $key = $matches[1].Trim()
                $value = $matches[2].Trim()
                [Environment]::SetEnvironmentVariable($key, $value, "Process")
            }
        }
        Write-Host "✓ 已加载 .env 配置文件" -ForegroundColor Green
    }
}

function Enable-HubDevReload {
    if (-not $env:UVICORN_RELOAD) {
        $env:UVICORN_RELOAD = "true"
    }

    Write-Host "✓ UVICORN_RELOAD=$($env:UVICORN_RELOAD)" -ForegroundColor Green
}
