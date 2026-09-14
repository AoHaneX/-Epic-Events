# Epic Events CRM — démarrage SQLAlchemy

Ce squelette connecte Python à la base MySQL `epic_events` et mappe les tables
`employees`, `clients`, `contracts` et `events` avec SQLAlchemy 2.

## Installation sous PowerShell

Depuis le dossier du projet :

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Ouvrir ensuite `.env` et remplacer uniquement la valeur de `DB_PASSWORD` par
le mot de passe du compte MySQL `epic_events_app`.

Ne jamais envoyer le fichier `.env` sur GitHub. Il est déjà présent dans
`.gitignore`.

## Vérification

```powershell
python -m app.main
```

Le programme doit afficher une connexion réussie, la base `epic_events` et les
quatre tables. `Base.metadata.create_all()` crée les tables manquantes mais ne
met pas à jour une table existante. Les futures évolutions du schéma devront
être gérées avec Alembic.

## Organisation

```text
app/database.py  configuration de SQLAlchemy et des sessions
app/models.py    classes ORM Employee, Client, Contract et Event
app/main.py      test de connexion et détection des tables
```
