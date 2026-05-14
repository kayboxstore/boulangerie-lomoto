# Publication GitHub

Le script principal pour publier le projet sur GitHub est :

- [publish-github.ps1](/A:/Mon application python/scripts/publish-github.ps1)

## Ce que fait le script

1. Régénère l'exécutable PyInstaller.
2. Recompile le setup Inno Setup.
3. Initialise le dépôt Git local si besoin.
4. Lance la connexion GitHub si elle n'est pas déjà faite.
5. Crée le dépôt GitHub de l'application.
6. Crée ou met à jour la release GitHub avec le setup.
7. Crée le dépôt du manifeste `update.json`.
8. Publie le manifeste de mise à jour.

## Commande

Depuis le dossier du projet :

```powershell
cd "A:\Mon application python"
.\scripts\publish-github.ps1
```

## Prérequis

- `git` installé
- `gh` installé
- setup déjà génère dans :
  `installer\output\BoulangerieLomotoSetup.exe`

Le script peut demander une connexion web GitHub la première fois, puis continue tout seul.

Si vous avez déjà régénéré l'exe et le setup vous-même, vous pouvez ignorer la reconstruction automatique avec :

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\publish-github.ps1" -SkipBuild
```

## Noms retenus

- utilisateur GitHub : `kayboxstore`
- dépôt application : `boulangerie-lomoto`
- dépôt updates : `boulangerie-lomoto-updates`

## URL finale du manifeste

Le manifeste public est lu depuis :

`https://raw.githubusercontent.com/kayboxstore/boulangerie-lomoto-updates/main/update.json`

Le script publie aussi un `download_url` fige sur la version courante, par exemple :

`https://github.com/kayboxstore/boulangerie-lomoto/releases/download/v1.0.2/BoulangerieLomotoSetup.exe`

Cela évite qu'un lien `latest/download` renvoie temporairement une ancienne version.
