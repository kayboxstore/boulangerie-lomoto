# Rapport de recette complete - Boulangerie Lomoto 1.5.1

Date : 2026-06-22 14:43:15
Base temporaire : `A:\Mon application python\output\recette-lomoto-1.5.1-20260622-144227\data`
Serveur temporaire : `http://127.0.0.1:65387`

Resultat : **25 OK / 0 echec(s)**

| Statut | Scenario | Duree | Details |
|---|---|---:|---|
| OK | Compilation Python des modules principaux | 140 ms | compileall OK |
| OK | Sante du service installe local | 54 ms | Boulangerie Lomoto 1.5.1 |
| OK | Sante du domaine public Cloudflare | 665 ms | Boulangerie Lomoto 1.5.1 |
| OK | Sante du serveur temporaire de recette | 2 ms | http://127.0.0.1:65387 \| data=A:\Mon application python\output\recette-lomoto-1.5.1-20260622-144227\data |
| OK | Configuration initiale obligatoire sur base vide | 5 ms | setup requis sur base vide |
| OK | Creation de l'administrateur initial | 920 ms | admin.recette cree |
| OK | Connexion administrateur | 1649 ms | modules=13 |
| OK | Page de connexion sans identifiants pre-remplis | 7 ms | anti-remplissage automatique actif |
| OK | Tableau de bord administrateur | 161 ms | 18 indicateurs |
| OK | Creation des roles et unicite du Directeur General | 6073 ms | 6 utilisateurs, e-mail auto OK |
| OK | Acces par role et modules visibles | 9004 ms | DG lecture seule, profils metier OK |
| OK | Session unique et deconnexion forcee par Admin | 3548 ms | conflit 409 + deconnexion admin OK |
| OK | Production journaliere | 591 ms | 20 bacs produits, 2 sacs |
| OK | Stock : approvisionnement, sortie et parametres | 1757 ms | stock parametre, entree et sortie OK |
| OK | Commandes : mamans, depositaires, dette et avance | 2614 ms | avance 9 000 FC generee puis utilisee |
| OK | Filtres commandes Maman / Depositaire | 279 ms | Maman=1, Depositaire=2 |
| OK | Caisse journaliere | 657 ms | fiche caisse OK |
| OK | Travailleurs, anciennete et paie | 1113 ms | anciennete >= 1 an, net 92 500 FC |
| OK | Notifications e-mail mises en file d'attente | 106 ms | 5 message(s) en attente sans configuration e-mail |
| OK | Blocage des dates futures sur les modules | 1743 ms | commandes/caisse/stock/production/travailleurs/rapports/cloture |
| OK | Rapports PDF et Excel | 5841 ms | PDF=rapport-journalier-20260622-144302.pdf, Excel=rapport-excel-periode-20260621-20260622-144306.xlsx |
| OK | Historique limite a 50 lignes cote API | 133 ms | 26 ligne(s) retournees |
| OK | Cloture DG, refus d'ecriture, reouverture Admin | 5929 ms | DG cloture, Admin reouvre, ecriture reprise |
| OK | Sauvegarde de la base temporaire | 784 ms | boulangerie-lomoto-backup-20260622-144314.db |
| OK | Effacement et archivage de l'historique | 599 ms | 30 supprimees, archive=historique-actions-20260622-144314.csv |

## Conclusion

Recette validee automatiquement.

Journal serveur temporaire : `A:\Mon application python\output\recette-lomoto-1.5.1-20260622-144227\serveur-temporaire.log`
Rapport JSON : `A:\Mon application python\output\recette-lomoto-1.5.1-20260622-144227\rapport-recette-lomoto-1.5.1.json`
