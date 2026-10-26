"""Sentry integration: private diagnostics and commit-aware business events.

Only the CLI configures Sentry. Services queue events on their SQLAlchemy
transaction; successful outer commits publish them, rollbacks discard them.
Telemetry is best effort and must never change a business operation's outcome.
"""
import os
import sys
from pathlib import Path

import sentry_sdk
from dotenv import load_dotenv
from sqlalchemy import event
from sqlalchemy.orm import Session

_enabled = False
_KEY = 'epic_audit_events'
_COMMITTED = 'epic_audit_committed'
ACTIONS = frozenset({
    'employee.created', 'employee.updated', 'employee.password_changed',
    'employee.deactivated', 'employee.deleted', 'contract.signed',
})


def before_send(payload, hint):
    """Allowlist outgoing data, including exceptions whose text may contain SQL."""
    clean = {key: payload[key] for key in
             ('event_id', 'timestamp', 'platform', 'level', 'environment', 'release')
             if key in payload}
    action = payload.get('tags', {}).get('action')
    if action in ACTIONS:
        clean['message'] = action
        clean['tags'] = {'action': action}
        clean['extra'] = {key: value for key, value in payload.get('extra', {}).items()
                          if key in ('actor_id', 'entity_id') and type(value) is int}
    exceptions = []
    for item in payload.get('exception', {}).get('values', []):
        frames = []
        for frame in item.get('stacktrace', {}).get('frames', []):
            safe = {key: frame[key] for key in ('module', 'function', 'lineno', 'in_app') if key in frame}
            if frame.get('filename'):
                safe['filename'] = Path(frame['filename']).name
            frames.append(safe)
        exceptions.append({'type': item.get('type', 'Exception'),
                           'value': '[message retiré pour confidentialité]',
                           'stacktrace': {'frames': frames}})
    if exceptions:
        clean['exception'] = {'values': exceptions}
    return clean if exceptions or action in ACTIONS else None


def initialize():
    """Read local configuration without exposing the DSN, or stay disabled."""
    global _enabled
    if _enabled:
        return
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    dsn = os.getenv('SENTRY_DSN', '').strip()
    if not dsn:
        return
    try:
        sentry_sdk.init(
            dsn=dsn, environment=os.getenv('SENTRY_ENVIRONMENT', 'development'),
            release=os.getenv('SENTRY_RELEASE', 'epic-events@development'),
            send_default_pii=False, include_local_variables=False,
            include_source_context=False, default_integrations=False,
            auto_enabling_integrations=False, auto_session_tracking=False,
            traces_sample_rate=0, max_breadcrumbs=0, debug=False,
            before_send=before_send, shutdown_timeout=2,
        )
        _enabled = True
    except Exception:
        print('Journalisation Sentry indisponible : vérifier sa configuration.', file=sys.stderr)


def capture_exception(error):
    """Record unexpected failures without letting telemetry raise another error."""
    if _enabled:
        try:
            sentry_sdk.capture_exception(error)
        except Exception:
            pass


def flush():
    """Give the short-lived CLI up to two seconds to send pending events."""
    if _enabled:
        try:
            sentry_sdk.flush(timeout=2)
        except Exception:
            pass


def publish(action, actor_id, entity_id):
    if _enabled:
        try:
            sentry_sdk.capture_event({'message': action, 'level': 'info',
                                     'tags': {'action': action},
                                     'extra': {'actor_id': actor_id, 'entity_id': entity_id}})
        except Exception:
            pass


def queue_audit(session, action, actor_id, entity_id):
    """Queue safe scalar data on the active transaction, never an ORM object."""
    transaction = session.get_nested_transaction() or session.get_transaction()
    session.info.setdefault(_KEY, {}).setdefault(transaction, []).append((action, actor_id, entity_id))


@event.listens_for(Session, 'after_commit')
def _mark_committed(session):
    transaction = session.get_nested_transaction() or session.get_transaction()
    session.info.setdefault(_COMMITTED, set()).add(transaction)


@event.listens_for(Session, 'after_transaction_end')
def _finish_transaction(session, transaction):
    pending = session.info.get(_KEY, {})
    committed = session.info.get(_COMMITTED, set())
    records = pending.pop(transaction, [])
    if transaction in committed:
        committed.discard(transaction)
        if transaction.parent is not None:
            pending.setdefault(transaction.parent, []).extend(records)
        else:
            for record in records:
                publish(*record)
    if transaction.parent is None:
        session.info.pop(_KEY, None)
        session.info.pop(_COMMITTED, None)
