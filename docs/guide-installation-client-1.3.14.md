# Guide d'installation client - Boulangerie Lomoto 1.3.14

Ce guide sert à installer et contrôler l'application chez un client.

## 1. Installer le poste serveur

1. Installer `BoulangerieLomotoSetup.exe` sur le PC principal.
2. Ouvrir l'application.
3. Se connecter avec le compte administrateur :
   - Identifiant : `a.kayembe`
   - Mot de passe : `010203`
4. Aller dans `Paramètres réseau`.
5. Cliquer sur `Installer / mettre à jour le service`.
6. Cliquer sur `Démarrer le service`.
7. Cliquer sur `Utiliser l'adresse locale du serveur`.
8. Cliquer sur `Tester la connexion`.
9. Cliquer sur `Enregistrer`.

Important : le PC serveur doit rester allumé pour que les postes clients travaillent sur la même base.

## 2. Installer les postes clients

1. Installer `BoulangerieLomotoSetup.exe` sur chaque poste client.
2. Ouvrir l'application.
3. Se connecter avec le compte de l'utilisateur.
4. L'application doit détecter automatiquement le serveur central.
5. Si la détection ne répond pas, ouvrir `Paramètres réseau`, cliquer sur `Détecter le serveur`, puis enregistrer.

Ne pas utiliser `127.0.0.1` sur un poste client. Cette adresse signifie toujours "ce même ordinateur".

## 3. Vérifier les droits des rôles

À tester après installation :

| Rôle | Résultat attendu |
| --- | --- |
| Admin | Tous les modules sont visibles, y compris `Travailleurs`, sauvegarde et restauration. |
| Caissier | `Caisse`, commandes en consultation selon les règles prévues, commissions, rapports de caisse et `Travailleurs` sont accessibles. |
| Gestionnaire des commandes | Les modules de commandes et production sont accessibles, mais `Travailleurs` est masqué. |
| Gestionnaire de stock | Le module stock est accessible, mais `Travailleurs` est masqué. |

## 4. Vérifier les rapports

1. Se connecter comme caissier.
2. Ouvrir les rapports.
3. Générer un rapport PDF journalier.
4. Générer un rapport Excel journalier.
5. Vérifier que le rapport du caissier contient la partie `Travailleurs et paies`.
6. Vérifier que le rapport du gestionnaire de stock ne contient que le stock.
7. Vérifier que le rapport du gestionnaire des commandes ne contient pas la caisse ni les travailleurs.

## 5. Vérifier les sauvegardes

Sur le poste serveur :

1. Se connecter comme administrateur.
2. Cliquer sur `Créer une sauvegarde`.
3. Vérifier que le fichier `.db` est créé.
4. Ouvrir le dossier des sauvegardes.
5. Ne restaurer une sauvegarde qu'après confirmation du responsable, car la restauration remplace les données actuelles.

## 6. Vérifier le mode connecté

Sur deux postes différents :

1. Créer ou modifier une donnée sur le poste serveur.
2. Ouvrir le même module sur le poste client.
3. Vérifier que la donnée apparaît.
4. Faire une modification autorisée sur le poste client.
5. Vérifier que le poste serveur voit la modification.

Si ça ne fonctionne pas :

- vérifier que le PC serveur est allumé ;
- vérifier que le service Windows est démarré ;
- vérifier que les postes sont sur le même réseau local ;
- vérifier que le pare-feu autorise le port `8765` ;
- relancer `Détecter le serveur` depuis `Paramètres réseau`.

## 7. Remise au client

À remettre au client :

- le setup officiel `BoulangerieLomotoSetup.exe` ;
- le compte administrateur initial ;
- ce guide ;
- une consigne claire : changer le mot de passe administrateur après installation ;
- une consigne claire : faire une sauvegarde avant toute restauration ou intervention importante.
