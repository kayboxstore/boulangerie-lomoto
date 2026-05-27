# Guide du mode connecté

Ce mode permet à plusieurs postes d'utiliser les mêmes données en temps réel.

## Principe

- un poste joue le role de serveur central
- les autres postes se connectént a ce serveur
- toutes les données sont lues et écrites sur la même base centrale

## Méthode recommandée : service Windows sur le poste serveur

### 1. Installer le service Windows sur le poste principal

Sur le poste principal :

1. Ouvrez l'application
2. Dans la fenêtre de connexion, cliquez sur `Paramètres réseau`
3. Cliquez sur `Installer / mettre à jour le service`
4. Cliquez sur `Démarrer le service`
5. Cliquez sur `Utiliser l'adresse locale du serveur`
6. Notez l'adresse affichee, par exemple :

```text
http://192.168.1.10:8765
```

Important :

- ces actions demandent les droits administrateur Windows sur le poste serveur
- le service continue de tourner même si vous fermez l'application
- l'application ouvre maintenant automatiquement le pare-feu Windows pour le port du serveur et la détection réseau
- le dossier central du serveur est :

```text
C:\ProgramData\BoulangerieLomoto\central-server-data
```

### 2. Connecter les autres postes

Sur chaque autre poste :

1. Ouvrez l'application
2. Connectez-vous normalement avec le compte voulu
3. Si c'est un compte simple comme `Caissier`, `Gestionnaire de stock` ou `Gestionnaire des commandes`, l'application cherche automatiquement le serveur principal
4. Si un seul serveur est trouvé, l'adresse est utilisée automatiquement
5. Sinon, vous pouvez toujours ouvrir `Paramètres réseau` pour choisir ou corriger manuellement l'adresse
6. Exemple d'adresse détectée :

```text
http://192.168.1.10:8765
```

Important :

- n'utilisez pas `127.0.0.1` sur les autres postes
- les postes clients doivent utiliser la vraie adresse IP du poste serveur sur le réseau local

7. Si vous utilisez un jeton, saisissez-le aussi
8. Cliquez sur `Tester la connexion`
9. Cliquez sur `Enregistrer`

Comportement automatique :

- si vous ouvrez l'application sur le poste principal avec un compte `Admin`, l'application se branche directement sur le serveur principal
- si vous ouvrez l'application sur un poste client avec un compte simple, l'application se comporte comme client et récupère automatiquement l'adresse du serveur principal
- depuis l'écran de connexion, le bouton `Détecter le serveur` permet toujours de relancer la recherche manuellement

## Variante temporaire

Si vous voulez juste tester rapidement sans installer de service Windows :

1. Ouvrez `Paramètres réseau`
2. Cliquez sur `Démarrer le serveur sur ce poste`
3. Laissez l'application ouverte sur ce poste

Attention :

- si vous fermez l'application, le serveur s'arrête
- pour un vrai poste serveur quotidien, utilisez plutôt le service Windows

## Variante en ligne de commande

Si vous préférez démarrer le serveur manuellement hors de l'application :

```powershell
python serveur_central.py
```

Vous pouvez aussi choisir un autre port :

```powershell
python serveur_central.py --port 18765
```

Et un jeton d'accès :

```powershell
python serveur_central.py --token mon-jeton-secret
```

## Sauvegardes en mode connecté

Quand un poste est en mode connecté :

- un admin peut lancer les sauvegardes et restaurations du serveur central depuis l'application
- les autres rôles n'ont pas accès à ces actions
- le bouton `Voir les sauvegardes du serveur` affiche la liste des sauvegardes centrales

## Rapports PDF en mode connecté

- les données viennent du serveur central
- les fichiers PDF restent enregistres localement sur le poste qui génère le rapport

## Réseau et pare-feu

Si les autres postes n'arrivent pas a se connectér :

- vérifiez que les postes sont sur le même réseau
- vérifiez que le pare-feu Windows autorise le port `8765`
- testez l'adresse du serveur depuis un autre poste

## Si le serveur central est introuvable

À partir de la version `1.3.6`, un poste configuré en mode connecté ne bascule plus silencieusement en mode local.

Si le serveur central est introuvable, l'application affiche un message clair et bloque la connexion locale automatique. Cela évite de créer des données séparées sur un poste client.

À vérifier dans ce cas :

- le poste serveur principal est allumé ;
- le service Windows du serveur central est démarré ;
- le poste client et le poste serveur utilisent le même réseau local ;
- le pare-feu Windows autorise le port `8765` en TCP ;
- le bouton `Détecter le serveur` retrouve bien le serveur central.

Si le poste client utilise une autre connexion Internet, une autre box, la 4G ou un autre site, l'adresse locale du serveur ne sera pas accessible directement.

À partir de la version `1.3.7`, l'application peut récupérer automatiquement une adresse Internet publique du serveur central.

Le fichier utilisé est :

`https://raw.githubusercontent.com/kayboxstore/boulangerie-lomoto-updates/main/server.json`

Ordre de connexion :

1. L'application cherche d'abord un serveur local sur le poste serveur/admin.
2. Elle réutilise ensuite l'adresse déjà enregistrée sur le poste client.
3. Elle récupère l'adresse Internet publiée dans `server.json`.
4. Elle cherche enfin un serveur sur le réseau local.
5. Si aucun serveur central n'est joignable, elle refuse de basculer en local pour éviter les données séparées.

Important : l'adresse publiée doit pointer vers le vrai serveur central. Si elle pointe vers Cloud Run, les données utilisées seront celles du serveur Cloud Run. Si vous voulez utiliser exactement les données du PC serveur local depuis Internet, il faut publier ce PC avec un tunnel sécurisé ou migrer la base centrale vers une base cloud persistante.

## Résumé pratique

- poste principal : installé et démarre le service Windows
- postes clients : passent en `Mode connecté`
- toutes les modifications sont partagées en temps réel
