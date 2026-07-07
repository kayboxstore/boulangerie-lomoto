param(
    [switch]$Release,
    [switch]$OpenAndroidStudio,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

. "$PSScriptRoot\tool_paths.ps1"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$androidProject = Join-Path $root "android-apk"
$androidSdk = $env:ANDROID_HOME
if (-not $androidSdk) {
    $androidSdk = $env:ANDROID_SDK_ROOT
}
if (-not $androidSdk) {
    $androidSdk = Join-Path $env:LOCALAPPDATA "Android\Sdk"
}
if (-not (Test-Path $androidSdk)) {
    throw "SDK Android introuvable. Ouvrez Android Studio puis installez Android SDK depuis Settings > Languages & Frameworks > Android SDK."
}

$javaCandidates = @(
    $env:JAVA_HOME,
    "C:\Program Files\Android\Android Studio\jbr",
    "C:\Program Files\Android\openjdk\jdk-21.0.8"
) | Where-Object { $_ -and (Test-Path (Join-Path $_ "bin\java.exe")) }

if (-not $javaCandidates) {
    throw "Java introuvable. Android Studio doit fournir Java dans C:\Program Files\Android\Android Studio\jbr."
}

$javaHome = $javaCandidates[0]
$env:JAVA_HOME = $javaHome
$env:ANDROID_HOME = $androidSdk
$env:ANDROID_SDK_ROOT = $androidSdk

foreach ($pathToAdd in @(
    (Join-Path $javaHome "bin"),
    (Join-Path $androidSdk "platform-tools"),
    (Join-Path $androidSdk "cmdline-tools\latest\bin")
)) {
    if ((Test-Path $pathToAdd) -and (($env:Path -split ';') -notcontains $pathToAdd)) {
        $env:Path = "$pathToAdd;$env:Path"
    }
}

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Content
    )

    $encoding = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

function Get-AppVersion {
    $versionFile = Join-Path $root "boulangerie_app\version.py"
    $content = Get-Content -Raw -LiteralPath $versionFile
    if ($content -match 'APP_VERSION\s*=\s*os\.environ\.get\("[^"]+",\s*"([^"]+)"\)') {
        return $matches[1]
    }
    return "1.0.0"
}

function Get-VersionCode {
    param([string]$Version)

    $parts = $Version.Split(".") | ForEach-Object { [int]$_ }
    while ($parts.Count -lt 3) {
        $parts += 0
    }
    return ($parts[0] * 10000) + ($parts[1] * 100) + $parts[2]
}

function Get-EnvOrDefault {
    param(
        [string]$Name,
        [string]$DefaultValue
    )
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        return $DefaultValue
    }
    return $value.Trim()
}

function Get-HostFromUrl {
    param([string]$Url)
    if ([string]::IsNullOrWhiteSpace($Url)) {
        return ""
    }
    try {
        return ([System.Uri]$Url).Host
    }
    catch {
        return ($Url -replace '^https?://', '' -split '/')[0]
    }
}

function Convert-ToSafeFileName {
    param([string]$Value)
    $safe = if ([string]::IsNullOrWhiteSpace($Value)) { "Application" } else { $Value.Trim() }
    foreach ($char in [System.IO.Path]::GetInvalidFileNameChars()) {
        $safe = $safe.Replace($char, "-")
    }
    return ($safe -replace '\s+', '')
}

function Update-CapacitorConfig {
    $configFile = Join-Path $androidProject "capacitor.config.json"
    if (-not (Test-Path $configFile)) {
        return
    }

    $config = Get-Content -Raw -LiteralPath $configFile | ConvertFrom-Json
    $appName = "Boulangerie Lomoto"
    $appId = "com.gis.boulangerielomoto"
    $publicUrl = "https://app.boulangerie-lomoto.com"
    $publicHost = Get-HostFromUrl -Url $publicUrl

    $config.appName = $appName
    $config.appId = $appId
    if (-not $config.server) {
        $config | Add-Member -NotePropertyName server -NotePropertyValue ([pscustomobject]@{})
    }
    $config.server.url = $publicUrl
    $config.server.cleartext = $false
    $config.server.androidScheme = "https"
    if ($publicHost) {
        $domains = @($publicHost)
        if ($publicHost.StartsWith("app.")) {
            $domains += $publicHost.Substring(4)
        }
        $config.server.allowNavigation = @($domains | Select-Object -Unique)
    }

    $json = $config | ConvertTo-Json -Depth 10
    Write-Utf8NoBom -Path $configFile -Content $json
}

