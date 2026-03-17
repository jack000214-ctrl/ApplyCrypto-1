<#
.SYNOPSIS
    Simple 7-Zip split compression script for email transfer
.DESCRIPTION
    Compresses directory into 20MB chunks for email transfer (max 20MB)
.PARAMETER SourceDir
    Source directory to compress
.PARAMETER MaxSizeMB
    Maximum size per file in MB (default: 20)
.EXAMPLE
    .\compress_for_email.ps1 -SourceDir "C:\Project\APPLYCRYPTO-deploy\APPLYCRYPTO-20260108_124622"
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$SourceDir,
    
    [int]$MaxSizeMB = 20
)

$ErrorActionPreference = "Stop"

Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host "  7-Zip Split Compression for Email Transfer (Max ${MaxSizeMB}MB per file)" -ForegroundColor Cyan
Write-Host "===============================================================================" -ForegroundColor Cyan

# Check source directory
Write-Host "`n[1/5] Checking source directory..." -ForegroundColor Yellow
if (-not (Test-Path $SourceDir)) {
    Write-Host "ERROR: Source directory not found: $SourceDir" -ForegroundColor Red
    exit 1
}

$SourceDir = Resolve-Path $SourceDir
Write-Host "  Source: $SourceDir" -ForegroundColor Green

$totalSize = (Get-ChildItem $SourceDir -Recurse | Measure-Object -Property Length -Sum).Sum
$totalSizeMB = [math]::Round($totalSize / 1MB, 2)
Write-Host "  Total size: $totalSizeMB MB" -ForegroundColor Green

# Find 7-Zip
Write-Host "`n[2/5] Finding 7-Zip..." -ForegroundColor Yellow
$7zipPaths = @(
    "C:\Program Files\7-Zip\7z.exe",
    "C:\Program Files (x86)\7-Zip\7z.exe"
)

$7zipPath = $null
foreach ($path in $7zipPaths) {
    if (Test-Path $path) {
        $7zipPath = $path
        break
    }
}

if (-not $7zipPath) {
    $7zipPath = (Get-Command 7z -ErrorAction SilentlyContinue).Source
}

if (-not $7zipPath) {
    Write-Host "ERROR: 7-Zip not found. Please install from https://www.7-zip.org/" -ForegroundColor Red
    exit 1
}

Write-Host "  Found: $7zipPath" -ForegroundColor Green

# Prepare output
Write-Host "`n[3/5] Preparing output..." -ForegroundColor Yellow
$OutputName = Split-Path $SourceDir -Leaf
$parentDir = "c:\Project\applycrypto\deploy"
$outputPath = Join-Path $parentDir "$OutputName.7z"

Write-Host "  Output: $outputPath" -ForegroundColor Green
Write-Host "  Split size: ${MaxSizeMB}MB" -ForegroundColor Green

# Compress
Write-Host "`n[4/5] Compressing with password... (this may take a while)" -ForegroundColor Yellow
$password = "1234"

Write-Host "  Password: $password" -ForegroundColor Yellow

$startTime = Get-Date
& $7zipPath a -t7z -mx=9 "-v${MaxSizeMB}m" "-p$password" -mhe=on $outputPath "$SourceDir\*"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Compression failed (Exit code: $LASTEXITCODE)" -ForegroundColor Red
    exit 1
}

$endTime = Get-Date
$duration = ($endTime - $startTime).TotalSeconds
Write-Host "  Completed in $([math]::Round($duration, 1)) seconds" -ForegroundColor Green

# Check results
Write-Host "`n[5/5] Checking results..." -ForegroundColor Yellow

$archiveFiles = Get-ChildItem $parentDir -Filter "$OutputName.7z*" | Sort-Object Name

if ($archiveFiles.Count -eq 0) {
    Write-Host "ERROR: No archive files found" -ForegroundColor Red
    exit 1
}

Write-Host "  Created $($archiveFiles.Count) files:" -ForegroundColor Green
Write-Host ""

