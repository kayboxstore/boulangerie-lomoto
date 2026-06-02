# Validation de la version 1.3.14

Date : 2026-06-02

## Objectif

La version 1.3.14 stabilise l'accès au module `Travailleurs et paies` en mode local et en mode connecté.

## Résultat validé

- L'administrateur voit et manipule le module `Travailleurs`.
- Le caissier voit et manipule le module `Travailleurs`.
- Le gestionnaire de stock ne voit pas le module `Travailleurs`.
- Le gestionnaire des commandes ne voit pas le module `Travailleurs`.
- En mode connecté, le serveur central autorise le caissier à lire et modifier les travailleurs et les paies.
- En mode connecté, le serveur central refuse l'accès au module `Travailleurs` pour le gestionnaire de stock et le gestionnaire des commandes.
- Le rapport du caissier inclut la section `Travailleurs et paies`.
- La sauvegarde locale et la restauration locale fonctionnent dans un dossier temporaire de recette.

## Commandes exécutées

```powershell
.\.venv\Scripts\python.exe -m compileall boulangerie_app main.py main_demo.py serveur_central.py serveur_windows_service.py
```

Une recette Python a aussi démarré un serveur central temporaire, connecté un caissier distant, ajouté un travailleur, ajouté une paie, refusé les rôles non autorisés, généré un rapport PDF, généré un rapport Excel et contrôlé une sauvegarde/restauration.

## Fichiers générés pendant la recette

- `outputs/validation-1.3.14-f7lcyory/reports/rapport-caissier-1.3.14.pdf`
- `outputs/validation-1.3.14-f7lcyory/reports/rapport-caissier-1.3.14.xlsx`
- `outputs/validation-1.3.14-f7lcyory/local-data/sauvegardes/boulangerie-lomoto-backup-20260602-143322.db`

## Conclusion

La version 1.3.14 est prête pour installation et test réel sur poste serveur + postes clients.
