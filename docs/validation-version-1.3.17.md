# Validation version 1.3.17

## Objectif

Corriger le thème visuel jugé insuffisant, ajouter les éléments légaux et améliorer la navigation dans le module Travailleurs.

## Changements à vérifier

- Les formulaires utilisent un thème plus professionnel : fond clair, cartes blanches, boutons bleu nuit et accent vert-bleu.
- La page de connexion affiche une option `À propos`.
- Le Tableau de bord affiche une option `À propos`.
- La fenêtre `À propos` présente Augustin Kayembe, le téléphone `+243 991 599 600` et les adresses `kayboxstore@gmail.com` / `kayboxstore@outlook.fr`.
- Le copyright affiche l'année courante et se rafraîchit automatiquement.
- Le module `Travailleurs et paies` contient un bouton `Fermer` visible en haut à droite et en bas.
- Les tableaux gardent une lecture claire avec des lignes alternées.

## Commandes de contrôle

```powershell
.\.venv\Scripts\python.exe -m compileall boulangerie_app main.py main_demo.py serveur_central.py serveur_windows_service.py
```

## Test manuel conseillé

1. Installer la version officielle `1.3.17`.
2. Ouvrir la connexion et vérifier le nouveau style.
3. Cliquer sur `À propos` depuis la connexion.
4. Se connecter, ouvrir `À propos` depuis le Tableau de bord.
5. Ouvrir `Travailleurs`, puis vérifier les deux boutons `Fermer`.
6. Parcourir `Caisse`, `Commandes`, `Stock`, `Production` et `Rapports` pour vérifier que les boutons restent lisibles.
