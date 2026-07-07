param(
    [switch]$OpenAndroidStudio
)

$ErrorActionPreference = "Stop"

if ($OpenAndroidStudio) {
    & "$PSScriptRoot\build_android_apk.ps1" -SkipBuild -OpenAndroidStudio
}
else {
    & "$PSScriptRoot\build_android_apk.ps1" -SkipBuild
}
