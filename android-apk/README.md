# APK Android Boulangerie Lomoto

Cette application Android emballe la vraie version web pro :

`https://app.boulangerie-lomoto.com`

Elle utilise donc la meme base et les memes donnees que Windows et que le navigateur.

## Preparation automatique

Depuis la racine du projet :

```powershell
.\scripts\build_android_apk.ps1
```

Le script :

- retrouve Java et le SDK Android installes avec Android Studio ;
- installe les dependances Capacitor ;
- cree le projet Android si necessaire ;
- synchronise la configuration ;
- applique le logo et la version ;
- genere un APK debug installable.

L'APK debug est genere dans :

`installer\output\android\<version>\BoulangerieLomoto-<version>-debug.apk`

## Ouvrir dans Android Studio

```powershell
.\scripts\build_android_apk.ps1 -OpenAndroidStudio
```

## APK final signe

Pour livrer une version professionnelle hors test, il faut une cle de signature Android.
Cette cle doit rester privee et sauvegardee hors du PC serveur.

```powershell
.\scripts\create_android_keystore.ps1
.\scripts\build_android_apk.ps1 -Release
```

L'APK release est genere dans :

`installer\output\android\<version>\BoulangerieLomoto-<version>-release.apk`

Si la cle Android n'existe pas, le script refuse le build release. C'est volontaire : un APK release non signe ne doit pas etre livre.

## Installation sur telephone de test

Quand le telephone Android est branche avec un bon cable USB et que le debogage USB est autorise :

```powershell
.\scripts\install_android_debug.ps1
```

## Principe retenu

On ne duplique pas la logique metier dans Android. L'APK ouvre l'application web pro officielle, deja synchronisee avec Windows via le serveur central. Cela donne un seul produit a maintenir et les memes droits d'acces sur PC, Web et Mobile.
