# Rapport de recette complete - Boulangerie Lomoto 1.5.6

Date : 2026-07-17 18:11:46
Base temporaire : `A:\Mon application python\output\recette-lomoto-1.5.6-20260717-181043\data`
Serveur temporaire : `http://127.0.0.1:49541`

Resultat : **27 OK / 0 echec(s)**

| Statut | Scenario | Duree | Details |
|---|---|---:|---|
| OK | Compilation Python des modules principaux | 145 ms | compileall OK |
| OK | Sante du service installe local | 39 ms | Boulangerie Lomoto 1.5.6 |
| OK | Sante du domaine public Cloudflare | 725 ms | Boulangerie Lomoto 1.5.6 |
| OK | Sante du serveur temporaire de recette | 2 ms | http://127.0.0.1:49541 \| data=A:\Mon application python\output\recette-lomoto-1.5.6-20260717-181043\data |
| OK | Maintenance locale protegee par jeton | 402 ms | jeton OK, sauvegarde=sauvegarde-automatique-20260717-181048.db |
| OK | Configuration initiale obligatoire sur base vide | 3 ms | setup requis sur base vide |
| OK | Creation de l'administrateur initial | 843 ms | admin.recette cree |
| OK | Connexion administrateur | 1681 ms | modules=13 |
| OK | Page de connexion sans identifiants pre-remplis | 20 ms | champs vides, gestionnaire de mots de passe autorise a la demande |
| OK | Tableau de bord administrateur | 203 ms | 18 indicateurs |
| OK | Creation des roles et unicite du Directeur General | 5879 ms | 6 utilisateurs, e-mail auto OK |
| OK | Acces par role et modules visibles | 25582 ms | DG lecture seule, profils metier OK |
| OK | Session unique et deconnexion forcee par Admin | 3687 ms | conflit 409 + deconnexion admin OK |
| OK | Previsions futures et droits du profil production | 1395 ms | 2 lignes futures, 11 articles, 12 000 FC, export Excel OK |
| OK | Production journaliere | 679 ms | 20 bacs produits, 2 sacs |
| OK | Stock : approvisionnement, sortie et parametres | 1488 ms | stock parametre, entree et sortie OK |
| OK | Commandes : mamans, depositaires, dette et avance | 2418 ms | avance 9 000 FC generee puis utilisee |
| OK | Filtres commandes Maman / Depositaire | 252 ms | Maman=1, Depositaire=2 |
| OK | Caisse journaliere | 766 ms | fiche caisse OK |
| OK | Travailleurs, anciennete et paie | 1135 ms | anciennete >= 1 an, net 92 500 FC |
| OK | Notifications e-mail mises en file d'attente | 118 ms | 12 message(s) en attente sans configuration e-mail |
| OK | Blocage des dates futures sur les modules | 1536 ms | commandes/caisse/stock/production/travailleurs/rapports/cloture |
| OK | Rapports PDF et Excel | 3894 ms | PDF=rapport-journalier-20260717-181136.pdf, Excel=rapport-excel-periode-20260716-20260717-181139.xlsx |
| OK | Historique limite a 50 lignes cote API | 134 ms | 36 ligne(s) retournees |
| OK | Cloture DG, refus d'ecriture, reouverture Admin | 5163 ms | DG cloture, Admin reouvre, ecriture reprise |
| OK | Sauvegarde de la base temporaire | 672 ms | boulangerie-lomoto-backup-20260717-181145.db |
| OK | Effacement et archivage de l'historique | 560 ms | 40 supprimees, archive=historique-actions-20260717-181146.csv |

## Conclusion

Recette validee automatiquement.

Journal serveur temporaire : `A:\Mon application python\output\recette-lomoto-1.5.6-20260717-181043\serveur-temporaire.log`
Rapport JSON : `A:\Mon application python\output\recette-lomoto-1.5.6-20260717-181043\rapport-recette-lomoto-1.5.6.json`
