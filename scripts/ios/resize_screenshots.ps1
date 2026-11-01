<#
SU11B-1: resize iPhone 12 screenshots (1170x2532) to the App Store 6.5" size (1242x2688).
Same aspect ratio (scale ~1.0615 on both axes), so no crop and no padding.
Writes PNG without alpha. Windows PowerShell 5.1 (System.Drawing), no extra install.

Usage:
  powershell -ExecutionPolicy Bypass -File C:\scrp\scripts\ios\resize_screenshots.ps1 -InputDir <raw> -OutputDir <out>
#>
param(
    [Parameter(Mandatory = $true)][string]$InputDir,
    [Parameter(Mandatory = $true)][string]$OutputDir
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

if (-not (Test-Path $InputDir)) { throw "Input folder not found: $InputDir" }
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$files = Get-ChildItem -Path $InputDir -File | Where-Object { $_.Extension -match '^\.(png|jpe?g)$' }
$done = 0
foreach ($f in $files) {
    $src = [System.Drawing.Image]::FromFile($f.FullName)
    try {
        $w = $src.Width; $h = $src.Height
        if ($w -eq 1170 -and $h -eq 2532) { $tw = 1242; $th = 2688 }
        elseif ($w -eq 2532 -and $h -eq 1170) { $tw = 2688; $th = 1242 }
        else { Write-Host ("SKIP {0} {1}x{2} (expected 1170x2532)" -f $f.Name, $w, $h); continue }

        # 24-bit RGB target: no alpha channel (App Store rejects transparency).
        $dst = New-Object System.Drawing.Bitmap($tw, $th, [System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
        try {
            $g = [System.Drawing.Graphics]::FromImage($dst)
            try {
                $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
                $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
                $g.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
                $g.Clear([System.Drawing.Color]::White)
                $attr = New-Object System.Drawing.Imaging.ImageAttributes
                $attr.SetWrapMode([System.Drawing.Drawing2D.WrapMode]::TileFlipXY)  # no edge halo
                $rect = New-Object System.Drawing.Rectangle(0, 0, $tw, $th)
                $g.DrawImage($src, $rect, 0, 0, $w, $h, [System.Drawing.GraphicsUnit]::Pixel, $attr)
            } finally { $g.Dispose() }
            $out = Join-Path $OutputDir ([System.IO.Path]::GetFileNameWithoutExtension($f.Name) + '.png')
            $dst.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
            Write-Host ("OK   {0} {1}x{2} -> {3}x{4}" -f $f.Name, $w, $h, $tw, $th)
            $done++
        } finally { $dst.Dispose() }
    } finally { $src.Dispose() }
}
Write-Host ("Done: {0} file(s)" -f $done)
