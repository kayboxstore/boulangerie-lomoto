# Version web sérieuse - Boulangerie Lomoto

## Objectif

Créer une version web parallèle à l'application Windows, utilisable sur PC, tablette et téléphone, sans supprimer la version Windows existante.

## Architecture retenue pour la démonstration

- Serveur central Python : `serveur_central.py`, port `8765`.
- Interface web : `web-mobile-app`, lancée avec Vite sur le port `5173`.
- Communication : API `/rpc` déjà utilisée par le mode connecté.
- Données : même base et mêmes règles métier que l'application Windows.

## Lancement de démonstration

Depuis la racine du projet :

```powershell
.\scripts\start-web-boulangerie-lomoto.ps1
```

Identifiants admin par défaut :

- Identifiant : `a.kayembe`
- Mot de passe : `010203`

## Modules couverts

- Tableau de bord avec indicateurs globaux.
- Stock : approvisionnement, sorties et alertes.
- Production : bacs commandés, bacs produits, sacs utilisés, écart et couverture.
- Commandes : calcul automatique du montant à percevoir et blocage du trop-perçu.
- Caisse : dépenses, dettes payées, total entrées et solde.
- Commissions automatiques.
- Travailleurs et paies.
- Rapports imprimables/PDF depuis le navigateur.
- Utilisateurs, clôtures, historique et sauvegardes selon le rôle.

## Nom de domaine

Pour `boulangerie-lomoto.com`, deux scénarios sont possibles :

- Démonstration économique : le PC serveur reste allumé, puis Cloudflare Tunnel expose l'API et/ou l'interface web sans ouvrir de ports.
- Production cloud : hébergement complet avec base de données distante. C'est plus robuste, mais plus coûteux.

## Prochaine étape après validation

Préparer le déploiement public : nom de domaine, certificat HTTPS, tunnel ou hébergement cloud, sauvegardes automatiques et procédure de reprise en cas de panne.
