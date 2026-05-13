# Publication GitHub

Le script principal pour publier le projet sur GitHub est :

- [publish-github.ps1](/A:/Mon application python/scripts/publish-github.ps1)

## Ce que fait le script

1. Initialise le depot Git local si besoin.
2. Lance la connexion GitHub si elle n'est pas deja faite.
3. Cree le depot GitHub de l'application.
4. Cree la release GitHub avec le setup.
5. Cree le depot du manifeste `update.json`.
6. Publie le manifeste de mise a jour.

## Commande

Depuis le dossier du projet :

```powershell
cd "A:\Mon application python"
.\scripts\publish-github.ps1
```

## Prerequis

- `git` installe
- `gh` installe
- setup deja genere dans :
  `installer\output\BoulangerieLomotoSetup.exe`

Le script peut demander une connexion web GitHub la premiere fois, puis continue tout seul.

## Noms retenus

- utilisateur GitHub : `kayboxstore`
- depot application : `boulangerie-lomoto`
- depot updates : `boulangerie-lomoto-updates`

## URL finale du manifeste

Le manifeste public est lu depuis :

`https://raw.githubusercontent.com/kayboxstore/boulangerie-lomoto-updates/main/update.json`

Le script publie aussi un `download_url` fige sur la version courante, par exemple :

`https://github.com/kayboxstore/boulangerie-lomoto/releases/download/v1.0.2/BoulangerieLomotoSetup.exe`

Cela evite qu'un lien `latest/download` renvoie temporairement une ancienne version.
