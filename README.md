# Boulangerie Lomoto en Python

Application desktop Python qui reprend la version VB.NET avec :

- connexion et roles utilisateur
- tableau de bord
- gestion des utilisateurs
- stock
- commandes
- caisse
- commissions
- rapports PDF journaliers
- verification hebdomadaire des mises a jour
- mode connecte avec serveur central

## Lancement

```powershell
python main.py
```

## Compte par defaut

- identifiant : `admin`
- mot de passe : `010203`

## Base de donnees

La base SQLite est maintenant stockee dans le profil Windows de l'utilisateur :

```text
%LOCALAPPDATA%\BoulangerieLomoto\boulangerie.db
```

Cela permet de creer un vrai setup Windows sans probleme d'ecriture dans `Program Files`.

## Formats de date acceptes

- `AAAA-MM-JJ`
- `JJ/MM/AAAA`

## Setup Windows

Le guide pas a pas est disponible dans [GUIDE_SETUP.md](/A:/Mon application python/GUIDE_SETUP.md).

## Mises a jour

Le guide de configuration des mises a jour est disponible dans [GUIDE_MISE_A_JOUR.md](/A:/Mon application python/GUIDE_MISE_A_JOUR.md).

## Mode connecte

Le guide de mise en reseau est disponible dans [GUIDE_MODE_CONNECTE.md](/A:/Mon application python/GUIDE_MODE_CONNECTE.md).
