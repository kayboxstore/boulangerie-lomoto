# API Google Cloud Run (recette uniquement)

Ce dossier permet de lancer une instance **jetable** du serveur central pour des tests techniques. Il ne doit pas recevoir les données réelles de la boulangerie : SQLite est stocké sur le disque éphémère de l'instance Cloud Run.

La production officielle reste le service Windows installé sur le PC serveur, exposé par Cloudflare Tunnel. Une future migration Cloud Run nécessiterait d'abord une base persistante gérée, par exemple Cloud SQL PostgreSQL.

## Garde-fous appliqués

- l'image est étiquetée avec la version réelle de l'application, sans valeur figée ancienne ;
- le jeton API n'est jamais passé en paramètre ni inscrit directement dans les variables d'environnement du script ;
- le jeton est généré aléatoirement et conservé dans Google Secret Manager ;
- Cloud Run reçoit une version numérique précise du secret ;
- le compte de service reçoit seulement l'accès de lecture au secret ;
- l'authentification par session reste obligatoire ;
- le déploiement est bloqué sans confirmation explicite du caractère éphémère de SQLite ;
- le nombre d'instances est limité à 1 par défaut et le minimum reste à 0.

## Déploiement d'une recette jetable

```powershell
.\cloud-run\deploy-cloud-run.ps1 `
  -ProjectId "votre-projet-google" `
  -Region "europe-west1" `
  -AllowEphemeralSqlite
```

Pour utiliser un compte de service dédié :

```powershell
.\cloud-run\deploy-cloud-run.ps1 `
  -ProjectId "votre-projet-google" `
  -ServiceAccount "lomoto-cloud-run@votre-projet-google.iam.gserviceaccount.com" `
  -AllowEphemeralSqlite
```

Pour effectuer une rotation volontaire du jeton :

```powershell
.\cloud-run\deploy-cloud-run.ps1 `
  -ProjectId "votre-projet-google" `
  -RotateApiToken `
  -AllowEphemeralSqlite
```

Le script active Cloud Run, Cloud Build, Artifact Registry et Secret Manager, crée les ressources manquantes, construit l'image, puis déploie l'API. Le service reste publiquement joignable au niveau réseau afin que les clients puissent l'atteindre, mais les appels métier restent protégés par le jeton et les sessions applicatives.

## Coûts et exploitation

Cloud Run et les services associés sont facturés à l'usage après leurs quotas gratuits. Créez une alerte de budget avant tout essai et supprimez le service de recette lorsqu'il n'est plus utile.

Références officielles :

- https://docs.cloud.google.com/run/docs/configuring/services/secrets
- https://docs.cloud.google.com/run/docs/authenticating/public
- https://docs.cloud.google.com/sdk/gcloud/reference/run/deploy
