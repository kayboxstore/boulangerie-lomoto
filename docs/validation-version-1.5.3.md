# Rapport de recette complete - Boulangerie Lomoto 1.5.3

Date : 2026-07-02 08:25:45
Base temporaire : `A:\Mon application python\output\recette-lomoto-1.5.3-20260702-082500\data`
Serveur temporaire : `http://127.0.0.1:62196`

Resultat : **25 OK / 1 echec(s)**

| Statut | Scenario | Duree | Details |
|---|---|---:|---|
| OK | Compilation Python des modules principaux | 522 ms | compileall OK |
| OK | Sante du service installe local | 82 ms | Boulangerie Lomoto 1.5.3 |
| ECHEC | Sante du domaine public Cloudflare | 27 ms | URLError: <urlopen error [WinError 10013] Une tentative d’accès à un socket de manière interdite par ses autorisations d’accès a été tentée> |
| OK | Sante du serveur temporaire de recette | 1 ms | http://127.0.0.1:62196 \| data=A:\Mon application python\output\recette-lomoto-1.5.3-20260702-082500\data |
| OK | Maintenance locale protegee par jeton | 628 ms | jeton OK, sauvegarde=sauvegarde-automatique-20260702-082506.db |
| OK | Configuration initiale obligatoire sur base vide | 3 ms | setup requis sur base vide |
| OK | Creation de l'administrateur initial | 793 ms | admin.recette cree |
| OK | Connexion administrateur | 1620 ms | modules=13 |
| OK | Page de connexion sans identifiants pre-remplis | 24 ms | champs vides, gestionnaire de mots de passe autorise a la demande |
| OK | Tableau de bord administrateur | 159 ms | 18 indicateurs |
| OK | Creation des roles et unicite du Directeur General | 5676 ms | 6 utilisateurs, e-mail auto OK |
| OK | Acces par role et modules visibles | 8900 ms | DG lecture seule, profils metier OK |
| OK | Session unique et deconnexion forcee par Admin | 3456 ms | conflit 409 + deconnexion admin OK |
| OK | Production journaliere | 564 ms | 20 bacs produits, 2 sacs |
| OK | Stock : approvisionnement, sortie et parametres | 1470 ms | stock parametre, entree et sortie OK |
| OK | Commandes : mamans, depositaires, dette et avance | 2467 ms | avance 9 000 FC generee puis utilisee |
| OK | Filtres commandes Maman / Depositaire | 220 ms | Maman=1, Depositaire=2 |
| OK | Caisse journaliere | 657 ms | fiche caisse OK |
| OK | Travailleurs, anciennete et paie | 1166 ms | anciennete >= 1 an, net 92 500 FC |
| OK | Notifications e-mail mises en file d'attente | 162 ms | 7 message(s) en attente sans configuration e-mail |
| OK | Blocage des dates futures sur les modules | 835 ms | commandes/caisse/stock/production/travailleurs/rapports/cloture |
| OK | Rapports PDF et Excel | 4042 ms | PDF=rapport-journalier-20260702-082534.pdf, Excel=rapport-excel-periode-20260701-20260702-082537.xlsx |
| OK | Historique limite a 50 lignes cote API | 121 ms | 26 ligne(s) retournees |
| OK | Cloture DG, refus d'ecriture, reouverture Admin | 5171 ms | DG cloture, Admin reouvre, ecriture reprise |
| OK | Sauvegarde de la base temporaire | 697 ms | boulangerie-lomoto-backup-20260702-082544.db |
| OK | Effacement et archivage de l'historique | 614 ms | 30 supprimees, archive=historique-actions-20260702-082544.csv |

## Conclusion

Recette avec ecarts a corriger avant livraison finale.

Journal serveur temporaire : `A:\Mon application python\output\recette-lomoto-1.5.3-20260702-082500\serveur-temporaire.log`
Rapport JSON : `A:\Mon application python\output\recette-lomoto-1.5.3-20260702-082500\rapport-recette-lomoto-1.5.3.json`
