# Validation de la version 1.3.5

Date de validation : 27/05/2026

Application : Boulangerie Lomoto

Version testée : 1.3.5

## Résumé

La version 1.3.5 est prête pour un test client encadré.

Elle contient deux installateurs séparés :

- Version officielle : `installer/output/1.3.5/BoulangerieLomotoSetup.exe`
- Version démo : `installer/output/1.3.5-demo/BoulangerieLomotoDemoSetup.exe`

## Identifiants validés

Version officielle :

```text
Identifiant : a.kayembe
Mot de passe : 010203
Rôle : Admin
```

Version démo :

```text
Identifiant : demo.admin
Mot de passe : demo2026
Rôle : Admin
```

Comptes secondaires de la démo :

```text
demo.caisse / 060606
demo.stock / 060606
demo.commandes / 060606
```

## Tests automatiques réalisés

| Point testé | Résultat |
|---|---|
| Compilation Python de l'application | OK |
| Captures d'écran utilisateur régénérées | OK |
| Comptes démo séparés des comptes officiels | OK |
| Connexion `demo.admin / demo2026` | OK |
| Refus de `a.kayembe / 010203` dans la démo | OK |
| Blocage du montant reçu supérieur au montant à percevoir | OK |
| Contrôle cohérence sacs utilisés Production / Stock | OK |
| Génération rapport PDF journalier | OK |
| Génération rapport PDF mensuel | OK |
| Génération rapport PDF entre deux dates | OK |
| Génération rapport Excel journalier | OK |
| Génération rapport Excel mensuel | OK |
| Génération rapport Excel entre deux dates | OK |
| Présence des deux installateurs 1.3.5 | OK |

## Checklist de test sur PC client

À faire avant toute livraison définitive :

1. Installer la version officielle sur le poste serveur principal.
2. Installer la version officielle sur au moins un poste client.
3. Vérifier que le poste client détecte le serveur central automatiquement.
4. Se connecter avec un compte Admin, Caissier, Gestionnaire de stock et Gestionnaire des commandes.
5. Créer une commande normale et vérifier les calculs automatiques.
6. Essayer un montant reçu supérieur au montant à percevoir et vérifier que l'application bloque.
7. Enregistrer une sortie stock et une production cohérentes.
8. Tester l'incohérence sacs Production / Stock et vérifier que l'application affiche l'alerte.
9. Générer les rapports PDF et Excel.
10. Fermer et rouvrir l'application pour vérifier que le mode connecté reste actif.

## Décision

La version 1.3.5 peut être présentée et installée chez un client pilote, avec une période d'observation avant la vente définitive.
