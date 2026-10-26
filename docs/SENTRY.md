# Journalisation Sentry

## Configuration

Installer les dépendances avec `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`.
Créer un projet Python dans Sentry, puis copier son DSN dans le fichier local `.env` :

```dotenv
SENTRY_DSN=
SENTRY_ENVIRONMENT=development
SENTRY_RELEASE=epic-events@development
```

Renseigner la valeur vide uniquement dans `.env` ou dans les variables
d'environnement du déploiement. Ne jamais enregistrer un DSN réel dans le code,
les tests, les captures d'écran ou `.env.example`. Aucun jeton d'administration
Sentry n'est nécessaire à l'application. `.env` et ses variantes sont ignorés
par Git ; `.env.example` reste un modèle sans valeurs sensibles.

Sans DSN, aucun événement n'est envoyé. Avec un DSN invalide, un avertissement
générique est affiché et l'application continue. Une panne de Sentry ne doit pas
transformer une écriture réussie en erreur métier.

## Événements

L'entrée publique `python epicevents.py ...` initialise le SDK avant le traitement
de la commande et attend au maximum deux secondes pour vider la file à la sortie.
Les exceptions inattendues sont capturées puis propagées ; les erreurs SQLAlchemy
déjà traitées par l'interface sont également capturées avant le message utilisateur.
Les refus d'autorisation, erreurs métier, mauvaises saisies, sorties d'aide et
interruptions clavier ne sont pas des incidents inattendus.

Les services enregistrent les événements suivants après validation de la transaction :

| Action | Déclenchement |
| --- | --- |
| `employee.created` | Création, y compris le premier manager |
| `employee.updated` | Modification du nom, email ou département |
| `employee.password_changed` | Changement du mot de passe |
| `employee.deactivated` | Désactivation |
| `employee.deleted` | Suppression |
| `contract.signed` | Création déjà signée ou transition non signé vers signé |

Une mise à jour d'un contrat déjà signé ne produit pas une nouvelle signature.
Une nouvelle signature après retrait du statut signé produit un nouvel événement.
Les événements métier sont de niveau `info` dans Sentry (événements individuels,
pas de simples breadcrumbs). Ils portent le tag `action` et les seuls champs
`actor_id` / `entity_id`. Aucun nom, email, mot de passe, hash, JWT, montant ou
contenu de contrat n'est transmis.

Le module `app/monitoring.py` conserve les événements dans la transaction
SQLAlchemy. Un rollback, y compris de savepoint, les abandonne ; un savepoint
validé attend encore le commit externe. Les appels directs aux services
bénéficient du même mécanisme après initialisation de Sentry par leur appelant.
Les écritures SQL directes ne passent pas par cet audit.

## Confidentialité et limites

Les intégrations automatiques, breadcrumbs, variables locales, extraits de code
et traces de performance sont désactivés. `before_send` applique une liste de
champs autorisés : les exceptions conservent leur type et leurs emplacements
de pile, mais leur message est retiré car il peut contenir des requêtes SQL ou
des données personnelles. Les chemins absolus, paramètres de commande,
contexte utilisateur et extras non autorisés sont supprimés.

Sentry est un outil de diagnostic à livraison au mieux : quota épuisé, réseau
indisponible ou arrêt brutal peuvent faire perdre des événements. Il ne remplace
pas un journal d'audit durable transactionnel. La capture des exceptions couvre
l'entrée `epicevents.py` ; les scripts externes qui appellent les services doivent
initialiser le module et capturer leurs propres exceptions.

## Vérification

```powershell
$env:SENTRY_DSN = ""
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
Remove-Item Env:SENTRY_DSN
```

Les tests utilisent SQLite et un transport Sentry en mémoire : aucun événement
n'est envoyé à un vrai projet Sentry. Ils vérifient notamment le filtrage des
données, le commit/rollback et les transitions de signature.

Pour la recette réelle, configurer le DSN local et une base MySQL de développement.
Depuis les commandes habituelles, créer/modifier un collaborateur, puis signer
un contrat non signé. Vérifier les événements correspondants dans Sentry avec
le filtre d'environnement `development`. Pour tester une exception sans écrire
dans MySQL :

```powershell
.\.venv\Scripts\python.exe -B -c "from app import monitoring; monitoring.initialize(); monitoring.capture_exception(RuntimeError('Sentry verification')); monitoring.flush()"
```

Ce dernier test envoie volontairement un événement. Vérifier sa réception et
l'absence de données sensibles dans sa charge utile. Cette recette nécessite
un vrai DSN et n'est pas réalisée par les tests automatiques.

Référence : [documentation officielle du SDK Python](https://getsentry.github.io/sentry-python/api.html),
notamment `init`, `capture_exception`, `capture_event`, `before_send` et `flush`.
