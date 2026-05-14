# Guide setup Windows

Ce guide montre une méthode simple pour créer vous-même le setup de l'application.

## 1. Préparer l'environnement

Placez-vous d'abord dans le dossier du projet :

```powershell
cd "A:\Mon application python"
```

Installez d'abord les dépendances du projet puis les outils de build :

```powershell
.\.venv\Scripts\pip.exe install -r requirements.txt
.\.venv\Scripts\pip.exe install pyinstaller
```

Installez aussi Inno Setup sur Windows :

- site officiel : https://jrsoftware.org/isinfo.php

## 2. Générer les exécutables

Depuis le dossier du projet, lancez :

```powershell
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean --windowed --onedir --name "Boulangerie Lomoto" main.py
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean --console --onefile --name "Boulangerie Lomoto Service" --distpath ".\dist\Boulangerie Lomoto" --workpath ".\build\service" serveur_windows_service.py
```

Résultat attendu :

- exécutable : `dist\Boulangerie Lomoto\Boulangerie Lomoto.exe`
- service Windows : `dist\Boulangerie Lomoto\Boulangerie Lomoto Service.exe`

## 3. Tester l'exécutable

Avant de fabriquer le setup, testez d'abord l'exe :

```powershell
& ".\dist\Boulangerie Lomoto\Boulangerie Lomoto.exe"
```

Si le chemin contient des espaces, PowerShell doit recevoir :

- le chemin entre guillemets
- et l'operateur `&` devant

## 4. Créer le setup avec Inno Setup

Le projet contient déjà un script exemple :

- `installer\setup.iss`

Ouvrez ce fichier avec Inno Setup, puis cliquez sur **Compile**.

Le setup sera généré dans :

- `installer\output`

Important :

Le setup doit être compilé après PyInstaller. Si vous recompilez seulement `setup.iss` sans régénérer d'abord `dist\Boulangerie Lomoto`, vous risquez de republier un ancien exe.

## 4 bis. Méthode recommandée en une seule commande

Pour éviter un mauvais ordre de build, utilisez plutôt :

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\publish-github.ps1" -SkipBuild:$false
```

Cette commande :

1. régénère l'exe PyInstaller
2. régénère aussi l'exe du service Windows
3. recompile le setup Inno Setup
4. publie ensuite la release GitHub et le manifeste

## 5. Important sur la base SQLite

L'application enregistre la base ici :

```text
%LOCALAPPDATA%\BoulangerieLomoto\boulangerie.db
```

Donc :

- le setup peut installer le programme dans `Program Files`
- les données utilisateur restent modifiables
- une mise à jour ne supprime pas automatiquement la base

## 6. Commande de travail la plus simple

Quand vous voudrez refaire un setup :

1. Ouvrir le projet.
2. Lancer PyInstaller.
3. Vérifier aussi `Boulangerie Lomoto Service.exe`.
4. Tester l'exe principal.
5. Compiler `installer\setup.iss` avec Inno Setup.
6. Publier seulement apres ces etapes.

## 7. Plus tard

Vous pourrez ensuite ajouter :

- une icone avec `--icon chemin\\vers\\icone.ico`
- un numero de version dans le script Inno Setup
- un raccourci bureau
- une vérification de mise à jour
