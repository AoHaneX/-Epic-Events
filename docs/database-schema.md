# Schéma de la base de données

Base MySQL `epic_events` (moteur InnoDB, `utf8mb4_0900_ai_ci`), définie par
les modèles SQLAlchemy de [`app/models.py`](../app/models.py).

![Schéma de la base de données](database-schema.png)

Les collaborateurs utilisent un **héritage par tables jointes** : `employees`
porte les champs communs et la colonne `role` ; `managers`,
`sales_employees` et `support_employees` partagent la même clé primaire.
Les clés étrangères visent la bonne spécialité : la base refuse elle-même
qu'un client soit suivi par un support ou qu'un événement soit confié à un
commercial. Le modèle conceptuel correspondant est [mcd.png](mcd.png).

```mermaid
erDiagram
    employees ||--o| managers : "id (héritage)"
    employees ||--o| sales_employees : "id (héritage)"
    employees ||--o| support_employees : "id (héritage)"
    sales_employees ||--o{ clients : "sales_contact_id"
    clients ||--o{ contracts : "client_id"
    contracts ||--o| events : "contract_id (unique)"
    support_employees |o--o{ events : "support_contact_id"

    employees {
        bigint id PK
        varchar(150) full_name
        varchar(254) email UK
        varchar(255) password_hash "Argon2id"
        varchar(20) role "MANAGEMENT, SALES, SUPPORT"
        boolean is_active "défaut 1"
        datetime created_at
        datetime updated_at
    }

    managers {
        bigint id PK, FK
    }

    sales_employees {
        bigint id PK, FK
    }

    support_employees {
        bigint id PK, FK
    }

    clients {
        bigint id PK
        varchar(150) full_name
        varchar(254) email UK
        varchar(32) phone
        varchar(200) company_name
        bigint sales_contact_id FK
        datetime created_at
        datetime updated_at
        datetime last_contact_at "nullable"
    }

    contracts {
        bigint id PK
        bigint client_id FK
        decimal total_amount "12,2"
        decimal remaining_amount "12,2"
        boolean is_signed "défaut 0"
        datetime signed_at "nullable"
        datetime created_at
        datetime updated_at
    }

    events {
        bigint id PK
        varchar(200) name
        bigint contract_id FK, UK
        bigint support_contact_id FK "nullable"
        varchar(150) contact_name "nullable"
        varchar(254) contact_email "nullable"
        varchar(32) contact_phone "nullable"
        datetime start_at
        datetime end_at
        varchar(500) location
        int attendees_count "non signé"
        text notes "nullable"
        datetime created_at
        datetime updated_at
    }
```

## Relations

| Relation | Cardinalité | Suppression du parent |
| --- | --- | --- |
| `managers.id`, `sales_employees.id`, `support_employees.id` → `employees.id` | héritage : un collaborateur a exactement une spécialité, indiquée par `employees.role` | la spécialité est supprimée avec lui (`CASCADE`) |
| `clients.sales_contact_id` → `sales_employees.id` | un commercial, plusieurs clients | interdite (`RESTRICT`) |
| `contracts.client_id` → `clients.id` | un client, plusieurs contrats | interdite (`RESTRICT`) |
| `events.contract_id` → `contracts.id` | un contrat, au plus un événement | interdite (`RESTRICT`) |
| `events.support_contact_id` → `support_employees.id` | un support, plusieurs événements ; facultatif | le champ passe à `NULL` |

## Contraintes de contrôle

| Nom | Règle |
| --- | --- |
| `chk_employees_role` | `role` vaut `MANAGEMENT`, `SALES` ou `SUPPORT` |
| `chk_contracts_amounts` | `0 <= remaining_amount <= total_amount` |
| `chk_contracts_signature` | non signé sans date, ou signé avec `signed_at` renseigné |
| `chk_events_dates` | `end_at > start_at` |
| `chk_events_contact` | `contact_email` ou `contact_phone` renseigné |

Index : `role`, `sales_contact_id`, `client_id`, `(is_signed, remaining_amount)`,
`support_contact_id` et `start_at`.