function Update-AndroidVersion {
    param(
        [string]$Version,
        [int]$VersionCode
    )

    $gradleFile = Join-Path $androidProject "android\app\build.gradle"
    if (-not (Test-Path $gradleFile)) {
        return
    }

    $content = Get-Content -Raw -LiteralPath $gradleFile
    $content = $content -replace 'versionCode\s+\d+', "versionCode $VersionCode"
    $content = $content -replace 'versionName\s+"[^"]+"', "versionName `"$Version`""
    Write-Utf8NoBom -Path $gradleFile -Content $content
}

function Get-AndroidAppId {
    return "com.gis.boulangerielomoto"
}

function Get-AndroidAppName {
    return "Boulangerie Lomoto"
}

function Update-AndroidNativeIdentity {
    $appId = Get-AndroidAppId
    $appName = Get-AndroidAppName
    $gradleFile = Join-Path $androidProject "android\app\build.gradle"
    if (Test-Path $gradleFile) {
        $content = Get-Content -Raw -LiteralPath $gradleFile
        $content = $content -replace 'namespace\s+"[^"]+"', "namespace `"$appId`""
        $content = $content -replace 'applicationId\s+"[^"]+"', "applicationId `"$appId`""
        Write-Utf8NoBom -Path $gradleFile -Content $content
    }

    $stringsFile = Join-Path $androidProject "android\app\src\main\res\values\strings.xml"
    if (Test-Path $stringsFile) {
        [xml]$strings = Get-Content -Raw -LiteralPath $stringsFile
        foreach ($node in $strings.resources.string) {
            if ($node.name -in @("app_name", "title_activity_main")) {
                $node.InnerText = $appName
            }
            elseif ($node.name -in @("package_name", "custom_url_scheme")) {
                $node.InnerText = $appId
            }
        }
        Write-Utf8NoBom -Path $stringsFile -Content $strings.OuterXml
    }
}

function Enable-ReleaseSigningIfAvailable {
    $gradleFile = Join-Path $androidProject "android\app\build.gradle"
    $keystoreProperties = Join-Path $androidProject "android\keystore.properties"
    if (-not (Test-Path $gradleFile) -or -not (Test-Path $keystoreProperties)) {
        return
    }

    $content = Get-Content -Raw -LiteralPath $gradleFile
    if ($content -notmatch 'keystorePropertiesFile') {
        $prefix = @'
def keystoreProperties = new java.util.Properties()
def keystorePropertiesFile = rootProject.file("keystore.properties")
if (keystorePropertiesFile.exists()) {
    keystoreProperties.load(new java.io.FileInputStream(keystorePropertiesFile))
}

'@
        $content = $prefix + $content
    }

    if ($content -notmatch 'signingConfigs\s*\{') {
        $signingBlock = @'
    signingConfigs {
        release {
            keyAlias keystoreProperties["keyAlias"]
            keyPassword keystoreProperties["keyPassword"]
            storeFile rootProject.file(keystoreProperties["storeFile"])
            storePassword keystoreProperties["storePassword"]
        }
    }

'@
        $content = $content -replace 'android\s*\{\s*', "android {`r`n$signingBlock"
    }

    if ($content -notmatch 'buildTypes\s*\{\s*release\s*\{\s*signingConfig signingConfigs\.release') {
        $content = $content -replace '(buildTypes\s*\{\s*release\s*\{)', "`$1`r`n            signingConfig signingConfigs.release"
    }

    Write-Utf8NoBom -Path $gradleFile -Content $content
}

function Harden-AndroidManifest {
    $manifestFile = Join-Path $androidProject "android\app\src\main\AndroidManifest.xml"
    if (-not (Test-Path $manifestFile)) {
        return
    }

    $content = Get-Content -Raw -LiteralPath $manifestFile
    $content = $content -replace '\s*<uses-permission android:name="android\.permission\.INTERNET"\s*/>', ''
    $content = $content -replace '(<manifest[^>]*>\s*)', "`$1`r`n    <uses-permission android:name=`"android.permission.INTERNET`" />`r`n"
    $content = $content -replace 'android:allowBackup="true"', 'android:allowBackup="false"'
    if ($content -notmatch 'android:fullBackupContent=') {
        $content = $content -replace 'android:allowBackup="false"', "android:allowBackup=`"false`"`r`n        android:fullBackupContent=`"false`""
    }
    if ($content -notmatch 'android:dataExtractionRules=') {
        $content = $content -replace 'android:fullBackupContent="false"', "android:fullBackupContent=`"false`"`r`n        android:dataExtractionRules=`"@xml/data_extraction_rules`""
    }
    if ($content -notmatch 'android:usesCleartextTraffic=') {
        $content = $content -replace 'android:supportsRtl="true"', "android:supportsRtl=`"true`"`r`n        android:usesCleartextTraffic=`"false`""
    }
    $content = $content -replace 'android:theme="@style/AppTheme\.NoActionBarLaunch"', 'android:theme="@style/AppTheme.NoActionBar"'
    if ($content -notmatch 'android:windowSoftInputMode=') {
        $content = $content -replace 'android:launchMode="singleTask"', "android:launchMode=`"singleTask`"`r`n            android:windowSoftInputMode=`"adjustResize`""
    }
    Write-Utf8NoBom -Path $manifestFile -Content $content

    $rulesDir = Join-Path $androidProject "android\app\src\main\res\xml"
    New-Item -ItemType Directory -Path $rulesDir -Force | Out-Null
    $rulesFile = Join-Path $rulesDir "data_extraction_rules.xml"
    $rules = @'
