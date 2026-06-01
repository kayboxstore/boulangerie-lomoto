# Validation de la version 1.3.9

Date : 2026-06-01

## Objectif

La version 1.3.9 renforce le mode serveur local avant toute reprise du cloud.

## Changements

- Ajout d'une sauvegarde automatique quotidienne sur le serveur central.
- Vérification horaire : si la sauvegarde du jour existe déjà, aucune copie inutile n'est créée.
- Nettoyage des sauvegardes automatiques de plus de 30 jours, en gardant au moins les 7 plus récentes.
- Affichage de la dernière sauvegarde automatique dans `Paramètres réseau`.

## Test recommandé

1. Installer la version 1.3.9 sur le poste serveur.
2. Ouvrir `Paramètres réseau`.
3. Cliquer sur `Installer / mettre à jour le service`, puis `Démarrer le service`.
4. Vérifier que le statut du service affiche une ligne `Sauvegarde automatique`.
5. Installer la version 1.3.9 sur un poste client et lancer la détection du serveur local.
