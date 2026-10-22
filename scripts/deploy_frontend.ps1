# Deploy frontend to Kamatera
# Run from repo root: .\scripts\deploy_frontend.ps1

$Server  = "dude@185.229.226.190"
$WebRoot = "/var/www/super.xxl.co.il"

Write-Host "Building React app..."
Set-Location web
npm run build
Set-Location ..

Write-Host "Uploading to Kamatera..."
scp -r web/dist/* "${Server}:${WebRoot}/"
if ($LASTEXITCODE -ne 0) {
    Write-Error "scp upload failed (exit code $LASTEXITCODE). Nothing was deployed. Common cause: SSH fell back to password auth in a non-interactive shell and the connection dropped. Re-run interactively so you can enter the SSH password."
    exit $LASTEXITCODE
}

# SU11A-49 (F-04): scp from Windows can carry odd modes (assets/ arrived as
# 707, world-writable), and the bundle in it is what every visitor runs.
# Directories 755, files 644. dude owns the web root, so no sudo is needed.
# The last command prints how many entries still have another mode (expect 0).
Write-Host "Setting web root permissions (dirs 755, files 644)..."
ssh $Server "find $WebRoot -type d -exec chmod 755 {} + && find $WebRoot -type f -exec chmod 644 {} + && find $WebRoot \( -type d ! -perm 755 \) -o \( -type f ! -perm 644 \) | wc -l"
if ($LASTEXITCODE -ne 0) {
    Write-Error "chmod on $WebRoot failed (exit code $LASTEXITCODE). The files ARE uploaded; fix the modes by hand: see docs/security/su11a49_runbook.md step 6."
    exit $LASTEXITCODE
}

Write-Host "Done! Site live at https://super.xxl.co.il"
