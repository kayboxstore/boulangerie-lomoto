# Validation version 1.3.18

## Objectif

Revenir à l'ancien design et ajouter les contraintes demandées sur la connexion, les rapports mensuels et les mises à jour.

## Changements à vérifier

- Les formulaires retrouvent l'ancien design bleu clair avec titres rouges.
- Les boutons de modules du Tableau de bord reviennent au rendu classique.
- La page de connexion contient une case `Afficher` à côté du mot de passe.
- La fenêtre `À propos`, le copyright dynamique et le bouton `Fermer` du module Travailleurs restent disponibles.
- L'application vérifie les mises à jour en arrière-plan à chaque ouverture du Tableau de bord.
- Une mise à jour disponible reste facultative pendant 10 jours, puis devient obligatoire.
- À partir du 8 du mois, le rapport mensuel du mois précédent devient obligatoire.
- Tant que le rapport mensuel obligatoire n'est pas généré, les grands modules sont bloqués et la fenêtre des rapports PDF s'ouvre en mode mensuel.
- Le suivi des rapports mensuels fonctionne aussi en mode connecté serveur-client.

## Commandes de contrôle

```powershell
.\.venv\Scripts\python.exe -m compileall boulangerie_app main.py main_demo.py serveur_central.py serveur_windows_service.py
```

## Test manuel conseillé

1. Installer la version officielle `1.3.18`.
2. Vérifier la page de connexion et la case `Afficher`.
3. Se connecter et vérifier l'ancien rendu du Tableau de bord.
4. Tester `À propos`.
5. Ouvrir `Travailleurs` et vérifier le bouton `Fermer`.
6. Simuler une date à partir du 8 du mois pour vérifier l'obligation du rapport mensuel.
7. Tester la détection de mise à jour avec un manifeste supérieur à la version installée.
