# Validation de la version 1.3.16

Date : 2026-06-03

## Objectif

La version 1.3.16 améliore le confort visuel et tactile de l'application.

## Améliorations intégrées

- Nouvelle palette ivoire, crème, rouge profond, brun et doré.
- Boutons plus grands, plus visibles et plus attractifs.
- Boutons des modules du tableau de bord agrandis pour une utilisation tactile.
- Champs de saisie, listes déroulantes et boutons avec plus d'espace intérieur.
- Tableaux plus lisibles avec lignes plus hautes et alternance de couleurs.
- Cartes d'indicateurs plus élégantes et mieux séparées.
- Couleurs d'alerte, de succès et d'information harmonisées.

## Commande de contrôle

```powershell
.\.venv\Scripts\python.exe -m compileall boulangerie_app main.py main_demo.py serveur_central.py serveur_windows_service.py
```

## Test manuel conseillé

1. Installer la version officielle `1.3.16`.
2. Ouvrir le tableau de bord et vérifier les nouveaux boutons de modules.
3. Ouvrir `Commandes`, `Caisse`, `Stock`, `Production` et `Travailleurs`.
4. Vérifier que les boutons sont faciles à toucher.
5. Vérifier que les champs restent lisibles et faciles à sélectionner.
6. Vérifier que les tableaux sont plus lisibles et défilent bien au doigt.
7. Vérifier que les messages d'erreur, de succès et d'alerte restent clairs.
