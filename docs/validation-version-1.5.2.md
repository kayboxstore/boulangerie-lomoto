# Rapport de recette complete - Boulangerie Lomoto 1.5.2

Date : 2026-06-22 14:53:19
Base temporaire : `A:\Mon application python\output\recette-lomoto-1.5.2-20260622-145231\data`
Serveur temporaire : `http://127.0.0.1:51403`

Resultat : **25 OK / 0 echec(s)**

| Statut | Scenario | Duree | Details |
|---|---|---:|---|
| OK | Compilation Python des modules principaux | 127 ms | compileall OK |
| OK | Sante du service installe local | 36 ms | Boulangerie Lomoto 1.5.2 |
| OK | Sante du domaine public Cloudflare | 453 ms | Boulangerie Lomoto 1.5.2 |
| OK | Sante du serveur temporaire de recette | 19 ms | http://127.0.0.1:51403 \| data=A:\Mon application python\output\recette-lomoto-1.5.2-20260622-145231\data |
| OK | Configuration initiale obligatoire sur base vide | 5 ms | setup requis sur base vide |
| OK | Creation de l'administrateur initial | 880 ms | admin.recette cree |
| OK | Connexion administrateur | 1490 ms | modules=13 |
| OK | Page de connexion sans identifiants pre-remplis | 11 ms | anti-remplissage automatique actif |
| OK | Tableau de bord administrateur | 156 ms | 18 indicateurs |
| OK | Creation des roles et unicite du Directeur General | 6013 ms | 6 utilisateurs, e-mail auto OK |
| OK | Acces par role et modules visibles | 9200 ms | DG lecture seule, profils metier OK |
| OK | Session unique et deconnexion forcee par Admin | 3459 ms | conflit 409 + deconnexion admin OK |
| OK | Production journaliere | 818 ms | 20 bacs produits, 2 sacs |
| OK | Stock : approvisionnement, sortie et parametres | 1553 ms | stock parametre, entree et sortie OK |
| OK | Commandes : mamans, depositaires, dette et avance | 2882 ms | avance 9 000 FC generee puis utilisee |
| OK | Filtres commandes Maman / Depositaire | 260 ms | Maman=1, Depositaire=2 |
| OK | Caisse journaliere | 661 ms | fiche caisse OK |
| OK | Travailleurs, anciennete et paie | 1158 ms | anciennete >= 1 an, net 92 500 FC |
| OK | Notifications e-mail mises en file d'attente | 117 ms | 7 message(s) en attente sans configuration e-mail |
| OK | Blocage des dates futures sur les modules | 1556 ms | commandes/caisse/stock/production/travailleurs/rapports/cloture |
| OK | Rapports PDF et Excel | 5497 ms | PDF=rapport-journalier-20260622-145305.pdf, Excel=rapport-excel-periode-20260621-20260622-145309.xlsx |
| OK | Historique limite a 50 lignes cote API | 111 ms | 26 ligne(s) retournees |
| OK | Cloture DG, refus d'ecriture, reouverture Admin | 6863 ms | DG cloture, Admin reouvre, ecriture reprise |
| OK | Sauvegarde de la base temporaire | 910 ms | boulangerie-lomoto-backup-20260622-145318.db |
| OK | Effacement et archivage de l'historique | 702 ms | 30 supprimees, archive=historique-actions-20260622-145319.csv |

## Conclusion

Recette validee automatiquement.

Journal serveur temporaire : `A:\Mon application python\output\recette-lomoto-1.5.2-20260622-145231\serveur-temporaire.log`
Rapport JSON : `A:\Mon application python\output\recette-lomoto-1.5.2-20260622-145231\rapport-recette-lomoto-1.5.2.json`
