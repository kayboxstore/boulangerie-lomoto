# Rapport de recette complete - Boulangerie Lomoto 1.5.7

Date : 2026-07-17 18:54:29
Base temporaire : `A:\Mon application python\output\recette-lomoto-1.5.7-20260717-185325\data`
Serveur temporaire : `http://127.0.0.1:63271`

Resultat : **27 OK / 0 echec(s)**

| Statut | Scenario | Duree | Details |
|---|---|---:|---|
| OK | Compilation Python des modules principaux | 166 ms | compileall OK |
| OK | Sante du service installe local | 40 ms | Boulangerie Lomoto 1.5.6 |
| OK | Sante du domaine public Cloudflare | 591 ms | Boulangerie Lomoto 1.5.6 |
| OK | Sante du serveur temporaire de recette | 14 ms | http://127.0.0.1:63271 \| data=A:\Mon application python\output\recette-lomoto-1.5.7-20260717-185325\data |
| OK | Maintenance locale protegee par jeton | 409 ms | jeton OK, sauvegarde=sauvegarde-automatique-20260717-185330.db |
| OK | Configuration initiale obligatoire sur base vide | 4 ms | setup requis sur base vide |
| OK | Creation de l'administrateur initial | 733 ms | admin.recette cree |
| OK | Connexion administrateur | 1435 ms | modules=14 |
| OK | Page de connexion sans identifiants pre-remplis | 52 ms | champs vides, gestionnaire de mots de passe autorise a la demande |
| OK | Tableau de bord administrateur | 164 ms | 18 indicateurs |
| OK | Creation des roles et unicite du Directeur General | 5955 ms | 6 utilisateurs, e-mail auto OK |
| OK | Acces par role et modules visibles | 25201 ms | DG lecture seule, profils metier OK |
| OK | Session unique et deconnexion forcee par Admin | 3528 ms | conflit 409 + deconnexion admin OK |
| OK | Previsions futures et droits du profil production | 2071 ms | Web/Android : 2 lignes futures, droits par role et export Excel OK |
| OK | Production journaliere | 587 ms | 20 bacs produits, 2 sacs |
| OK | Stock : approvisionnement, sortie et parametres | 1688 ms | stock parametre, entree et sortie OK |
| OK | Commandes : mamans, depositaires, dette et avance | 2341 ms | avance 9 000 FC generee puis utilisee |
| OK | Filtres commandes Maman / Depositaire | 218 ms | Maman=1, Depositaire=2 |
| OK | Caisse journaliere | 712 ms | fiche caisse OK |
| OK | Travailleurs, anciennete et paie | 1213 ms | anciennete >= 1 an, net 92 500 FC |
| OK | Notifications e-mail mises en file d'attente | 106 ms | 12 message(s) en attente sans configuration e-mail |
| OK | Blocage des dates futures sur les modules | 1653 ms | commandes/caisse/stock/production/travailleurs/rapports/cloture |
| OK | Rapports PDF et Excel | 3662 ms | PDF=rapport-journalier-20260717-185419.pdf, Excel=rapport-excel-periode-20260716-20260717-185421.xlsx |
| OK | Historique limite a 50 lignes cote API | 133 ms | 39 ligne(s) retournees |
| OK | Cloture DG, refus d'ecriture, reouverture Admin | 5057 ms | DG cloture, Admin reouvre, ecriture reprise |
| OK | Sauvegarde de la base temporaire | 682 ms | boulangerie-lomoto-backup-20260717-185427.db |
| OK | Effacement et archivage de l'historique | 754 ms | 43 supprimees, archive=historique-actions-20260717-185428.csv |

## Conclusion

Recette validee automatiquement.

Journal serveur temporaire : `A:\Mon application python\output\recette-lomoto-1.5.7-20260717-185325\serveur-temporaire.log`
Rapport JSON : `A:\Mon application python\output\recette-lomoto-1.5.7-20260717-185325\rapport-recette-lomoto-1.5.7.json`