<?xml version="1.0" encoding="utf-8"?>
<data-extraction-rules>
    <cloud-backup disableIfNoEncryptionCapabilities="true">
        <exclude domain="root" path="." />
        <exclude domain="file" path="." />
        <exclude domain="database" path="." />
        <exclude domain="sharedpref" path="." />
        <exclude domain="external" path="." />
    </cloud-backup>
    <device-transfer>
        <exclude domain="root" path="." />
        <exclude domain="file" path="." />
        <exclude domain="database" path="." />
        <exclude domain="sharedpref" path="." />
        <exclude domain="external" path="." />
    </device-transfer>
</data-extraction-rules>
'@
    Write-Utf8NoBom -Path $rulesFile -Content $rules
}

function Update-AndroidIcon {
    Add-Type -AssemblyName System.Drawing

    $source = Join-Path $root "boulangerie_app\assets\logo-boulangerie-lomoto.png"
    if (-not (Test-Path $source)) {
        return
    }

    Copy-Item -LiteralPath $source -Destination (Join-Path $androidProject "www\logo-boulangerie-lomoto.png") -Force

    $resRoot = Join-Path $androidProject "android\app\src\main\res"
    if (-not (Test-Path $resRoot)) {
        return
    }

    $densities = @{
        "mipmap-mdpi" = 48
        "mipmap-hdpi" = 72
        "mipmap-xhdpi" = 96
        "mipmap-xxhdpi" = 144
        "mipmap-xxxhdpi" = 192
    }

    $original = [System.Drawing.Image]::FromFile($source)
    try {
        foreach ($density in $densities.Keys) {
            $targetDir = Join-Path $resRoot $density
            New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
            foreach ($name in @("ic_launcher.png", "ic_launcher_round.png", "ic_launcher_foreground.png")) {
                $size = [int]$densities[$density]
                $bitmap = New-Object System.Drawing.Bitmap $size, $size
                $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
                $clip = New-Object System.Drawing.Drawing2D.GraphicsPath
                try {
                    $graphics.Clear([System.Drawing.Color]::Transparent)
                    $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
                    $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
                    $clip.AddEllipse(0, 0, $size, $size)
                    $graphics.SetClip($clip)
                    $overscan = [int][Math]::Ceiling($size * 0.035)
                    $graphics.DrawImage($original, -$overscan, -$overscan, $size + ($overscan * 2), $size + ($overscan * 2))
                    $bitmap.Save((Join-Path $targetDir $name), [System.Drawing.Imaging.ImageFormat]::Png)
                }
                finally {
                    $clip.Dispose()
                    $graphics.Dispose()
                    $bitmap.Dispose()
                }
            }
        }

        $adaptiveIcon = @'
<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/ic_launcher_background"/>
    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>
</adaptive-icon>
'@
        $adaptiveDir = Join-Path $resRoot "mipmap-anydpi-v26"
        New-Item -ItemType Directory -Path $adaptiveDir -Force | Out-Null
        Write-Utf8NoBom -Path (Join-Path $adaptiveDir "ic_launcher.xml") -Content $adaptiveIcon
        Write-Utf8NoBom -Path (Join-Path $adaptiveDir "ic_launcher_round.xml") -Content $adaptiveIcon

        $backgroundFile = Join-Path $resRoot "values\ic_launcher_background.xml"
        Write-Utf8NoBom -Path $backgroundFile -Content @'
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="ic_launcher_background">#FFFFFF</color>
</resources>
'@

        Get-ChildItem -Path $resRoot -Recurse -Filter "splash.png" | ForEach-Object {
            $probe = [System.Drawing.Image]::FromFile($_.FullName)
            try {
                $width = [int]$probe.Width
                $height = [int]$probe.Height
            }
            finally {
                $probe.Dispose()
            }
            $bitmap = New-Object System.Drawing.Bitmap $width, $height
            $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
            try {
                $graphics.Clear([System.Drawing.ColorTranslator]::FromHtml("#F4F6F9"))
                $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
                $targetSize = [int][Math]::Max(96, [Math]::Min($width, $height) * 0.28)
                $x = [int](($width - $targetSize) / 2)
                $y = [int](($height - $targetSize) / 2)
                $graphics.DrawImage($original, $x, $y, $targetSize, $targetSize)
                $bitmap.Save($_.FullName, [System.Drawing.Imaging.ImageFormat]::Png)
            }
            finally {
                $graphics.Dispose()
                $bitmap.Dispose()
            }
        }
    }
    finally {
        $original.Dispose()
    }
}

