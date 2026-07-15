# Deploy frontend to Kamatera
# Run from repo root: .\scripts\deploy_frontend.ps1

Write-Host "Building React app..."
Set-Location web
npm run build
Set-Location ..

Write-Host "Uploading to Kamatera..."
scp -r web/dist/* dude@185.229.226.190:/var/www/super.xxl.co.il/
if ($LASTEXITCODE -ne 0) {
    Write-Error "scp upload failed (exit code $LASTEXITCODE). Nothing was deployed. Common cause: SSH fell back to password auth in a non-interactive shell and the connection dropped. Re-run interactively so you can enter the SSH password."
    exit $LASTEXITCODE
}

Write-Host "Done! Site live at https://super.xxl.co.il"
