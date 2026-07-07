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

## Première utilisation

Au tout premier lancement, l'application ouvre un écran de **configuration
initiale** qui vous demande de créer le compte administrateur (nom, identifiant,
e-mail et mot de passe). Aucun mot de passe par défaut n'est distribué : le mot
de passe est choisi par l'administrateur et doit respecter la politique de
sécurité (longueur minimale, majuscule, minuscule, chiffre et symbole).

> Si vous migrez depuis une ancienne base contenant un compte au mot de passe
> hérité, l'application force son changement dès la première connexion.

## Tests

Une suite de tests couvre la logique sensible (mots de passe, montants de
commande, commissions, paies, verrouillage des journées clôturées,
authentification, licences et versionnage de schéma).

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```

Les tests s'exécutent sur une base SQLite jetable dans un dossier temporaire :
ils ne touchent jamais la base réelle. La CI GitHub Actions
([.github/workflows/ci.yml](/A:/Mon application python/.github/workflows/ci.yml))
les lance automatiquement à chaque push et pull request sur `main`.

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