function Update-AndroidAppearance {
    $resRoot = Join-Path $androidProject "android\app\src\main\res"
    if (-not (Test-Path $resRoot)) {
        return
    }

    $layoutDir = Join-Path $resRoot "layout"
    New-Item -ItemType Directory -Path $layoutDir -Force | Out-Null
    Write-Utf8NoBom -Path (Join-Path $layoutDir "activity_main.xml") -Content @'
<?xml version="1.0" encoding="utf-8"?>
<androidx.coordinatorlayout.widget.CoordinatorLayout xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:app="http://schemas.android.com/apk/res-auto"
    xmlns:tools="http://schemas.android.com/tools"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    tools:context=".MainActivity">

    <com.getcapacitor.CapacitorWebView
        android:id="@+id/webview"
        android:layout_width="fill_parent"
        android:layout_height="fill_parent"
        android:importantForAutofill="yes"
        android:saveEnabled="true" />
</androidx.coordinatorlayout.widget.CoordinatorLayout>
'@

    Write-Utf8NoBom -Path (Join-Path $resRoot "values\colors.xml") -Content @'
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="colorPrimary">#B71924</color>
    <color name="colorPrimaryDark">#8F111A</color>
    <color name="colorAccent">#163A63</color>
</resources>
'@

    Write-Utf8NoBom -Path (Join-Path $resRoot "values\styles.xml") -Content @'
<?xml version="1.0" encoding="utf-8"?>
<resources>

    <style name="AppTheme" parent="Theme.AppCompat.DayNight.NoActionBar">
        <item name="colorPrimary">@color/colorPrimary</item>
        <item name="colorPrimaryDark">@color/colorPrimaryDark</item>
        <item name="colorAccent">@color/colorAccent</item>
        <item name="windowActionBar">false</item>
        <item name="windowNoTitle">true</item>
    </style>

    <style name="AppTheme.NoActionBar" parent="Theme.AppCompat.DayNight.NoActionBar">
        <item name="windowActionBar">false</item>
        <item name="windowNoTitle">true</item>
        <item name="android:background">#F4F6F9</item>
        <item name="android:statusBarColor">#B71924</item>
        <item name="android:navigationBarColor">#F4F6F9</item>
        <item name="android:windowLightStatusBar">true</item>
    </style>

    <style name="AppTheme.NoActionBarLaunch" parent="Theme.SplashScreen">
        <item name="windowSplashScreenBackground">#F4F6F9</item>
        <item name="windowSplashScreenAnimatedIcon">@mipmap/ic_launcher</item>
        <item name="postSplashScreenTheme">@style/AppTheme.NoActionBar</item>
        <item name="android:background">@drawable/splash</item>
    </style>
</resources>
'@

    $valuesV27 = Join-Path $resRoot "values-v27"
    New-Item -ItemType Directory -Path $valuesV27 -Force | Out-Null
    Write-Utf8NoBom -Path (Join-Path $valuesV27 "styles.xml") -Content @'
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="AppTheme.NoActionBar">
        <item name="android:statusBarColor">#B71924</item>
        <item name="android:navigationBarColor">#F4F6F9</item>
        <item name="android:windowLightStatusBar">true</item>
        <item name="android:windowLightNavigationBar">true</item>
    </style>
</resources>
'@

    $valuesV35 = Join-Path $resRoot "values-v35"
    New-Item -ItemType Directory -Path $valuesV35 -Force | Out-Null
    Write-Utf8NoBom -Path (Join-Path $valuesV35 "styles.xml") -Content @'
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="AppTheme.NoActionBar">
        <item name="android:windowOptOutEdgeToEdgeEnforcement">true</item>
    </style>
</resources>
'@

    $appId = Get-AndroidAppId
    $mainActivityDir = Join-Path $androidProject ("android\app\src\main\java\" + $appId.Replace(".", "\"))
    New-Item -ItemType Directory -Path $mainActivityDir -Force | Out-Null
    $mainActivity = Join-Path $mainActivityDir "MainActivity.java"
    Write-Utf8NoBom -Path $mainActivity -Content @"
package $appId;

import android.graphics.Color;
import android.os.Bundle;
import android.view.View;

import com.getcapacitor.BridgeActivity;

import androidx.core.view.WindowCompat;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        WindowCompat.setDecorFitsSystemWindows(getWindow(), true);
        super.onCreate(savedInstanceState);
        getWindow().setStatusBarColor(Color.rgb(183, 25, 36));
        getWindow().setNavigationBarColor(Color.rgb(244, 246, 249));
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR);
    }
}
"@
}

