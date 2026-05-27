# Validation de la version 1.3.7

Date : 2026-05-27

## Objectif

La version 1.3.7 ajoute la connexion distante par Internet.

Un poste client peut maintenant récupérer automatiquement l'adresse publique du serveur central depuis `server.json`, puis se connecter même s'il n'utilise pas le même Wi-Fi ou la même box Internet que le poste principal.

## Changements principaux

- Ajout du fichier public `server.json` dans le dépôt des mises à jour.
- Détection automatique du serveur Internet avant la recherche sur réseau local.
- Bouton `Utiliser l'adresse Internet` dans les paramètres réseau.
- Ajout d'une session distante après connexion avec identifiant et mot de passe.
- Les appels distants suivants utilisent la session de l'utilisateur connecté.
- Le serveur distant exige une session par défaut, sauf désactivation explicite par variable d'environnement.

## Livrables attendus

- Version officielle : `installer/output/1.3.7/BoulangerieLomotoSetup.exe`
- Version démo : `installer/output/1.3.7-demo/BoulangerieLomotoDemoSetup.exe`

## Test recommandé

1. Installer la version 1.3.7 sur le poste serveur.
2. Publier ou vérifier l'URL publique du serveur dans `server.json`.
3. Installer la version 1.3.7 sur un poste client connecté à une autre connexion Internet.
4. Ouvrir l'application et vérifier que le mode connecté indique l'adresse Internet du serveur.
5. Se connecter avec un utilisateur existant.
6. Vérifier que les données ajoutées sont visibles depuis un autre poste connecté au même serveur.

## Point d'attention

L'adresse Internet doit pointer vers le vrai serveur central utilisé par l'entreprise.
Si elle pointe vers Cloud Run, les données sont celles du serveur Cloud Run. Si l'objectif est d'utiliser exactement les données du PC serveur local, il faut publier ce PC avec un tunnel sécurisé ou migrer la base centrale vers une base cloud persistante.
