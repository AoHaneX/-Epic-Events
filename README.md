# Epic Events CRM

Application Python en ligne de commande avec authentification, permissions
et journalisation Sentry. SQLAlchemy 2 relie les sept tables MySQL :
`employees` et ses trois spécialisations `managers`, `sales_employees`,
`support_employees` (héritage), puis `clients`, `contracts` et `events`.

## Installation sous PowerShell

Prérequis : Python 3.10 ou supérieur et un serveur MySQL 8.0 ou supérieur
(les modèles utilisent la collation `utf8mb4_0900_ai_ci`).
Depuis le dossier du projet :

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Dans `.env`, renseigner `DB_PASSWORD` et `JWT_SECRET`.
Consulter `README_AUTH.md` pour générer le secret et utiliser les commandes
d'authentification.

Ne jamais envoyer le fichier `.env` sur GitHub. Il est déjà présent dans
`.gitignore`.

## Préparer MySQL

Pour une installation locale neuve, ouvrir le client MySQL avec un compte
administrateur (`mysql -u root -p`, si ce compte existe sur ton installation),
puis exécuter le SQL suivant. Remplacer le mot de passe d'exemple par une
valeur personnelle avant exécution ; ne pas enregistrer cette valeur dans Git.

```sql
CREATE DATABASE epic_events CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER 'epic_events_app'@'localhost' IDENTIFIED BY 'REMPLACER_PAR_UN_MOT_DE_PASSE';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, REFERENCES
ON epic_events.* TO 'epic_events_app'@'localhost';
```

Si la base ou le compte existe déjà, réutiliser la configuration existante.
Dans `.env`, vérifier `DB_USER=epic_events_app`, `DB_HOST=localhost`,
`DB_PORT=3306`, `DB_NAME=epic_events` et renseigner le même `DB_PASSWORD`.
Le compte applicatif est limité à cette base et ne possède aucun droit
d'administration des comptes MySQL.

## Initialiser et démarrer

```powershell
python -m app.main
```

Le programme crée les tables manquantes ; un second lancement conserve les
données existantes. Il affiche une connexion réussie, la base `epic_events`
et les sept tables.

Les rôles ne sont plus des lignes d'une table `roles` : chaque département
est une classe qui hérite de `Employee` (`Manager`, `SalesEmployee`,
`SupportEmployee`), avec sa propre table. La colonne `employees.role` indique
la spécialité. Une base créée avec une version précédente (table `roles`,
colonne `role_id`) doit être recréée : `create_all()` ne modifie pas une
table existante.
`Base.metadata.create_all()` crée les tables manquantes mais ne
met pas à jour une table existante. Les futures évolutions du schéma devront
être gérées avec Alembic.

Une fois l'initialisation réussie, le compte administrateur MySQL peut retirer
les droits de création au compte applicatif :

```sql
REVOKE CREATE, REFERENCES ON epic_events.* FROM 'epic_events_app'@'localhost';
```

Réattribuer ces droits avant une initialisation qui doit créer de nouvelles
tables. Générer le secret JWT selon [README_AUTH.md](README_AUTH.md), puis :

```powershell
python epicevents.py create-manager
python epicevents.py login
python epicevents.py status
```

