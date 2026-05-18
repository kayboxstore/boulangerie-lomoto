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

## Résumé pratique

- poste principal : installé et démarre le service Windows
- postes clients : passent en `Mode connecté`
- toutes les modifications sont partagées en temps réel
