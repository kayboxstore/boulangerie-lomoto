# Guide mises a jour

L'application verifie maintenant les mises a jour au maximum une fois tous les 7 jours, au moment de l'ouverture du tableau de bord.

## Comment ca marche

L'application lit un manifeste JSON disponible sur internet.

Exemple de manifeste :

```json
{
  "version": "1.0.1",
  "download_url": "https://votre-site.com/BoulangerieLomotoSetup.exe",
  "published_at": "2026-05-13",
  "notes": "Correction du module stock et amelioration de la caisse."
}
```

Si la version distante est plus recente que la version installee, l'application affiche une boite de dialogue et propose d'ouvrir le lien de telechargement.

## Ou configurer l'URL du manifeste

Vous avez 2 options.

## Configuration recommandee pour votre compte

Comme votre nom d'utilisateur GitHub est `kayboxstore`, je vous recommande :

1. Depot application : `boulangerie-lomoto`
2. Depot manifeste : `boulangerie-lomoto-updates`

Avec cette organisation :

- manifeste de mise a jour :
  `https://raw.githubusercontent.com/kayboxstore/boulangerie-lomoto-updates/main/update.json`
- setup a telecharger :
  `https://github.com/kayboxstore/boulangerie-lomoto/releases/latest/download/BoulangerieLomotoSetup.exe`

Cette URL de manifeste est deja configuree dans l'application.

### Option 1 : dans le code avant de regenerer l'application

Editez ce fichier :

- [version.py](/A:/Mon application python/boulangerie_app/version.py)

Renseignez cette variable :

```python
DEFAULT_UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/kayboxstore/boulangerie-lomoto-updates/main/update.json"
```

Puis regenerez l'exe et le setup.

### Option 2 : sur une machine deja installee

L'application cree automatiquement ce fichier :

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

Cela permet de changer la source de mise a jour sans recompiler.

## Fichiers utilises

- configuration locale : `%LOCALAPPDATA%\BoulangerieLomoto\update_config.json`
- etat des verifications : `%LOCALAPPDATA%\BoulangerieLomoto\update_state.json`

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
3. Vous regenerez l'exe.
4. Vous regenerez le setup.
5. Vous mettez a jour le manifeste JSON en ligne.
