# Validation de la version 1.3.15

Date : 2026-06-03

## Objectif

La version 1.3.15 ajoute le défilement tactile pour les utilisateurs qui travaillent avec un écran tactile.

## Résultat attendu

- Les grands formulaires défilent avec un geste du doigt.
- Les tableaux défilent verticalement avec un glissement du doigt.
- Les tableaux peuvent aussi défiler horizontalement quand les colonnes débordent.
- Les boutons, champs de saisie, listes déroulantes et cases à cocher restent utilisables normalement.
- Le geste tactile réinitialise aussi le délai de verrouillage automatique.

## Zones concernées

- Tableau de bord.
- Paramètres réseau.
- Caisse.
- Stock.
- Production.
- Commandes.
- Commissions.
- Travailleurs et paies.
- Rapports.
- Sauvegardes et clôtures.

## Commande de contrôle

```powershell
.\.venv\Scripts\python.exe -m compileall boulangerie_app main.py main_demo.py serveur_central.py serveur_windows_service.py
```

## Test manuel conseillé

Sur un écran tactile :

1. Ouvrir un module qui contient beaucoup d'éléments, par exemple `Commandes` ou `Travailleurs`.
2. Faire glisser le doigt vers le haut ou vers le bas sur une zone vide, un label ou un tableau.
3. Vérifier que la page ou le tableau défile.
4. Toucher un bouton pour vérifier qu'il clique toujours normalement.
5. Toucher un champ de saisie pour vérifier que le clavier et le curseur fonctionnent toujours.
