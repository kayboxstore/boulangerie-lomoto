$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$androidProject = Join-Path $root "android-apk"
$javaHome = $env:JAVA_HOME
if (-not $javaHome -or -not (Test-Path (Join-Path $javaHome "bin\keytool.exe"))) {
    $javaHome = "C:\Program Files\Android\Android Studio\jbr"
}
if (-not (Test-Path (Join-Path $javaHome "bin\keytool.exe"))) {
    $javaHome = "C:\Program Files\Android\openjdk\jdk-21.0.8"
}
if (-not (Test-Path (Join-Path $javaHome "bin\keytool.exe"))) {
    throw "keytool introuvable. Installez Android Studio avec son JBR."
}

function ConvertTo-PlainText {
    param([securestring]$Secret)

    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secret)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

$keystoreDir = Join-Path $androidProject "keystore"
New-Item -ItemType Directory -Path $keystoreDir -Force | Out-Null

$keystoreFile = Join-Path $keystoreDir "boulangerie-lomoto-release.jks"
$alias = Read-Host "Alias de la cle Android [boulangerie-lomoto]"
if (-not $alias) {
    $alias = "boulangerie-lomoto"
}

$storePassword = ConvertTo-PlainText (Read-Host "Mot de passe de la cle Android" -AsSecureString)
$keyPassword = ConvertTo-PlainText (Read-Host "Confirmez le mot de passe de la cle Android" -AsSecureString)
if ($storePassword -ne $keyPassword) {
    throw "Les mots de passe ne correspondent pas."
}

$keytool = Join-Path $javaHome "bin\keytool.exe"
& $keytool -genkeypair -v `
    -keystore $keystoreFile `
    -alias $alias `
    -keyalg RSA `
    -keysize 2048 `
    -validity 10000 `
    -storepass $storePassword `
    -keypass $keyPassword `
    -dname "CN=Boulangerie Lomoto, OU=General Investment Services, O=General Investment Services, L=Kinshasa, ST=Kinshasa, C=CD"

if ($LASTEXITCODE -ne 0) {
    throw "Creation de la cle Android echouee."
}

$androidDir = Join-Path $androidProject "android"
if (Test-Path $androidDir) {
    $properties = @"
storePassword=$storePassword
keyPassword=$keyPassword
keyAlias=$alias
storeFile=../keystore/boulangerie-lomoto-release.jks
"@
    Set-Content -LiteralPath (Join-Path $androidDir "keystore.properties") -Value $properties -Encoding ASCII
}

Write-Host "Cle Android creee : $keystoreFile" -ForegroundColor Green
Write-Host "Conservez ce fichier hors du PC serveur. Sans cette cle, les futures mises a jour APK ne pourront pas remplacer l'application installee." -ForegroundColor Yellow
