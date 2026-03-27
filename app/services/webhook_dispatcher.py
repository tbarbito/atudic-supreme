"""
Serviço de dispatch de webhooks.

Envia payloads HTTP para URLs configuradas quando eventos do sistema ocorrem.
Executa em threads separadas para não bloquear o fluxo principal.
"""
import json
import threading
from datetime import datetime
import requests as http_requests

from app.database import get_db, release_db_connection


def dispatch_webhook_event(event_type, payload):
    """
    Busca webhooks ativos para o evento e dispara em threads separadas.

    Args:
        event_type: Tipo do evento (ex: PIPELINE_FINISH, RELEASE_FINISH)
        payload: Dicionário com dados do evento
    """
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, url, events, headers FROM webhooks WHERE is_active = TRUE"
        )
        webhooks = cursor.fetchall()
        release_db_connection(conn)
    except Exception as e:
        print(f"[WEBHOOK] Erro ao buscar webhooks: {e}")
        return

    for webhook in webhooks:
        # Verificar se o webhook escuta este tipo de evento
        events = webhook.get("events", "")
        event_list = [e.strip() for e in events.split(",")]
        if "*" not in event_list and event_type not in event_list:
            continue

        # Disparar em thread separada
        thread = threading.Thread(
            target=_send_webhook,
            args=(webhook, event_type, payload),
            daemon=True,
        )
        thread.start()


def _send_webhook(webhook, event_type, payload):
    """Envia o webhook HTTP (executado em thread separada)."""
    url = webhook["url"]
    name = webhook["name"]

    # Montar headers
    headers = {"Content-Type": "application/json", "User-Agent": "AtuDIC-Webhook/1.0"}
    try:
        custom_headers = json.loads(webhook.get("headers", "{}") or "{}")
        headers.update(custom_headers)
    except (json.JSONDecodeError, TypeError):
        pass

    # Montar payload
    body = {
        "event": event_type,
        "timestamp": datetime.now().isoformat(),
        "data": _serialize_payload(payload),
    }

    try:
        resp = http_requests.post(url, json=body, headers=headers, timeout=10)
        if resp.status_code >= 400:
            print(f"[WEBHOOK] '{name}' retornou {resp.status_code}: {url}")
        else:
            print(f"[WEBHOOK] '{name}' enviado com sucesso ({resp.status_code})")
    except http_requests.exceptions.Timeout:
        print(f"[WEBHOOK] '{name}' timeout: {url}")
    except http_requests.exceptions.ConnectionError:
        print(f"[WEBHOOK] '{name}' erro de conexão: {url}")
    except Exception as e:
        print(f"[WEBHOOK] '{name}' erro: {e}")


def _serialize_payload(payload):
    """Converte payload para formato serializável (trata datetime)."""
    result = {}
    for key, value in payload.items():
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result
