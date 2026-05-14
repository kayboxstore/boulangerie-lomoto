# Guide du mode connecte

Ce mode permet a plusieurs postes d'utiliser les memes donnees en temps reel.

## Principe

- un poste joue le role de serveur central
- les autres postes se connectent a ce serveur
- toutes les donnees sont lues et ecrites sur la meme base centrale

## Methode la plus simple

### 1. Demarrer le serveur central sur le poste principal

Sur le poste principal :

1. Ouvrez l'application
2. Dans la fenetre de connexion, cliquez sur `Parametres reseau`
3. Cliquez sur `Demarrer le serveur sur ce poste`
4. Notez l'adresse affichee, par exemple :

```text
http://192.168.1.10:8765
```

Important :

- laissez l'application ouverte sur ce poste
- si vous fermez cette application, le serveur central s'arrete aussi

### 2. Connecter les autres postes

Sur chaque autre poste :

1. Ouvrez l'application
2. Cliquez sur `Parametres reseau`
3. Choisissez `Mode connecte au serveur central`
4. Cliquez d'abord sur `Rechercher automatiquement`
5. Si un seul serveur est trouve, son adresse sera remplie automatiquement
6. Sinon, collez l'adresse du serveur, par exemple :

```text
http://192.168.1.10:8765
```

7. Si vous utilisez un jeton, saisissez-le aussi
8. Cliquez sur `Tester la connexion`
9. Cliquez sur `Enregistrer`
10. Connectez-vous normalement

Alternative rapide :

- depuis l'ecran de connexion, le bouton `Detecter le serveur` permet aussi de retrouver automatiquement l'adresse du serveur central

## Variante avec serveur dedie

Si vous preferez demarrer le serveur hors de l'application :

```powershell
python serveur_central.py
```

Vous pouvez aussi choisir un autre port :

```powershell
python serveur_central.py --port 18765
```

Et un jeton d'acces :

```powershell
python serveur_central.py --token mon-jeton-secret
```

## Sauvegardes en mode connecte

Quand un poste est en mode connecte :

- les boutons de sauvegarde et restauration locale sont desactives
- les sauvegardes doivent etre faites sur le poste serveur central

## Rapports PDF en mode connecte

- les donnees viennent du serveur central
- les fichiers PDF restent enregistres localement sur le poste qui genere le rapport

## Reseau et pare-feu

Si les autres postes n'arrivent pas a se connecter :

- verifiez que les postes sont sur le meme reseau
- verifiez que le pare-feu Windows autorise le port `8765`
- testez l'adresse du serveur depuis un autre poste

## Resume pratique

- poste principal : demarre le serveur
- postes clients : passent en `Mode connecte`
- toutes les modifications sont partagees en temps reel