`create-manager` demande le nom, l'email et le mot de passe du premier
collaborateur ; il exige une table `employees` vide.
Le [schéma de la base de données](docs/database-schema.md) détaille les cinq
tables, leurs relations et contraintes ([image](docs/database-schema.png)) ;
le [schéma d'architecture](docs/mermaid-diagram.png) montre l'enchaînement des
modules d'authentification.

## Organisation

```text
app/database.py  configuration de SQLAlchemy et des sessions
app/models.py    Employee et ses sous-classes Manager, SalesEmployee,
                 SupportEmployee ; Client, Contract et Event
app/main.py      création des tables manquantes, vérification MySQL
```

## Services et commandes métier

Chaque entité dispose d'un seul module dans `app/services/` et dans
`app/commands/` : `employees.py`, `clients.py`, `contracts.py`, `events.py`.
Les services d'écriture reçoivent le collaborateur authentifié, valident les
futures valeurs, puis appellent `flush()`. Les commandes récupèrent ce
collaborateur via `get_current_user()` et contrôlent le commit ou le rollback
avec `SessionLocal.begin()`.

```powershell
python epicevents.py login
python epicevents.py employees list
python epicevents.py employees create
python epicevents.py employees update 7 --full-name "Nouveau nom" --role-code SUPPORT
python epicevents.py employees password 7
python epicevents.py employees deactivate 7
python epicevents.py clients list
python epicevents.py clients create
python epicevents.py clients update 10 --phone "+33 6 12 34 56 78" --last-contact-at 2026-11-05T14:00
python epicevents.py contracts list --unsigned --unpaid
python epicevents.py contracts create
python epicevents.py contracts update 100 --client-id 20 --total-amount 1500 --remaining-amount 500
python epicevents.py events list --without-support
python epicevents.py events create
python epicevents.py events update 1000 --support-contact-id 3
python epicevents.py events update 1000 --support-contact-id none
```

Les identifiants sont des exemples à remplacer. Les commandes d'écriture
modifient la base configurée : utiliser une base de développement pour les
essais. La création demande les champs omis ; la modification accepte les
champs via options et demande l'identifiant s'il est absent. Consulter
`python epicevents.py events update --help`, par exemple.

Un champ omis conserve sa valeur. `none` efface un champ nullable :
`--signed-at none`, `--support-contact-id none`, `--notes none`,
`--last-contact-at none`,
`--contact-name none`, `--contact-email none`, `--contact-phone none`.
Les relations obligatoires client/contrat ne peuvent pas être retirées.
Un contact email ou téléphone reste obligatoire pour un événement.
Les dates utilisent `AAAA-MM-JJTHH:MM`, sans fuseau horaire ; les montants
utilisent un point et au maximum deux décimales.

```powershell
python epicevents.py contracts update 100 --signed --signed-at 2026-10-10T10:00
python epicevents.py contracts update 100 --no-signed --signed-at none
python epicevents.py events list --mine
python epicevents.py events update 1000 --location "Salle B" --attendees-count 80 --notes none
python epicevents.py events update 1000 --contract-id 200
```

### Permissions

| Action | Autorisation |
| --- | --- |
| Lire clients, contrats, événements | Tout collaborateur actif |
| Gérer et lister les collaborateurs | Management |
| Créer un client | Commercial ; le client lui est automatiquement associé |
| Modifier un client | Commercial responsable de ce client uniquement |
| Changer le rôle d'un collaborateur | Management ; refusé tant qu'un commercial suit des clients ou qu'un support a des événements |
| Changer un mot de passe | Son propre compte actif, ou Management |
| Créer un contrat | Management uniquement |
| Modifier un contrat | Management, ou commercial du client actuel |
| Changer le client d'un contrat | Même règle sur le nouveau client ; un commercial reste limité à ses clients |
| Créer un événement | Commercial du client, contrat signé sans événement |
| Modifier les informations d'un événement | Support affecté à cet événement |
| Attribuer ou retirer le support | Management ; support actif uniquement |
| Remplacer le contrat d'un événement | Management ; nouveau contrat signé sans autre événement |

La création des contrats reste réservée à Management, conformément à la règle
existante. Les README ne demandent pas d'autoriser Sales. La nouvelle règle
de remplacement du contrat d'un événement est limitée à Management ; une
éventuelle ouverture à Sales doit être confirmée métier. Management ne peut
pas modifier les informations générales réservées au Support.

`create-manager`, `create-employee`, `list-clients`, `list-contracts` et
`list-events` restent des alias de l'entrée `epicevents.py`.
Les anciens modules Python de commandes par action sont remplacés par les
modules par entité ; les anciens chemins `python -m app.commands.list_*`
et `python -m app.commands.create_*` ne sont plus pris en charge.
Les fonctions inutilisées `get_all_clients`, `get_all_contracts`,
`get_all_events` sont remplacées par les fonctions `list_*` authentifiées.

### Vérifications isolées

```powershell
python -m unittest discover -s tests -v
python -m compileall -q app tests epicevents.py
```

Les tests utilisent SQLite en mémoire et des sessions JWT temporaires,
neutralisent la lecture de `.env` et ne se connectent pas à MySQL.
La compilation test de `BIGINT` en `INTEGER` fournit l'autoincrément SQLite,
sans modifier les modèles MySQL. Les verrous et les écritures concurrentes
doivent encore être vérifiés sur un MySQL de développement distinct.
Les identifiants saisis doivent être des entiers strictement positifs, y compris
dans les invites interactives. Les erreurs SQLAlchemy sont présentées sans
requête SQL ni détails de connexion ; une erreur entraîne l'annulation de la
transaction en cours.

Aucun outil de lint ou de formatage n'est configuré dans ce dépôt.

## Journalisation Sentry

Voir [docs/SENTRY.md](docs/SENTRY.md) pour la configuration, les événements,
les protections des données et la recette de validation.
