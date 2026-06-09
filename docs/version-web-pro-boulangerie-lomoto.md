# Version web professionnelle - Boulangerie Lomoto

Cette version est une nouvelle base web, distincte de l'ancienne tentative `web-mobile-app`.

## Ce qui change

- Un seul serveur Python sert l'interface web et l'API.
- Le navigateur ne dépend plus de l'ancienne API RPC générique.
- Les endpoints sont organisés par module : commandes, caisse, stock, production, travailleurs, rapports, etc.
- Les sessions web sont gérées côté serveur avec des rôles.
- L'interface est responsive pour PC, tablette et téléphone.

## Lancement

Depuis la racine du projet :

```powershell
.\scripts\start-web-pro-boulangerie-lomoto.ps1
```

Adresse locale :

```text
http://127.0.0.1:8787
```

Identifiants admin par défaut :

- Identifiant : `a.kayembe`
- Mot de passe : `010203`

## Modules présents

- Tableau de bord
- Commandes
- Caisse
- Stock
- Production
- Commissions
- Travailleurs et paies
- Rapports imprimables
- Utilisateurs
- Historique

## Suite pour le domaine

Quand le domaine `boulangerie-lomoto.com` sera acheté, le scénario économique recommandé est :

- `boulangerie-lomoto.com` pour l'interface web.
- `api.boulangerie-lomoto.com` pour le serveur API si l'interface est séparée.
- Cloudflare Tunnel si le serveur reste sur le PC local.
- Hébergement cloud plus tard si on veut que l'application fonctionne même quand le PC local est éteint.
