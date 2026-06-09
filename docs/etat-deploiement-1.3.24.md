# Etat du deploiement 1.3.24

Date de validation : 6 juin 2026

## Adresses publiques

- https://app.boulangerie-lomoto.com
- https://boulangerie-lomoto.com
- https://www.boulangerie-lomoto.com

Les trois adresses sont reliees au tunnel Cloudflare
`boulangerie-lomoto-production`.

## Controles valides

- DNS public propage.
- Certificat HTTPS Cloudflare valide.
- Redirection permanente HTTP vers HTTPS.
- Service Windows central en demarrage automatique.
- Service Cloudflare Tunnel en demarrage automatique.
- Connexion utilisateur distante fonctionnelle.
- Tableau de bord et donnees existantes accessibles.
- Version Windows et Web Pro : 1.3.24.
- Manifest PWA et service worker disponibles.
- En-tetes de securite HTTPS, anti-cadrage et CSP actifs.

## Sauvegarde avant mise a jour

`C:\ProgramData\BoulangerieLomoto\central-server-data\sauvegardes\boulangerie-lomoto-backup-20260606-122058.db`

## Installateur

`installer/output/1.3.24/BoulangerieLomotoSetup.exe`

SHA-256 :
`2EC121AF74ABFE12049E52696A13647692E2FE5A0584320E057CC0CB6D5E6A99`

## En attente

L'envoi automatique des e-mails est volontairement reporte. Les notifications
restent dans la file locale et pourront etre relancees apres configuration du
fournisseur d'e-mails.
