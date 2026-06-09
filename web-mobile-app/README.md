# Version web/mobile Boulangerie Lomoto

Cette version web est une application responsive utilisable sur PC, tablette et téléphone. Elle se connecte au serveur central Python existant via l'API `/rpc`, ce qui permet de garder la même base de données et la même logique métier que la version Windows.

## Lancement rapide pour présentation

Depuis la racine du projet :

```powershell
.\scripts\start-web-boulangerie-lomoto.ps1
```

Le script démarre :

- le serveur central local sur `http://127.0.0.1:8765` ;
- l'interface web Vite sur `http://127.0.0.1:5173` ;
- le navigateur automatiquement.

## Modules disponibles

- Tableau de bord avec indicateurs globaux.
- Stock : approvisionnements, sorties et alertes.
- Production : bacs produits, écart avec commandes et sacs utilisés.
- Commandes : calcul automatique du montant à percevoir et blocage du trop-perçu.
- Caisse : entrées, dettes payées, dépenses et solde.
- Commissions automatiques.
- Travailleurs et paies.
- Rapports imprimables/PDF côté navigateur.
- Utilisateurs, clôtures, historique et sauvegardes selon le rôle.

## Configuration

Par défaut, l'application utilise :

```env
VITE_API_URL=http://127.0.0.1:8765
VITE_API_TOKEN=
```

Pour un accès distant avec un nom de domaine comme `boulangerie-lomoto.com`, on publiera ensuite le serveur local avec Cloudflare Tunnel ou une API hébergée.

## Build production

```powershell
cd web-mobile-app
npm.cmd install
npm.cmd run build
```

Le dossier généré est `web-mobile-app/dist`.
