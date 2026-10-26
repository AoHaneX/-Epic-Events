# Authentification et permissions

Le CRM utilise les comptes collaborateurs pour ouvrir une session persistante
et contrôler les actions autorisées selon leur rôle et leurs affectations.

## 1. Installer les dépendances et configurer le secret

```powershell
pip install -r requirements.txt
```

Dans `.env`, renseigner `DB_PASSWORD` avec le mot de passe du compte MySQL
`epic_events_app`. Générer ensuite un secret JWT aléatoire :

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copier le résultat dans la valeur de `JWT_SECRET` du fichier `.env`.
Le secret doit contenir au moins 32 caractères. Ne jamais publier ce secret
ni le fichier `.env`. Conserver le même secret entre les exécutions : le changer
invalide les jetons existants.

## 2. Créer le premier manager

Cette commande ne fonctionne que lorsque la table `employees` est vide :

```powershell
python epicevents.py create-manager
```

## 3. Ouvrir et consulter sa session

```powershell
python epicevents.py login
python epicevents.py status
```

`login` demande l'email et le mot de passe du collaborateur. Les mots de passe
sont saisis sans affichage et stockés en base sous forme de hash Argon2id.
`status` affiche l'utilisateur et le rôle de la session en cours.

Les jetons sont enregistrés dans `.epic_events/session.json`, dans le dossier
personnel de l'utilisateur. La variable optionnelle `EPIC_EVENTS_SESSION_FILE`
permet de choisir un autre chemin. Ce fichier contient des jetons permettant
d'utiliser la session : ne pas le partager ni le publier.

Par défaut, le jeton d'accès expire après 15 minutes (`ACCESS_TOKEN_MINUTES`).
Il est renouvelé automatiquement à la prochaine utilisation si le jeton de
renouvellement est encore valide. Ce dernier expire 7 jours après la connexion
(`REFRESH_TOKEN_DAYS`) ; le renouvellement du jeton d'accès ne prolonge pas
cette durée. Une fois les jetons expirés, la session locale est supprimée
lors de son utilisation et une nouvelle connexion est nécessaire.

Pour fermer la session locale :

```powershell
python epicevents.py logout
```

## 4. Créer les autres collaborateurs

```powershell
python epicevents.py create-employee
```

La commande utilise la session ouverte avec `login`, puis demande les données
du nouveau compte. Seul un collaborateur actif ayant le rôle `MANAGEMENT`
peut créer un collaborateur.

## 5. Utiliser les permissions

Toute future opération métier doit passer par un service. Avant une action,
appeler la règle adaptée depuis `app.permissions`, puis `require(...)`.

Exemple :

```python
from app.permissions import can_update_client, require

require(
    can_update_client(current_employee, client),
    "Tu ne peux modifier que tes propres clients.",
)
```

Ne jamais vérifier les rôles uniquement dans le menu ou l'interface : le
contrôle doit être exécuté dans le service qui écrit en base de données.
