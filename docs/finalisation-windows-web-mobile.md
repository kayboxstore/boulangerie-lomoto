# Finalisation Windows, Web et Android

## Etat actuel

- Windows : application installee et synchronisee avec le serveur central.
- Web : application publique disponible sur `https://app.boulangerie-lomoto.com`.
- Android : projet Capacitor genere dans `android-apk`.
- APK debug genere : `installer/output/android/1.4.6/BoulangerieLomoto-1.4.6-debug.apk`.
- Controle Android du 11/06/2026 : build debug OK, tests Gradle OK, site public OK, manifeste durci avec HTTPS uniquement, sauvegarde Android desactivee.

## Choix technique retenu pour Android

L'APK ouvre directement la web pro officielle. On evite donc une deuxieme logique metier separee.

Avantages :

- memes donnees que Windows et Web ;
- memes droits d'acces ;
- corrections deployees une seule fois cote serveur/web ;
- installation simple sur telephone Android.

Contrainte :

- le telephone doit avoir Internet pour atteindre `app.boulangerie-lomoto.com`.

## Tests a faire avant livraison finale

1. Installer l'APK sur un telephone Android.
2. Tester en dehors du Wi-Fi du serveur.
3. Se connecter avec chaque role.
4. Verifier qu'une action Windows apparait sur Android.
5. Verifier qu'une action Android apparait sur Windows.
6. Tester la deconnexion forcee par Admin.
7. Tester une coupure Internet courte puis reprise.
8. Tester la cloture journaliere et l'ouverture des rapports.

## APK de production

L'APK debug sert aux tests. Pour une livraison professionnelle, il faut creer une cle Android privee :

```powershell
.\scripts\create_android_keystore.ps1
.\scripts\build_android_apk.ps1 -Release
```

La cle `.jks` doit etre sauvegardee hors du PC serveur. Sans cette cle, il sera impossible de publier une mise a jour qui remplace proprement l'APK deja installe.

Le script refuse maintenant de generer un APK release si `android-apk/android/keystore.properties` n'existe pas. Cela evite de livrer par erreur un APK non signe.

## Suite logique

1. Installer l'APK debug sur telephone et valider les tests reels.
2. Creer la cle Android release.
3. Generer l'APK release.
4. Sauvegarder la cle release sur support externe.
5. Conserver le domaine, Cloudflare Tunnel, la sauvegarde hebdomadaire et la 2FA.
6. Demarrer la version multi-client uniquement apres validation complete de Lomoto.
