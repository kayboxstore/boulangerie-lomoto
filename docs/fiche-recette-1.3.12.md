# Fiche de recette utilisateur - Boulangerie Lomoto 1.3.12

Objectif : vérifier que la version 1.3.12 est prête pour une utilisation réelle.

| Domaine | Scénario | Rôle | Résultat attendu | Priorité |
|---|---|---|---|---|
| Installation | Installer la version officielle sur le PC serveur | Admin | L’application s’ouvre en version 1.3.12. | Haute |
| Installation | Installer la version démo sur un PC séparé | Admin | La démo s’ouvre sans mélanger les données officielles. | Moyenne |
| Mise à jour | Détection de la version 1.3.12 | Admin | La mise à jour 1.3.12 est proposée. | Haute |
| Mode connecté | Démarrer le service central | Admin | Le service central démarre sans erreur. | Haute |
| Mode connecté | Connexion d’un poste client | Utilisateur | Le mode connecté reste actif après connexion. | Haute |
| Mode connecté | Détection automatique du serveur | Utilisateur | L’adresse du serveur est récupérée automatiquement. | Haute |
| Connexion | Connexion administrateur | Admin | Le tableau de bord admin s’affiche. | Haute |
| Connexion | Blocage après mauvais mot de passe | Tous | Le compte est bloqué temporairement. | Haute |
| Tableau de bord | Affichage selon rôle admin | Admin | Tous les modules autorisés sont visibles. | Haute |
| Tableau de bord | Affichage selon rôle caissier | Caissier | Seuls les boutons utiles au caissier sont visibles. | Haute |
| Commandes | Commande Maman avec dette | Gestionnaire commandes | La dette est calculée correctement. | Haute |
| Commandes | Blocage montant reçu supérieur | Gestionnaire commandes | L’enregistrement est refusé. | Haute |
| Commandes | Détection client similaire | Gestionnaire commandes | L’application propose modification ou client différent. | Moyenne |
| Commandes | Grilles par statut | Gestionnaire commandes | Les dépositaires et mamans/vente cash sont lisibles séparément ou filtrables. | Moyenne |
| Commissions | Synchronisation automatique | Gestionnaire commandes | La commission apparaît sans bouton Enregistrer. | Haute |
| Commissions | Dépositaire sans commission | Gestionnaire commandes | La commission reste à zéro. | Haute |
| Caisse | Paiement de dette | Caissier | Le total des entrées augmente et la liste est visible dans la grille. | Haute |
| Caisse | Aucune dette à payer | Caissier | Le message indique que personne n’a payé car il n’y a pas de dette accumulée. | Moyenne |
| Caisse | Rapport mensuel allégé | Caissier/Admin | La liste des payeurs de dettes n’est pas reprise dans le mensuel. | Haute |
| Stock | Approvisionnement | Gestionnaire stock | Le stock augmente et l’historique est visible. | Haute |
| Stock | Cohérence sacs utilisés | Gestionnaire stock | L’application affiche une alerte de non-correspondance. | Haute |
| Production | Saisie manuelle sacs utilisés | Gestionnaire commandes | La valeur saisie est conservée et reportée. | Haute |
| Travailleurs | Créer un travailleur | Admin | Le travailleur apparaît dans la grille. | Moyenne |
| Travailleurs | Créer une paie | Admin | Le net à payer est calculé correctement. | Moyenne |
| Travailleurs | Bouton Fermer | Admin | La fenêtre se ferme proprement. | Moyenne |
| Rapports PDF | Rapport journalier complet | Admin | Logo, en-tête, tableaux et solde après commissions sont visibles. | Haute |
| Rapports PDF | Rapport mensuel commandes | Admin | Le rapport affiche une synthèse par statut, pas la liste complète. | Haute |
| Rapports PDF | Rapport par rôle stock | Gestionnaire stock | Seules les données stock sont visibles. | Moyenne |
| Rapports Excel | Export journalier Excel | Admin | Les onglets utiles existent et les montants sont formatés. | Moyenne |
| Rapports Excel | Export mensuel Excel | Admin | La feuille commandes est synthétique. | Haute |
| Sauvegarde | Sauvegarde manuelle | Admin | Un fichier de sauvegarde est créé. | Haute |
| Restauration | Restauration contrôlée | Admin | Les données restaurées sont correctes. | Haute |
| Clôture | Clôturer journée | Admin/Caissier | La journée est verrouillée contre les modifications non autorisées. | Haute |
| Sécurité | Lecture seule caissier sur commandes | Caissier | Le caissier voit sans modifier si prévu. | Moyenne |
| Performance | Ouverture modules | Tous | Le délai d’ouverture reste très court. | Moyenne |