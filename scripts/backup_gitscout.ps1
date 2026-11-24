$ErrorActionPreference = "Stop"
$Uri = "http://127.0.0.1:8765/api/v1/system/backups"
try {
    $result = Invoke-RestMethod -Method Post -Uri $Uri -TimeoutSec 120
    Write-Host "GitScout backup created:" -ForegroundColor Green
    Write-Host $result.item.filename
    Write-Host ("Size: {0:N2} MB" -f ($result.item.size_bytes / 1MB))
}
catch {
    Write-Host "Unable to create a backup. Is GitScout running?" -ForegroundColor Red
    Write-Host $_.Exception.Message
    exit 1
}
