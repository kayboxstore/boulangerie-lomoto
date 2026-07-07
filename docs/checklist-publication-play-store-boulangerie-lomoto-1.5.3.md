# Checklist de publication Play Store - Boulangerie Lomoto 1.5.3

Date de mise a jour : 2 juillet 2026  
Application : Boulangerie Lomoto  
Package Android : `com.gis.boulangerielomoto`  
Version : `1.5.3`  
Version code : `10503`

## Fichiers prets

- APK de production : `A:\Mon application python\installer\output\android\1.5.3\BoulangerieLomoto-1.5.3-release.apk`
- Android App Bundle Play Store : `A:\Mon application python\installer\output\android\1.5.3\BoulangerieLomoto-1.5.3-release.aab`
- Archive de publication : `A:\Mon application python\output\play-store-1.5.3\Boulangerie-Lomoto-Play-Store-1.5.3-20260702.zip`
- Icone Play Store : `A:\Mon application python\output\play-store-1.5.3\assets\icone-play-store-512.png`
- Image de presentation : `A:\Mon application python\output\play-store-1.5.3\assets\image-presentation-1024x500.png`
- Capture Android de connexion : `A:\Mon application python\output\play-store-1.5.3\screenshots\01-connexion.png`
- Capture Android du menu : `A:\Mon application python\output\play-store-1.5.3\screenshots\03-menu-modules.png`
- Fiche de publication : `A:\Mon application python\docs\fiche-publication-play-store-boulangerie-lomoto-1.5.3.md`
- Politique de confidentialite HTML : `A:\Mon application python\docs\politique-confidentialite-boulangerie-lomoto-1.5.3.html`
- Politique de confidentialite Markdown : `A:\Mon application python\docs\politique-confidentialite-boulangerie-lomoto-1.5.3.md`
- URL publique a utiliser sur Play Store : `https://boulangerie-lomoto.com/politique-confidentialite`

## Points techniques verifies

- Logo de Boulangerie Lomoto integre.
- Logo public et Android nettoye, sans damier.
- Cache PWA renouvele pour imposer le logo corrige.
- Barre Flutter retiree.
- Affichage Android corrige pour ne pas chevaucher la barre systeme.
- Google Password Manager autorise apres interaction volontaire avec le formulaire.
- Champs de connexion toujours vides a l'ouverture.
- Navigation mobile verrouillee contre le decalage horizontal global.
- Une coupure reseau temporaire ne ferme plus immediatement la session.
- Sauvegarde Android desactivee : `allowBackup=false`.
- Cleartext HTTP desactive : `usesCleartextTraffic=false`.
- Permission Internet presente.
- L'APK installe ouvre la version web officielle synchronisee avec Windows.
- L'identite Android est verrouillee sur `com.gis.boulangerielomoto`.
- L'URL embarquee est verrouillee sur `https://app.boulangerie-lomoto.com`.
- L'APK et l'AAB sont signes avec la cle de publication.
- Empreinte SHA-256 du certificat de signature : `30D6DEB45D557BEBA6A1C8944CD00F465B2457A166143D9AD5121109C269917F`.
- Certificat de signature valide jusqu'au 28 octobre 2053.
- Niveau Android cible : API 35, conforme aux exigences Google Play actuelles.
- Test reel sur Pixel 6 Pro : installation, lancement et champs de connexion OK.
- Ancien package `com.kayboxstore.boulangerielomoto` supprime du Pixel 6 Pro.
- Debogage USB Pixel 6 Pro : autorise.
- Icone Play Store 512 x 512 : prete.
- Image de presentation 1024 x 500 : prete.
- Capture de connexion Android 1440 x 3120 : prete.
- Capture du menu Android 1440 x 3120 : prete.
- Test hors Wi-Fi serveur : chargement par connexion LTE OK.
- Domaine public actif : `https://boulangerie-lomoto.com`.

## Informations a saisir dans Google Play Console

- Nom de l'application : Boulangerie Lomoto
- Description courte : Application interne de gestion commerciale pour Boulangerie Lomoto.
- Categorie : Business / Outils professionnels
- Public cible : utilisateurs professionnels autorises de Boulangerie Lomoto
- Publicites : non
- Achats integres : non
- Collecte de donnees : oui, donnees professionnelles necessaires a la gestion interne
- Partage ou vente de donnees : non
- Chiffrement en transit : oui
- Suppression des donnees : sur demande aupres de l'administrateur

## Actions a faire dans Google Play Console

1. Creer ou ouvrir le compte developpeur Google Play.
2. Creer l'application Boulangerie Lomoto.
3. Charger `BoulangerieLomoto-1.5.3-release.aab` dans une piste de test interne.
4. Ajouter la politique de confidentialite : `https://boulangerie-lomoto.com/politique-confidentialite`.
5. Remplir la section securite des donnees.
6. Ajouter les captures d'ecran telephone.
7. Ajouter l'icone Play Store 512 x 512 et l'image de presentation 1024 x 500.
8. Activer Play App Signing.
9. Tester l'installation depuis la piste interne.
10. Si le compte developpeur personnel a ete cree apres le 13 novembre 2023, ouvrir une piste de test ferme avec au moins 12 testeurs inscrits pendant 14 jours consecutifs.
11. Demander l'acces a la production apres la periode de test obligatoire, si elle s'applique au compte.
12. Passer ensuite en production si tout est valide.

## Points qui exigent une action manuelle du proprietaire du compte

- Paiement et validation du compte developpeur Google Play.
- Validation 2FA du compte Google.
- Activation de la 2FA du compte Cloudflare : terminee le 1 juillet 2026.
- Acceptation des declarations legales Google Play.
- Saisie des declarations "Securite des donnees" selon les donnees reellement utilisees.
- Ajouter d'autres captures metier sans donnees confidentielles seulement si Google Play en demande davantage.

## Recommandation

Publier d'abord en test interne, avec uniquement les appareils de Boulangerie Lomoto. La production publique ne doit etre lancee qu'apres validation complete sur telephone hors Wi-Fi serveur.
