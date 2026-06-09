# Etat de livraison 1.3.23

## Termine

- Application Windows et Web Pro alignees sur la version 1.3.23.
- Service central Windows automatique sur les ports 8765 et 8787.
- Base centrale conservee et sauvegardee avant mise a jour.
- Acces local PC : http://127.0.0.1:8787
- Acces Wi-Fi : http://192.168.1.225:8787
- Tunnel Cloudflare `boulangerie-lomoto-production` installe, actif et sain.
- Domaine cible : `boulangerie-lomoto.com`.
- Notifications de paie et de creation de compte placees en file et traitees immediatement quand le service e-mail est configure.
- Rapports PDF/Excel ouverts dans le navigateur apres generation.
- Liste des rapports disponible depuis la page Rapports.
- Installateur final : `installer/output/1.3.23/BoulangerieLomotoSetup.exe`.

## Actions Cloudflare restantes

1. Creer un jeton API Cloudflare limite au compte et au domaine avec :
   - Account / Cloudflare Tunnel / Edit
   - Zone / DNS / Edit
   - permission d'envoi d'e-mails Cloudflare Email Service
2. Definir temporairement `CLOUDFLARE_API_TOKEN` sur le PC serveur.
3. Lancer `scripts/configure_production_cloudflare.py`.
4. Verifier que les trois noms DNS ci-dessous pointent, en mode proxy Cloudflare, vers
   `bd4284d8-b7b9-4d58-89e2-cdbdc8c06d15.cfargotunnel.com` :

   - `boulangerie-lomoto.com`
   - `www.boulangerie-lomoto.com`
   - `app.boulangerie-lomoto.com`

5. Activer Email Sending pour `boulangerie-lomoto.com`.
6. Dans Utilisateurs > Envoi des e-mails, renseigner le jeton et l'expediteur
   `notifications@boulangerie-lomoto.com`.
7. Relancer les quatre notifications actuellement en attente.

Ces actions demandent un secret Cloudflare qui ne doit pas etre inscrit dans le code source.