$totalCompressedSize = 0
foreach ($file in $archiveFiles) {
    $sizeMB = [math]::Round($file.Length / 1MB, 2)
    $totalCompressedSize += $file.Length
    
    $color = if ($sizeMB -le $MaxSizeMB) { "Green" } else { "Red" }
    Write-Host "    $($file.Name) - $sizeMB MB" -ForegroundColor $color
    
    if ($sizeMB -gt $MaxSizeMB) {
        Write-Host "      WARNING: Exceeds ${MaxSizeMB}MB email limit!" -ForegroundColor Yellow
    }
}

$totalCompressedMB = [math]::Round($totalCompressedSize / 1MB, 2)
$compressionRatio = [math]::Round(($totalCompressedMB / $totalSizeMB) * 100, 1)

Write-Host "`n===============================================================================" -ForegroundColor Green
Write-Host "  Compression Summary" -ForegroundColor Green
Write-Host "===============================================================================" -ForegroundColor Green
Write-Host "  Original size:    $totalSizeMB MB" -ForegroundColor White
Write-Host "  Compressed size:  $totalCompressedMB MB" -ForegroundColor White
Write-Host "  Compression ratio: $compressionRatio%" -ForegroundColor White
Write-Host "  Space saved:      $([math]::Round($totalSizeMB - $totalCompressedMB, 2)) MB" -ForegroundColor White
Write-Host "  Number of files:  $($archiveFiles.Count)" -ForegroundColor White

Write-Host "`n===============================================================================" -ForegroundColor Cyan
Write-Host "  Next Steps: Email Transfer" -ForegroundColor Cyan
Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host "  PASSWORD: 1234 (share separately via secure channel)" -ForegroundColor Red
Write-Host ""
Write-Host "  1. Send each file as a separate email (max ${MaxSizeMB}MB)" -ForegroundColor White
Write-Host "  2. Subject format: ApplyCrypto Deployment [1/$($archiveFiles.Count)], [2/$($archiveFiles.Count)], ..." -ForegroundColor White
Write-Host "  3. Receiver: Save all files in the same folder" -ForegroundColor White
Write-Host "  4. Receiver: Extract ONLY the first file: $($archiveFiles[0].Name)" -ForegroundColor White
Write-Host "     (7-Zip will automatically process the rest)" -ForegroundColor White
Write-Host "  5. When prompted, enter password: 1234" -ForegroundColor White

Write-Host "`n===============================================================================" -ForegroundColor Cyan
Write-Host "  Email Checklist" -ForegroundColor Cyan
Write-Host "===============================================================================" -ForegroundColor Cyan
for ($i = 0; $i -lt $archiveFiles.Count; $i++) {
    Write-Host "  [ ] Email $($i+1)/$($archiveFiles.Count): $($archiveFiles[$i].Name)" -ForegroundColor Yellow
}

Write-Host "`n===============================================================================" -ForegroundColor Green
Write-Host "  Files ready for email transfer!" -ForegroundColor Green
Write-Host "  Location: $parentDir" -ForegroundColor Green
Write-Host "===============================================================================" -ForegroundColor Green

# Clean up intermediate ZIP file
$zipFile = Join-Path $parentDir "$OutputName.zip"
if (Test-Path $zipFile) {
    Write-Host "`n===============================================================================" -ForegroundColor Yellow
    Write-Host "  Cleaning up intermediate files..." -ForegroundColor Yellow
    Write-Host "===============================================================================" -ForegroundColor Yellow
    Remove-Item $zipFile -Force
    Write-Host "  [OK] Deleted intermediate ZIP file: $OutputName.zip" -ForegroundColor Green
}

# Clean up source directory
if (Test-Path $SourceDir) {
    Remove-Item $SourceDir -Recurse -Force
    Write-Host "  [OK] Deleted source directory: $SourceDir" -ForegroundColor Green
}
