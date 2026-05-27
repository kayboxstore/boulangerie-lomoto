# Validation de la version 1.3.6

Date de validation : 27/05/2026

Application : Boulangerie Lomoto

Version testée : 1.3.6

## Résumé

La version 1.3.6 ajoute une protection importante pour le mode connecté.

Un poste configuré en mode connecté ne bascule plus silencieusement en mode local lorsque le serveur central est introuvable. L'application affiche un message clair pour éviter de créer des données séparées sur un poste client.

## Installateurs

- Version officielle : `installer/output/1.3.6/BoulangerieLomotoSetup.exe`
- Version démo : `installer/output/1.3.6-demo/BoulangerieLomotoDemoSetup.exe`

## Identifiants

Version officielle :

```text
Identifiant : a.kayembe
Mot de passe : 010203
Rôle : Admin
```

Version démo :

```text
Identifiant : demo.admin
Mot de passe : demo2026
Rôle : Admin
```

## Tests réalisés

| Point testé | Résultat |
|---|---|
| Compilation Python de l'application | OK |
| Poste configuré en mode connecté sans serveur disponible | OK, aucun retour automatique en local |
| Poste non configuré en mode connecté | OK, mode local autorisé |
| Message clair si serveur central introuvable | OK |
| Version démo séparée et locale | OK |

## Note réseau

Le mode connecté Windows fonctionne sur un réseau local interne. Si un poste client utilise une autre connexion Internet que le serveur principal, l'adresse locale du serveur ne sera pas accessible directement.

Pour un accès à distance, il faut prévoir une solution complémentaire : VPN, Tailscale, ZeroTier ou hébergement en ligne.
