param(
    [double]$WatermarkOpacity = 0.10
)

$ErrorActionPreference = "Stop"

if ($WatermarkOpacity -lt 0.02 -or $WatermarkOpacity -gt 0.30) {
    throw "WatermarkOpacity doit etre compris entre 0.02 et 0.30."
}

Add-Type -AssemblyName System.Drawing

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$SourcePath = Join-Path $ProjectRoot "assets\brand-source\logo-boulangerie-lomoto-original.png"
$OutputRoot = Join-Path $ProjectRoot "output\brand-assets"
$CleanPath = Join-Path $OutputRoot "logo-boulangerie-lomoto.png"
$WatermarkPath = Join-Path $OutputRoot "logo-boulangerie-lomoto-watermark.png"

if (-not (Test-Path -LiteralPath $SourcePath)) {
    throw "Logo source introuvable: $SourcePath"
}

New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

$source = [System.Drawing.Image]::FromFile($SourcePath)
try {
    $size = 1254
    $clean = New-Object System.Drawing.Bitmap($size, $size, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $graphics = [System.Drawing.Graphics]::FromImage($clean)
    try {
        $graphics.Clear([System.Drawing.Color]::Transparent)
        $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
        $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality

        $destination = New-Object System.Drawing.Rectangle(2, 2, 1250, 1250)
        $sourceCrop = New-Object System.Drawing.Rectangle(44, 44, 1166, 1166)
        $clip = New-Object System.Drawing.Drawing2D.GraphicsPath
        try {
            $clip.AddEllipse($destination)
            $graphics.SetClip($clip)
            $graphics.DrawImage(
                $source,
                $destination,
                $sourceCrop.X,
                $sourceCrop.Y,
                $sourceCrop.Width,
                $sourceCrop.Height,
                [System.Drawing.GraphicsUnit]::Pixel
            )
        }
        finally {
            $clip.Dispose()
        }
    }
    finally {
        $graphics.Dispose()
    }
    $clean.Save($CleanPath, [System.Drawing.Imaging.ImageFormat]::Png)

    $watermark = New-Object System.Drawing.Bitmap($size, $size, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $watermarkGraphics = [System.Drawing.Graphics]::FromImage($watermark)
    $attributes = New-Object System.Drawing.Imaging.ImageAttributes
    try {
        $watermarkGraphics.Clear([System.Drawing.Color]::Transparent)
        $watermarkGraphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
        $matrix = New-Object System.Drawing.Imaging.ColorMatrix
        $matrix.Matrix33 = [single]$WatermarkOpacity
        $attributes.SetColorMatrix($matrix)
        $watermarkGraphics.DrawImage(
            $clean,
            (New-Object System.Drawing.Rectangle(0, 0, $size, $size)),
            0,
            0,
            $size,
            $size,
            [System.Drawing.GraphicsUnit]::Pixel,
            $attributes
        )
    }
    finally {
        $attributes.Dispose()
        $watermarkGraphics.Dispose()
    }
    $watermark.Save($WatermarkPath, [System.Drawing.Imaging.ImageFormat]::Png)
    $watermark.Dispose()
    $clean.Dispose()
}
finally {
    $source.Dispose()
}

$logoTargets = @(
    (Join-Path $ProjectRoot "boulangerie_app\assets\logo-boulangerie-lomoto.png"),
    (Join-Path $ProjectRoot "android-apk\www\logo-boulangerie-lomoto.png"),
    (Join-Path $ProjectRoot "web-mobile-app\public\assets\logo-boulangerie-lomoto.png")
)
$watermarkTargets = @(
    (Join-Path $ProjectRoot "boulangerie_app\assets\logo-boulangerie-lomoto-watermark.png"),
    (Join-Path $ProjectRoot "web-mobile-app\public\assets\logo-boulangerie-lomoto-watermark.png")
)

foreach ($target in $logoTargets) {
    Copy-Item -LiteralPath $CleanPath -Destination $target -Force
}
foreach ($target in $watermarkTargets) {
    Copy-Item -LiteralPath $WatermarkPath -Destination $target -Force
}

Get-Item -LiteralPath $CleanPath, $WatermarkPath |
    Select-Object Name, Length, FullName
