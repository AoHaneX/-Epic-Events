# Schéma de la base de données

Base MySQL `epic_events` (moteur InnoDB, `utf8mb4_0900_ai_ci`), définie par
les modèles SQLAlchemy de [`app/models.py`](../app/models.py).

![Schéma de la base de données](database-schema.png)

```mermaid
erDiagram
    roles ||--o{ employees : "role_id"
    employees ||--o{ clients : "sales_contact_id (commercial)"
    clients ||--o{ contracts : "client_id"
    contracts ||--o| events : "contract_id (unique)"
    employees |o--o{ events : "support_contact_id (support)"

    roles {
        bigint id PK
        varchar(20) code UK "MANAGEMENT, SALES, SUPPORT"
        varchar(100) name UK
    }

    employees {
        bigint id PK
        varchar(150) full_name
        varchar(254) email UK
        varchar(255) password_hash "Argon2id"
        bigint role_id FK
        boolean is_active "défaut 1"
        datetime created_at
        datetime updated_at
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
| `employees.role_id` → `roles.id` | un rôle, plusieurs collaborateurs | interdite (`RESTRICT`) |
| `clients.sales_contact_id` → `employees.id` | un commercial, plusieurs clients | interdite (`RESTRICT`) |
| `contracts.client_id` → `clients.id` | un client, plusieurs contrats | interdite (`RESTRICT`) |
| `events.contract_id` → `contracts.id` | un contrat, au plus un événement | interdite (`RESTRICT`) |
| `events.support_contact_id` → `employees.id` | un support, plusieurs événements ; facultatif | le champ passe à `NULL` |

## Contraintes de contrôle

| Nom | Règle |
| --- | --- |
| `chk_contracts_amounts` | `0 <= remaining_amount <= total_amount` |
| `chk_contracts_signature` | non signé sans date, ou signé avec `signed_at` renseigné |
| `chk_events_dates` | `end_at > start_at` |
| `chk_events_contact` | `contact_email` ou `contact_phone` renseigné |

Index : `role_id`, `sales_contact_id`, `client_id`, `(is_signed, remaining_amount)`,
`support_contact_id` et `start_at`.
