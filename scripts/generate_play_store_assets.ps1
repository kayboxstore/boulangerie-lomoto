param(
    [string]$Version = "1.5.3"
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Drawing

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$OutputRoot = Join-Path $ProjectRoot "output\play-store-$Version\assets"
$LogoPath = Join-Path $ProjectRoot "android-apk\www\logo-boulangerie-lomoto.png"
$BoldFontPath = Join-Path $ProjectRoot "boulangerie_app\fonts\Poppins-Bold.ttf"
$RegularFontPath = Join-Path $ProjectRoot "boulangerie_app\fonts\Poppins-Regular.ttf"

foreach ($path in @($LogoPath, $BoldFontPath, $RegularFontPath)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Fichier requis introuvable: $path"
    }
}

New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

$fontCollection = New-Object System.Drawing.Text.PrivateFontCollection
$fontCollection.AddFontFile($BoldFontPath)
$fontCollection.AddFontFile($RegularFontPath)
$boldFamily = $fontCollection.Families |
    Where-Object { $_.Name -match "Poppins" } |
    Select-Object -First 1
$regularFamily = $fontCollection.Families |
    Where-Object { $_.Name -match "Poppins" } |
    Select-Object -Last 1
if (-not $boldFamily -or -not $regularFamily) {
    throw "Les polices Poppins n'ont pas pu etre chargees."
}

$navy = [System.Drawing.Color]::FromArgb(255, 8, 37, 73)
$red = [System.Drawing.Color]::FromArgb(255, 193, 24, 38)
$paper = [System.Drawing.Color]::FromArgb(255, 247, 249, 252)
$muted = [System.Drawing.Color]::FromArgb(255, 76, 94, 117)
$gold = [System.Drawing.Color]::FromArgb(255, 178, 127, 54)
$subtitleText = "Gestion commerciale connect$([char]0x00E9)e"

function New-Canvas {
    param(
        [int]$Width,
        [int]$Height,
        [System.Drawing.Color]$Background
    )
    $bitmap = New-Object System.Drawing.Bitmap($Width, $Height, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
    $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    $graphics.Clear($Background)
    return [pscustomobject]@{
        Bitmap = $bitmap
        Graphics = $graphics
    }
}

function Save-Png {
    param(
        [System.Drawing.Bitmap]$Bitmap,
        [string]$Path
    )
    $Bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
}

function Draw-CircularLogo {
    param(
        [System.Drawing.Graphics]$Graphics,
        [System.Drawing.Image]$Image,
        [System.Drawing.Rectangle]$Destination
    )
    $state = $Graphics.Save()
    $clip = New-Object System.Drawing.Drawing2D.GraphicsPath
    try {
        $clip.AddEllipse($Destination)
        $Graphics.SetClip($clip)
        $source = New-Object System.Drawing.Rectangle(34, 34, 1186, 1186)
        $Graphics.DrawImage(
            $Image,
            $Destination,
            $source.X,
            $source.Y,
            $source.Width,
            $source.Height,
            [System.Drawing.GraphicsUnit]::Pixel
        )
    }
    finally {
        $Graphics.Restore($state)
        $clip.Dispose()
    }
}

$logo = [System.Drawing.Image]::FromFile($LogoPath)
try {
    $iconCanvas = New-Canvas -Width 512 -Height 512 -Background $paper
    try {
        $iconGraphics = $iconCanvas.Graphics
        $iconGraphics.FillRectangle((New-Object System.Drawing.SolidBrush($red)), 0, 0, 512, 18)
        $iconGraphics.FillEllipse((New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)), 34, 34, 444, 444)
        Draw-CircularLogo `
            -Graphics $iconGraphics `
            -Image $logo `
            -Destination (New-Object System.Drawing.Rectangle(54, 54, 404, 404))
        $iconEdgePen = New-Object System.Drawing.Pen($paper, 10)
        try {
            $iconGraphics.DrawEllipse($iconEdgePen, 54, 54, 404, 404)
        }
        finally {
            $iconEdgePen.Dispose()
        }
        Save-Png -Bitmap $iconCanvas.Bitmap -Path (Join-Path $OutputRoot "icone-play-store-512.png")
    }
    finally {
        $iconCanvas.Graphics.Dispose()
        $iconCanvas.Bitmap.Dispose()
    }

    $bannerCanvas = New-Canvas -Width 1024 -Height 500 -Background $paper
    try {
        $graphics = $bannerCanvas.Graphics
        $graphics.FillRectangle((New-Object System.Drawing.SolidBrush($red)), 0, 0, 1024, 18)
        $graphics.FillRectangle((New-Object System.Drawing.SolidBrush($navy)), 0, 422, 1024, 78)
        $graphics.FillRectangle((New-Object System.Drawing.SolidBrush($gold)), 70, 355, 112, 8)

        $titleFont = New-Object System.Drawing.Font($boldFamily, 48, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
        $brandFont = New-Object System.Drawing.Font($boldFamily, 72, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
        $subtitleFont = New-Object System.Drawing.Font($regularFamily, 27, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
        $platformFont = New-Object System.Drawing.Font($boldFamily, 24, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
        try {
            $graphics.DrawString("BOULANGERIE", $titleFont, (New-Object System.Drawing.SolidBrush($navy)), 70, 78)
            $graphics.DrawString("LOMOTO", $brandFont, (New-Object System.Drawing.SolidBrush($navy)), 64, 127)
            $graphics.DrawString($subtitleText, $subtitleFont, (New-Object System.Drawing.SolidBrush($muted)), 70, 248)
            $graphics.DrawString("Windows  |  Web  |  Android", $platformFont, (New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)), 70, 442)
            Draw-CircularLogo `
                -Graphics $graphics `
                -Image $logo `
                -Destination (New-Object System.Drawing.Rectangle(642, 65, 350, 350))
            $bannerEdgePen = New-Object System.Drawing.Pen($paper, 8)
            try {
                $graphics.DrawEllipse($bannerEdgePen, 642, 65, 350, 350)
            }
            finally {
                $bannerEdgePen.Dispose()
            }
        }
        finally {
            $titleFont.Dispose()
            $brandFont.Dispose()
            $subtitleFont.Dispose()
            $platformFont.Dispose()
        }
        Save-Png -Bitmap $bannerCanvas.Bitmap -Path (Join-Path $OutputRoot "image-presentation-1024x500.png")
    }
    finally {
        $bannerCanvas.Graphics.Dispose()
        $bannerCanvas.Bitmap.Dispose()
    }
}
finally {
    $logo.Dispose()
    $fontCollection.Dispose()
}

Get-ChildItem -LiteralPath $OutputRoot -Filter "*.png" -File |
    Select-Object Name, Length, FullName
