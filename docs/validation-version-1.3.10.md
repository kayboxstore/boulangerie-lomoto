# Validation de la version 1.3.10

Date : 2026-06-01

## Objectif

La version 1.3.10 ajoute un module `Travailleurs` pour gérer le personnel et les paies.

## Changements

- Nouveau bouton `Travailleurs` visible uniquement pour l'administrateur.
- Création et modification des fiches travailleurs : nom, fonction, téléphone, adresse, date d'embauche, salaire mensuel, statut et observations.
- Enregistrement des paies : période, montant brut, prime, avance, retenue, mode de paiement, statut et observations.
- Calcul automatique du net à payer : brut + prime - avance - retenue.
- Conservation de l'historique : un travailleur qui possède déjà des paies est désactivé au lieu d'être supprimé définitivement.
- Le module fonctionne aussi en mode connecté via le serveur central local.

## Test recommandé

1. Se connecter en tant qu'administrateur.
2. Ouvrir `Travailleurs`.
3. Ajouter un travailleur actif avec un salaire mensuel.
4. Enregistrer une paie et vérifier le calcul du net à payer.
5. Vérifier que le résumé du tableau de bord affiche les paies des travailleurs.
