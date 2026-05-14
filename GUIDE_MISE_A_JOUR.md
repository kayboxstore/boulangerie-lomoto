# Guide des mises à jour

L'application vérifie maintenant les mises à jour au maximum une fois tous les 7 jours, au moment de l'ouverture du tableau de bord.

## Comment ca marche

L'application lit un manifeste JSON disponible sur internet.

Exemple de manifeste :

```json
{
  "version": "1.0.1",
  "download_url": "https://votre-site.com/BoulangerieLomotoSetup.exe",
  "published_at": "2026-05-13",
  "notes": "Correction du module stock et amélioration de la caisse."
}
```

Si la version distante est plus récente que la version installée, l'application affiche une boîte de dialogue et propose d'ouvrir le lien de téléchargement.

## Où configurer l'URL du manifeste

Vous avez 2 options.

## Configuration recommandee pour votre compte

Comme votre nom d'utilisateur GitHub est `kayboxstore`, je vous recommande :

1. Dépôt application : `boulangerie-lomoto`
2. Dépôt manifeste : `boulangerie-lomoto-updates`

Avec cette organisation :

- manifeste de mise à jour :
  `https://raw.githubusercontent.com/kayboxstore/boulangerie-lomoto-updates/main/update.json`
- setup a telecharger :
  `https://github.com/kayboxstore/boulangerie-lomoto/releases/download/v1.0.2/BoulangerieLomotoSetup.exe`

Cette URL de manifeste est déjà configurée dans l'application.

Important :

Pour éviter qu'un ancien setup soit repris par le cache, le champ `download_url` du manifeste doit toujours viser une version précise, par exemple :

```text
https://github.com/kayboxstore/boulangerie-lomoto/releases/download/v1.0.2/BoulangerieLomotoSetup.exe
```

Il vaut mieux ne pas utiliser `releases/latest/download/...` dans le manifeste.

### Option 1 : dans le code avant de regénérer l'application

Editez ce fichier :

- [version.py](/A:/Mon application python/boulangerie_app/version.py)

Renseignez cette variable :

```python
DEFAULT_UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/kayboxstore/boulangerie-lomoto-updates/main/update.json"
```

Puis régénérez l'exe et le setup.

### Option 2 : sur une machine déjà installée

L'application créé automatiquement ce fichier :

```text
%LOCALAPPDATA%\BoulangerieLomoto\update_config.json
```

Exemple :

```json
{
  "manifest_url": "https://raw.githubusercontent.com/kayboxstore/boulangerie-lomoto-updates/main/update.json",
  "check_interval_days": 7
}
```

Cela permet de changer la source de mise à jour sans recompiler.

## Fichiers utilises

- configuration locale : `%LOCALAPPDATA%\BoulangerieLomoto\update_config.json`
- état des vérifications : `%LOCALAPPDATA%\BoulangerieLomoto\update_state.json`

## Ce qu'il vous faudra pour que cela marche vraiment

Il faut heberger sur internet :

1. Le fichier JSON de manifeste.
2. Le fichier setup a telecharger.

Le plus simple est :

- un site web
- ou un hebergement de fichiers
- ou un lien direct vers votre setup sur votre serveur

## Pensee importante pour chaque nouvelle version

Quand vous publiez une nouvelle version :

1. Vous augmentez `APP_VERSION` dans [version.py](/A:/Mon application python/boulangerie_app/version.py).
2. Vous augmentez aussi `MyAppVersion` dans [setup.iss](/A:/Mon application python/installer/setup.iss).
3. Vous régénérez l'exe.
4. Vous régénérez le setup.
5. Vous mettez à jour le manifeste JSON en ligne avec le lien exact de la release publiee, par exemple `.../releases/download/v1.0.2/...`.
