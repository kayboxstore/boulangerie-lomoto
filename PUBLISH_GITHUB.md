# Publication GitHub

Le script principal pour publier le projet sur GitHub est :

- [publish-github.ps1](/A:/Mon application python/scripts/publish-github.ps1)

## Ce que fait le script

1. Regenere l'executable PyInstaller.
2. Recompile le setup Inno Setup.
3. Initialise le depot Git local si besoin.
4. Lance la connexion GitHub si elle n'est pas deja faite.
5. Cree le depot GitHub de l'application.
6. Cree ou met a jour la release GitHub avec le setup.
7. Cree le depot du manifeste `update.json`.
8. Publie le manifeste de mise a jour.

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

Si vous avez deja regenere l'exe et le setup vous-meme, vous pouvez ignorer la reconstruction automatique avec :

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\publish-github.ps1" -SkipBuild
```

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
