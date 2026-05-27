# Architecture web, Android et Google

## Ce qui a été créé

- `cloud-run` : packaging de l'API centrale pour Google Cloud Run.
- `web-mobile-app` : interface web responsive utilisable sur PC et téléphone.
- `android-apk` : projet Capacitor pour produire une APK Android à partir de la version web.

## Fonctionnement

L'interface web et l'APK communiquent avec le serveur central grâce à l'API `/rpc`. Cela permet d'utiliser la même logique métier que l'application Windows sans recopier les règles dans plusieurs endroits.

## Chemin de production recommandé

1. Déployer l'API sur Cloud Run.
2. Migrer la base SQLite vers Cloud SQL PostgreSQL pour une exploitation sérieuse.
3. Déployer l'interface web sur Firebase Hosting.
4. Générer l'APK Android depuis le projet `android-apk`.
5. Faire tester les rôles : Admin, Caissier, Gestionnaire de stock, Gestionnaire des commandes.

## Attention

Cloud Run peut exécuter l'API actuelle, mais SQLite n'est pas le meilleur choix pour une application distante multi-utilisateur. Pour une vraie mise en production Google, Cloud SQL PostgreSQL est la prochaine étape indispensable.
