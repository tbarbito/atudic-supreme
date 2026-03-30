"""
Helpers compartilhados pelas tools do agente.
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _internal_api(method, path, json_body=None, headers=None):
    """Faz request interno às APIs do BiizHubOps usando test_client.
    Reutiliza as rotas existentes com todas as validações.
    """
    from flask import current_app, request

    auth_token = None
    if hasattr(request, "headers"):
        auth_token = request.headers.get("Authorization", "")

    client = current_app.test_client()
    req_headers = {"Content-Type": "application/json"}
    if auth_token:
        req_headers["Authorization"] = auth_token
    if headers:
        req_headers.update(headers)

    m = method.upper()
    if m == "GET":
        resp = client.get(path, headers=req_headers)
    elif m == "POST":
        resp = client.post(path, json=json_body or {}, headers=req_headers)
    elif m == "PUT":
        resp = client.put(path, json=json_body or {}, headers=req_headers)
    elif m == "PATCH":
        resp = client.patch(path, json=json_body or {}, headers=req_headers)
    elif m == "DELETE":
        resp = client.delete(path, headers=req_headers)
    else:
        resp = client.get(path, headers=req_headers)

    try:
        data = resp.get_json()
    except Exception:
        data = {"raw": resp.data.decode("utf-8", errors="replace")[:500]}

    if resp.status_code >= 400:
        return {"error": data.get("error", data.get("message", f"Erro HTTP {resp.status_code}"))}

    return data


def _serialize_rows(rows, date_fields=None):
    """Serializa datetimes em lista de dicts."""
    if not date_fields:
        date_fields = [
            "created_at", "started_at", "finished_at", "last_login",
            "last_run_at", "next_run_at", "acknowledged_at", "last_seen",
        ]
    for row in rows:
        for key in date_fields:
            if isinstance(row.get(key), datetime):
                row[key] = row[key].isoformat()
    return rows


PROFILE_LEVELS = {"viewer": 1, "operator": 2, "admin": 3}


def _check_permission(user_profile, min_profile):
    """Verifica se o perfil do usuário atende o mínimo exigido."""
    user_level = PROFILE_LEVELS.get(user_profile, 0)
    min_level = PROFILE_LEVELS.get(min_profile, 99)
    return user_level >= min_level
