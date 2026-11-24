param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Filename
)
$ErrorActionPreference = "Stop"
$escaped = [uri]::EscapeDataString($Filename)
$Uri = "http://127.0.0.1:8765/api/v1/system/backups/$escaped/restore"
$answer = Read-Host "Type RESTORE to queue database restore for '$Filename'"
if ($answer -cne "RESTORE") {
    Write-Host "Restore cancelled." -ForegroundColor Yellow
    exit 0
}
try {
    $result = Invoke-RestMethod -Method Post -Uri $Uri -ContentType "application/json" -Body '{"confirm":true}' -TimeoutSec 120
    Write-Host "Restore queued." -ForegroundColor Green
    Write-Host "Safety backup: $($result.restore.safety_backup)"
    Write-Host "Stop GitScout, then run start_gitscout.bat. Restore is applied during startup."
}
catch {
    Write-Host "Unable to queue restore. Is GitScout running and is the backup filename correct?" -ForegroundColor Red
    Write-Host $_.Exception.Message
    exit 1
}
