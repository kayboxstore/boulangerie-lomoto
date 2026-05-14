# Boulangerie Lomoto en Python

Application desktop Python qui reprend la version VB.NET avec :

- connexion et rôles utilisateur
- tableau de bord
- gestion des utilisateurs
- stock
- commandes
- caisse
- commissions
- rapports PDF journaliers
- vérification hebdomadaire des mises à jour
- mode connecté avec serveur central
- service Windows pour le serveur central

## Lancement

```powershell
python main.py
```

## Compte par défaut

- identifiant : `admin`
- mot de passe : `010203`

## Base de données

La base SQLite est maintenant stockée dans le profil Windows de l'utilisateur :

```text
%LOCALAPPDATA%\BoulangerieLomoto\boulangerie.db
```

Cela permet de créer un vrai setup Windows sans problème d'écriture dans `Program Files`.

## Formats de date acceptés

- `AAAA-MM-JJ`
- `JJ/MM/AAAA`

## Setup Windows

Le guide pas à pas est disponible dans [GUIDE_SETUP.md](/A:/Mon application python/GUIDE_SETUP.md).

## Mises à jour

Le guide de configuration des mises à jour est disponible dans [GUIDE_MISE_A_JOUR.md](/A:/Mon application python/GUIDE_MISE_A_JOUR.md).

## Mode connecté

Le guide de mise en réseau est disponible dans [GUIDE_MODE_CONNECTE.md](/A:/Mon application python/GUIDE_MODE_CONNECTE.md).
