# Validation de la version 1.3.12

Date : 2026-06-02

## Objectif

La version 1.3.12 améliore la lisibilité des rapports et ajoute les derniers ajustements demandés sur le module Travailleurs.

## Points validés

- Les rapports PDF et Excel affichent `Solde après paiement des commissions` juste après `Net à payer des commissions` dans le premier tableau récapitulatif.
- Le rapport mensuel ne reprend plus la liste complète de toutes les commandes du mois.
- Le rapport mensuel ne reprend plus la liste des personnes ayant payé leurs dettes.
- Les commandes mensuelles sont présentées sous forme de synthèse par statut.
- Les tableaux PDF et Excel utilisent une mise en forme plus élégante avec en-têtes bleu foncé, texte lisible et lignes alternées.
- Le module `Travailleurs et paies` affiche un bouton `Fermer`.

## Commandes de contrôle

```powershell
.\.venv\Scripts\python.exe -m compileall boulangerie_app main.py main_demo.py serveur_central.py serveur_windows_service.py
```

Un jeu de données temporaire a aussi été utilisé pour générer et contrôler les rapports suivants :

- `outputs/report-validation-1.3.12/reports/journalier.pdf`
- `outputs/report-validation-1.3.12/reports/mensuel.pdf`
- `outputs/report-validation-1.3.12/reports/periode.pdf`
- `outputs/report-validation-1.3.12/reports/journalier.xlsx`
- `outputs/report-validation-1.3.12/reports/mensuel.xlsx`
- `outputs/report-validation-1.3.12/reports/periode.xlsx`

## Supports préparés

- `docs/supports/1.3.12/Guide-exploitation-Boulangerie-Lomoto-1.3.12.docx`
- `docs/supports/1.3.12/Guide-exploitation-Boulangerie-Lomoto-1.3.12.pdf`
- `docs/supports/1.3.12/Fiche-recette-Boulangerie-Lomoto-1.3.12.xlsx`

## Contrôles complémentaires

- Le guide Word contient les sections d'installation, d'exploitation, de sécurité, de rapports et de dépannage.
- Le PDF du guide a été généré et contrôlé.
- La fiche Excel contient les onglets `Recette complète`, `Résumé` et `Mode d'emploi`.
- Le rendu visuel DOCX page par page n'a pas été exécuté parce que LibreOffice n'est pas installé sur ce poste.

## Test réel restant

Le setup ne doit pas être lancé automatiquement par script sur la machine de production, afin d'éviter une modification involontaire du service Windows ou de l'installation réelle. La validation finale doit être faite manuellement avec la fiche de recette Excel sur :

- le PC serveur / admin ;
- au moins un PC client ;
- la version démo, séparée de la version officielle.
