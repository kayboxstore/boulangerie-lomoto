# Validation de la version 1.3.8

Date : 2026-05-28

## Objectif

La version 1.3.8 revient au serveur local/réseau local.

Le serveur Internet est désactivé temporairement. L'application ne récupère plus automatiquement d'adresse Cloud Run, sauf si une variable d'environnement spéciale est volontairement configurée.

## Changements

- Désactivation du répertoire Internet par défaut.
- Publication de `server.json` avec `enabled=false` et `required=false`.
- Suppression effectuée du service Cloud Run de test.
- Désactivation effectuée de Firebase Hosting pour la version web de test.
- Maintien du mode connecté local avec le service Windows du serveur central.

## Test recommandé

1. Installer la version 1.3.8 sur le poste serveur.
2. Démarrer ou mettre à jour le service Windows du serveur central.
3. Installer la version 1.3.8 sur un poste client du même réseau local.
4. Cliquer sur `Détecter le serveur`.
5. Vérifier que l'application se connecte au serveur local et non à une URL Cloud Run.
