# Version APK Android

Ce projet emballe l'application web/mobile dans une application Android avec Capacitor.

## Préparer le projet Android

```powershell
cd android-apk
npm install
npm run build:web
npm run add:android
npm run sync
npm run open
```

Android Studio s'ouvre ensuite. Depuis Android Studio, lancez :

- `Build > Generate Signed Bundle / APK`
- choisissez `APK`
- signez l'application avec une clé Android

## Remarque importante

La génération finale d'un fichier `.apk` nécessite Android Studio, le SDK Android et une clé de signature. Sans ces outils installés sur le PC, le projet est prêt mais l'APK final ne peut pas être compilé localement.
