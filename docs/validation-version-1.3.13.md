# Validation de la version 1.3.13

Date : 2026-06-02

## Objectif

La version 1.3.13 ajuste les droits du module `Travailleurs et paies`.

## Points validés

- L'administrateur voit et manipule le module `Travailleurs`.
- Le caissier voit et manipule le module `Travailleurs`.
- Le gestionnaire de stock ne voit pas le module `Travailleurs`.
- Le gestionnaire des commandes ne voit pas le module `Travailleurs`.
- Les rapports du caissier incluent maintenant les travailleurs et les paies pour rester cohérents avec son accès au module.

## Commandes de contrôle

```powershell
.\.venv\Scripts\python.exe -m compileall boulangerie_app main.py main_demo.py serveur_central.py serveur_windows_service.py
```

Un jeu de données temporaire a aussi été utilisé pour générer et contrôler :

- `outputs/report-validation-1.3.13/reports/caissier.pdf`
- `outputs/report-validation-1.3.13/reports/caissier.xlsx`

Le rapport Excel caissier contient l'onglet `Travailleurs et paies` ainsi que les lignes `Travailleurs actifs` et `Paies travailleurs` dans le résumé.
