# Deploy frontend to Kamatera
# Run from repo root: .\scripts\deploy_frontend.ps1
#
# SU11A-58 guards (web/scripts/check-deploy.mjs, tested by check-deploy.test.mjs):
#   - before uploading: the built JS must contain the production API host and
#     the Supabase project host (web/deploy-hosts.json). A build made on a PC
#     without web/.env.production has neither and is NOT uploaded.
#   - after uploading: the live https://super.xxl.co.il/ must serve the same
#     index-*.js as web/dist/index.html (MATCH / MISMATCH).
# Any failure stops with a red message and a non-zero exit; "Done!" only prints
# when every step succeeded.

$Server  = "dude@185.229.226.190"
$WebRoot = "/var/www/super.xxl.co.il"

function Fail([string]$msg, [int]$code = 1) {
    Write-Host $msg -ForegroundColor Red
    exit $code
}

Write-Host "Building React app..."
Push-Location web
try {
    npm run build
    $build = $LASTEXITCODE
} finally {
    Pop-Location
}
if ($build -ne 0) { Fail "npm run build failed (exit code $build). Nothing was uploaded." $build }

Write-Host "Checking the build for the production hosts..."
node web/scripts/check-deploy.mjs hosts web/dist
if ($LASTEXITCODE -ne 0) {
    Fail "STOP: this build is not a production build (see FAIL lines above). Nothing was uploaded. Deploy from a PC that has web/.env.production."
}

Write-Host "Uploading to Kamatera..."
scp -r web/dist/* "${Server}:${WebRoot}/"
if ($LASTEXITCODE -ne 0) {
    Fail "scp upload failed (exit code $LASTEXITCODE). Nothing was deployed. Common cause: SSH fell back to password auth in a non-interactive shell and the connection dropped. Re-run interactively so you can enter the SSH password." $LASTEXITCODE
}

# SU11A-49 (F-04): scp from Windows can carry odd modes (assets/ arrived as
# 707, world-writable), and the bundle in it is what every visitor runs.
# Directories 755, files 644. dude owns the web root, so no sudo is needed.
# The last command prints how many entries still have another mode (expect 0).
Write-Host "Setting web root permissions (dirs 755, files 644)..."
ssh $Server "find $WebRoot -type d -exec chmod 755 {} + && find $WebRoot -type f -exec chmod 644 {} + && find $WebRoot \( -type d ! -perm 755 \) -o \( -type f ! -perm 644 \) | wc -l"
if ($LASTEXITCODE -ne 0) {
    Fail "chmod on $WebRoot failed (exit code $LASTEXITCODE). The files ARE uploaded; fix the modes by hand: see docs/security/su11a49_runbook.md step 6." $LASTEXITCODE
}

Write-Host "Comparing the live index-*.js with this build..."
node web/scripts/check-deploy.mjs live web/dist
if ($LASTEXITCODE -ne 0) {
    Fail "MISMATCH: https://super.xxl.co.il/ does not serve this build's index-*.js. The upload may have failed part-way or a cache is serving the old page; check before announcing the deploy."
}

Write-Host "Done! Site live at https://super.xxl.co.il" -ForegroundColor Green
