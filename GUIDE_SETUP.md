# Guide setup Windows

Ce guide montre une methode simple pour creer vous-meme le setup de l'application.

## 1. Preparer l'environnement

Placez-vous d'abord dans le dossier du projet :

```powershell
cd "A:\Mon application python"
```

Installez les outils une seule fois :

```powershell
.\.venv\Scripts\pip.exe install pyinstaller
```

Installez aussi Inno Setup sur Windows :

- site officiel : https://jrsoftware.org/isinfo.php

## 2. Generer l'executable

Depuis le dossier du projet, lancez :

```powershell
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean --windowed --onedir --name "Boulangerie Lomoto" main.py
```

Resultat attendu :

- executable : `dist\Boulangerie Lomoto\Boulangerie Lomoto.exe`

## 3. Tester l'executable

Avant de fabriquer le setup, testez d'abord l'exe :

```powershell
& ".\dist\Boulangerie Lomoto\Boulangerie Lomoto.exe"
```

Si le chemin contient des espaces, PowerShell doit recevoir :

- le chemin entre guillemets
- et l'operateur `&` devant

## 4. Creer le setup avec Inno Setup

Le projet contient deja un script exemple :

- `installer\setup.iss`

Ouvrez ce fichier avec Inno Setup, puis cliquez sur **Compile**.

Le setup sera genere dans :

- `installer\output`

Important :

Le setup doit etre compile apres PyInstaller. Si vous recompilez seulement `setup.iss` sans regenerer d'abord `dist\Boulangerie Lomoto`, vous risquez de republier un ancien exe.

## 4 bis. Methode recommandee en une seule commande

Pour eviter un mauvais ordre de build, utilisez plutot :

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\publish-github.ps1" -SkipBuild:$false
```

Cette commande :

1. regenere l'exe PyInstaller
2. recompile le setup Inno Setup
3. publie ensuite la release GitHub et le manifeste

## 5. Important sur la base SQLite

L'application enregistre la base ici :

```text
%LOCALAPPDATA%\BoulangerieLomoto\boulangerie.db
```

Donc :

- le setup peut installer le programme dans `Program Files`
- les donnees utilisateur restent modifiables
- une mise a jour ne supprime pas automatiquement la base

## 6. Commande de travail la plus simple

Quand vous voudrez refaire un setup :

1. Ouvrir le projet.
2. Lancer PyInstaller.
3. Tester l'exe.
4. Compiler `installer\setup.iss` avec Inno Setup.
5. Publier seulement apres ces deux etapes.

## 7. Plus tard

Vous pourrez ensuite ajouter :

- une icone avec `--icon chemin\\vers\\icone.ico`
- un numero de version dans le script Inno Setup
- un raccourci bureau
- une verification de mise a jour
