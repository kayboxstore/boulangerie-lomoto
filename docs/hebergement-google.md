# Hebergement Google - Boulangerie Lomoto

## Etat actuel

- Firebase Hosting est configure et publie la version web.
- Projet Google/Firebase : `kayboxstore-boulangerie-lomoto`.
- URL web : https://kayboxstore-boulangerie-lomoto.web.app
- La facturation Google Cloud est actuellement desactivee sur le projet.

Tant que `billing_enabled` vaut `False`, le risque de facture est nul, mais Cloud Run ne peut pas etre utilise correctement pour l'API centrale.

## Couts et securite

Firebase Hosting peut rester sur le plan Spark gratuit pour heberger le site.

Cloud Run fonctionne en pay-as-you-go avec quota gratuit. Il ne s'agit pas d'un abonnement fixe mensuel, mais Google peut facturer si l'usage depasse les limites gratuites ou si d'autres services payants sont actives.

Avant de lier une carte bancaire ou un compte de facturation, faire obligatoirement ceci :

- creer une alerte budget dans Google Cloud Billing ;
- garder Cloud Run avec `min-instances=0` ;
- limiter Cloud Run a `max-instances=1` ;
- utiliser la facturation a la requete ;
- surveiller la page Billing les premiers jours.

## Architecture recommandee

L'application Windows actuelle est une application Tkinter : elle ne peut pas etre hebergee directement comme un site web. Pour l'utiliser sur PC, telephone et a distance, il faut une version web/mobile qui parle avec une API centrale.

Architecture recommandee :

- `Frontend web responsive` : interface utilisable sur PC et telephone.
- `API centrale` : logique metier, securite, roles, rapports, synchronisation.
- `Base de donnees geree` : donnees centralisees et persistantes.
- `Cloud Run` : hebergement de l'API dans un conteneur.
- `Firebase Hosting` : hebergement de l'interface web avec lien public securise.
- `APK Android` : application mobile qui utilise la meme API centrale.

## Point important sur les donnees

Le serveur Cloud Run actuel peut servir pour un test technique, mais il utilise encore SQLite comme l'application Windows. Le stockage local Cloud Run n'est pas une base persistante fiable pour l'exploitation reelle.

Pour une vraie version distante, il faudra migrer les donnees vers une base geree comme Cloud SQL PostgreSQL ou Firestore. Cloud SQL est plus proche d'une vraie base relationnelle, mais il peut generer des couts. Firestore propose un quota gratuit plus simple, mais demande une adaptation plus importante de la logique.

## Liens officiels utiles

- Cloud Run : https://cloud.google.com/run/docs/deploying
- Tarifs Cloud Run : https://cloud.google.com/run/pricing
- Firebase Hosting et plans Firebase : https://firebase.google.com/docs/projects/billing/firebase-pricing-plans
- Budgets et alertes Google Cloud : https://cloud.google.com/billing/docs/how-to/budgets