function Set-AndroidLocalProperties {
    $localProperties = Join-Path $androidProject "android\local.properties"
    $escapedSdk = $androidSdk.Replace("\", "\\")
    Set-Content -LiteralPath $localProperties -Value "sdk.dir=$escapedSdk" -Encoding ASCII
}

$appVersion = Get-AppVersion
$versionCode = Get-VersionCode -Version $appVersion

Push-Location $androidProject
try {
    Update-CapacitorConfig
    Invoke-Tool -Candidates @("npm.cmd", "npm") -Arguments @("install")

    if (-not (Test-Path (Join-Path $androidProject "android"))) {
        Invoke-Tool -Candidates @("npx.cmd", "npx") -Arguments @("cap", "add", "android")
    }

    Set-AndroidLocalProperties
    Invoke-Tool -Candidates @("npx.cmd", "npx") -Arguments @("cap", "sync", "android")
    Update-AndroidNativeIdentity
    Update-AndroidVersion -Version $appVersion -VersionCode $versionCode
    if ($Release -and -not (Test-Path (Join-Path $androidProject "android\keystore.properties"))) {
        throw "APK release impossible : cle Android absente. Lancez d'abord .\scripts\create_android_keystore.ps1, puis relancez .\scripts\build_android_apk.ps1 -Release."
    }
    Enable-ReleaseSigningIfAvailable
    Harden-AndroidManifest
    Update-AndroidAppearance
    Update-AndroidIcon

    if ($OpenAndroidStudio) {
        Invoke-Tool -Candidates @("npx.cmd", "npx") -Arguments @("cap", "open", "android")
    }

    if (-not $SkipBuild) {
        Push-Location (Join-Path $androidProject "android")
        try {
            $targets = if ($Release) { @("assembleRelease", "bundleRelease") } else { @("assembleDebug") }
            & ".\gradlew.bat" $targets
            if ($LASTEXITCODE -ne 0) {
                throw "Gradle a echoue ($LASTEXITCODE)."
            }
        }
        finally {
            Pop-Location
        }

        $kind = if ($Release) { "release" } else { "debug" }
        $sourceApk = Join-Path $androidProject "android\app\build\outputs\apk\$kind\app-$kind.apk"
        if (-not (Test-Path $sourceApk)) {
            $sourceApk = Get-ChildItem -Path (Join-Path $androidProject "android\app\build\outputs\apk") -Recurse -Filter "*.apk" |
                Sort-Object LastWriteTime -Descending |
                Select-Object -First 1 -ExpandProperty FullName
        }
        if (-not $sourceApk -or -not (Test-Path $sourceApk)) {
            throw "APK genere introuvable."
        }

        $outputDir = Join-Path $root "installer\output\android\$appVersion"
        New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
        $targetName = "BoulangerieLomoto"
        $targetApk = Join-Path $outputDir "$targetName-$appVersion-$kind.apk"
        Copy-Item -LiteralPath $sourceApk -Destination $targetApk -Force
        Write-Host "APK genere : $targetApk" -ForegroundColor Green

        if ($Release) {
            $sourceBundle = Join-Path $androidProject "android\app\build\outputs\bundle\release\app-release.aab"
            if (-not (Test-Path $sourceBundle)) {
                throw "Bundle Android release introuvable apres la compilation."
            }
            $targetBundle = Join-Path $outputDir "$targetName-$appVersion-release.aab"
            Copy-Item -LiteralPath $sourceBundle -Destination $targetBundle -Force
            Write-Host "AAB genere : $targetBundle" -ForegroundColor Green
        }
    }
    else {
        Write-Host "Projet Android prepare : $androidProject\android" -ForegroundColor Green
    }
}
finally {
    Pop-Location
}
