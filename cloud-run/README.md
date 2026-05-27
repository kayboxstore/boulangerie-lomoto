# API Google Cloud Run

Ce dossier prepare le serveur central pour Google Cloud Run.
La configuration privilegie les couts bas : facturation a la requete, aucune instance au repos et une seule instance maximum par defaut.

## Deploiement rapide

```powershell
.\cloud-run\deploy-cloud-run.ps1 -ProjectId "votre-projet-google" -Region "europe-west1"
```

Le script :

- active les API Google necessaires ;
- cree le depot Artifact Registry si besoin ;
- construit l'image Docker ;
- deploie le service sur Cloud Run ;
- limite Cloud Run a 0 instance au repos et 1 instance maximum ;
- affiche l'URL publique de l'API.

## Couts

Firebase Hosting peut rester sur le plan Spark gratuit. Cloud Run a un quota gratuit, mais il reste un service pay-as-you-go si l'usage depasse les limites gratuites. Avant une mise en production, creez une alerte budget dans Google Cloud Billing.

## Important sur les donnees

Cette premiere version Cloud Run utilise le meme moteur SQLite que l'application Windows pour permettre un test rapide. Le disque Cloud Run n'est pas une base de donnees persistante fiable pour une exploitation reelle. Pour une vraie utilisation multi-postes distante, il faut migrer les donnees vers une base geree, par exemple Cloud SQL PostgreSQL ou Firestore selon le modele retenu.

La documentation officielle Google recommande Cloud SQL pour une base relationnelle centralisee avec Cloud Run.
