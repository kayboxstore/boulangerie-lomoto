# Rapport final de mise en production - Boulangerie Lomoto 1.5.3

Date : 2 juillet 2026  
Domaine : `https://boulangerie-lomoto.com`  
Editeur : General Investment Services (GIS)  
Responsable : Christian Lomoto  
Initiateur et support IT : Augustin Kayembe

## Etat general

La version Windows, la version web publique et l'APK Android sont alignees sur la version `1.5.3`.

La synchronisation entre Windows, Web et Android passe par le serveur central de Boulangerie Lomoto. Les donnees saisies sur une plateforme sont visibles par les autres plateformes, selon les droits du role connecte.

## Services de production verifies

| Element | Etat |
|---|---|
| Service Windows `BoulangerieLomotoCentralServer` | Actif, demarrage automatique |
| Service `cloudflared` | Actif, demarrage automatique |
| Sante locale | `http://127.0.0.1:8787/api/health` OK, version 1.5.3 |
| Sante publique | `https://boulangerie-lomoto.com/api/health` OK, version 1.5.3 |
| Domaine Cloudflare | Actif via Cloudflare Tunnel |
| Redirection de port routeur | Non utilisee |
| Recuperation du tunnel | Redemarrage automatique apres 3 echecs publics consecutifs |
| Politique de confidentialite publique | `https://boulangerie-lomoto.com/politique-confidentialite` active |

## Sauvegarde et maintenance

| Controle | Resultat |
|---|---|
| Sauvegarde automatique forcee | OK |
| Derniere sauvegarde testee | `sauvegarde-automatique-20260630-093432.db` |
| Test de restauration | OK |
| Integrite SQLite | `ok` |
| Tables restaurees | 20 |
| Sauvegarde externe | `D:\BoulangerieLomoto-Backups\BoulangerieLomoto\SauvegardesHebdomadaires\2026-06-29-200040` |
| Test de restauration externe | OK le 29 juin 2026 |
| Tache sauvegarde quotidienne | Presente, prete |
| Tache sauvegarde externe hebdomadaire | Presente, prete |
| Tache surveillance service | Presente, prete |

## E-mails

| Element | Etat |
|---|---|
| Fournisseur | Cloudflare Email Sending |
| Adresse d'envoi | `notifications@boulangerie-lomoto.com` |
| Adresse de reponse | `contact@boulangerie-lomoto.com` |
| Configuration application | Active |
| Test d'envoi | Recu par l'utilisateur |
| File d'attente apres relance | 0 en attente, 0 echec |
| SPF / DKIM / DMARC Cloudflare Sending | Publies |
| Quota API verifie | 200 e-mails / jour |

## Android

| Element | Etat |
|---|---|
| Package | `com.gis.boulangerielomoto` |
| Version name | `1.5.3` |
| Version code | `10503` |
| APK release | Genere |
| AAB Play Store | Genere |
| Installation sur telephone branche | OK |
| Appareil detecte | `19011FDEE004NP` |
| Ancien package `com.kayboxstore.boulangerielomoto` | Supprime du telephone |
| Logo Boulangerie Lomoto | Corrige, sans damier ni cache obsolete |
| Google Password Manager | Autorise apres interaction volontaire |
| Champs de connexion | Vides a l'ouverture |
| Session sur coupure temporaire | Conservee, nouvelle tentative au prochain heartbeat |
| Navigation mobile | Blocage du decalage horizontal global |
| Sauvegarde Android | Desactivee |
| HTTP non chiffre | Desactive |

## Fichiers de livraison

- Installateur Windows : `A:\Mon application python\installer\output\1.5.3\BoulangerieLomotoSetup.exe`
- APK Android : `A:\Mon application python\installer\output\android\1.5.3\BoulangerieLomoto-1.5.3-release.apk`
- AAB Play Store : `A:\Mon application python\installer\output\android\1.5.3\BoulangerieLomoto-1.5.3-release.aab`
- Paquet Play Store : `A:\Mon application python\output\play-store-1.5.3\Boulangerie-Lomoto-Play-Store-1.5.3-20260702.zip`
- Guide production/securite/exploitation : `A:\Mon application python\docs\Guide-production-securite-exploitation-Boulangerie-Lomoto-1.5.3.docx`
- Rapport de recette : `A:\Mon application python\output\recette-lomoto-1.5.3-20260701-110837\rapport-recette-lomoto-1.5.3.md`
- Validation version : `A:\Mon application python\docs\validation-version-1.5.3.md`
- Politique de confidentialite : `A:\Mon application python\docs\politique-confidentialite-boulangerie-lomoto-1.5.3.html`
- URL publique de confidentialite : `https://boulangerie-lomoto.com/politique-confidentialite`

## Empreintes de livraison

| Fichier | SHA-256 |
|---|---|
| `BoulangerieLomotoSetup.exe` | `A7DA1FDD5BAFB670D2AA76CC652581686C05A7450B584A251A8BB7D84F7D7C8B` |
| `BoulangerieLomoto-1.5.3-release.apk` | `D8DC6D88B657D86D1ADCA2F704514405037AAA745135D15B0C11B28175329421` |
| `BoulangerieLomoto-1.5.3-release.aab` | `0D964D2E3711B852F4B8B61A15CD5700FA46426CAEB81E9EB7C31E8566DC0E02` |
| `Boulangerie-Lomoto-Play-Store-1.5.3-20260702.zip` | `E2B2240505A3476616AEDAC57442616BAE735C4F2413B85ACA6949C321BF637B` |

## Recette fonctionnelle

La recette finale du 1 juillet a valide directement `26 scenarios sur 26`, y compris la sante du domaine public Cloudflare.

Le formulaire public a aussi ete controle au format mobile 390 x 844 : aucun identifiant pre-rempli et aucun debordement horizontal.

Les controles couvraient notamment :

- configuration initiale sur base vide ;
- creation de l'administrateur ;
- connexion sans identifiants pre-remplis ;
- acces par role ;
- session unique ;
- deconnexion forcee par Admin ;
- production ;
- stock ;
- commandes Maman / Depositaire ;
- dette et avance ;
- caisse ;
- travailleurs, anciennete et paie ;
- notifications e-mail ;
- blocage des dates futures ;
- rapports PDF et Excel ;
- historique ;
- cloture et reouverture ;
- sauvegarde ;
- effacement et archivage de l'historique.

## Points manuels restants

Les elements suivants exigent l'intervention du proprietaire des comptes et ne peuvent pas etre automatises depuis le code :

- activer la 2FA de l'adresse e-mail principale ;
- conserver les codes de recuperation hors du PC serveur ;
- creer ou finaliser le compte Google Play Developer ;
- charger le fichier `.aab` dans Google Play Console ;
- prendre les captures connectees des modules sans donnees confidentielles ;
- si le compte personnel a ete cree apres le 13 novembre 2023, maintenir au moins 12 testeurs dans une piste fermee pendant 14 jours consecutifs ;
- remplir les declarations legales Google Play.

La 2FA Cloudflare est active depuis le 1 juillet 2026. L'icone Play Store 512 x 512, l'image de presentation 1024 x 500 et la capture de connexion Android sont pretes.

## Recommandation finale

La production Lomoto est techniquement prete. La sauvegarde externe et le test hors Wi-Fi ont ete realises. La publication Play Store depend maintenant des actions manuelles du proprietaire du compte.
