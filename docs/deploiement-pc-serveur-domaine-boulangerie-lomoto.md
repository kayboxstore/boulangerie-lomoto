# Déploiement avec PC serveur et domaine

Objectif : utiliser le PC principal comme serveur web, sans forfait serveur mensuel, avec accès public via `boulangerie-lomoto.com`.

## Principe

- Le PC principal héberge la version web professionnelle.
- Cloudflare Tunnel publie le site sans ouvrir de ports sur le routeur.
- Le domaine `boulangerie-lomoto.com` pointe vers Cloudflare.
- Les utilisateurs ouvrent le site depuis un navigateur : PC, tablette ou téléphone.

Limite : si le PC est éteint, sans courant ou sans Internet, le site est inaccessible.

## Coûts

- Nom de domaine : paiement annuel.
- Serveur cloud : aucun, si le PC reste le serveur.
- Cloudflare Tunnel : utilisable sans forfait serveur pour ce scénario de base.
- Coûts indirects : électricité, connexion Internet, onduleur recommandé.

## Préparation locale

Depuis la racine du projet :

```powershell
powershell.exe -ExecutionPolicy Bypass -File "A:\Mon application python\scripts\start-public-web-server-boulangerie-lomoto.ps1"
```

Test local :

```text
http://127.0.0.1:8787
```

Identifiants admin :

- `a.kayembe`
- `010203`

## Étapes Cloudflare

1. Acheter ou connecter le domaine `boulangerie-lomoto.com` à Cloudflare.
2. Installer `cloudflared` sur le PC serveur.
3. Se connecter :

```powershell
cloudflared tunnel login
```

4. Créer le tunnel :

```powershell
cloudflared tunnel create boulangerie-lomoto
```

5. Copier l'identifiant du tunnel dans :

```text
deploy\cloudflare-tunnel-boulangerie-lomoto.example.yml
```

6. Renommer ce fichier en `config.yml`, puis le placer dans le dossier attendu par Cloudflare, généralement :

```text
C:\Users\AIO\.cloudflared\config.yml
```

7. Créer les routes DNS :

```powershell
cloudflared tunnel route dns boulangerie-lomoto boulangerie-lomoto.com
cloudflared tunnel route dns boulangerie-lomoto www.boulangerie-lomoto.com
```

8. Lancer le tunnel :

```powershell
cloudflared tunnel run boulangerie-lomoto
```

9. Ouvrir :

```text
https://boulangerie-lomoto.com
```

## Installation comme service Windows

Quand le test manuel fonctionne :

```powershell
cloudflared service install
```

Ensuite, configurer le serveur web professionnel pour démarrer automatiquement au lancement de Windows. Cette partie peut être faite avec le Planificateur de tâches Windows.

## Sauvegardes obligatoires

Le PC devient le serveur officiel. Il faut donc prévoir :

- sauvegarde quotidienne de la base ;
- copie automatique vers un disque externe ou Google Drive/OneDrive ;
- test de restauration au moins une fois par mois ;
- onduleur recommandé.

## Checklist de validation

- Le site s'ouvre en local sur `http://127.0.0.1:8787`.
- La connexion admin fonctionne.
- Le domaine `https://boulangerie-lomoto.com` s'ouvre depuis un autre téléphone/PC.
- Les modules principaux chargent les données.
- Une commande test peut être enregistrée.
- Un rapport peut être imprimé en PDF.
- Le PC redémarre et le site revient automatiquement.
