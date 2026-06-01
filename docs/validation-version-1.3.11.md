# Validation de la version 1.3.11

Date : 2026-06-01

## Objectif

La version 1.3.11 intègre les travailleurs et les paies dans les rapports PDF, Excel et les bilans de caisse générés par l'administrateur.

## Points validés

- Les rapports PDF journalier, mensuel et période affichent une section `Travailleurs et paies` pour l'admin.
- Les rapports Excel journalier, mensuel et période ajoutent un onglet `Travailleurs et paies`.
- Les bilans de caisse admin tiennent compte des paies comme charges salariales.
- Le caissier conserve les bilans caisse sans accès aux détails sensibles des paies.
- La génération PDF et Excel fonctionne avec un travailleur, une paie et une fiche de caisse de test.

## Commandes de contrôle

```powershell
.\.venv\Scripts\python.exe -m compileall boulangerie_app main.py main_demo.py serveur_central.py serveur_windows_service.py
```
