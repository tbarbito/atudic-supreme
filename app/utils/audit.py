"""
Audit logging utility module.

This module provides functions to log security-relevant actions and events
for auditing purposes.
"""
import logging
from flask import request

def log_audit(action, user_id, user_name, details, status='success'):
    """
    Registra ação de auditoria de forma padronizada.
    
    Args:
        action (str): Tipo de ação (login, create_user, delete_repo, etc)
        user_id (str/int): ID do usuário que realizou a ação
        user_name (str): Nome do usuário
        details (str): Detalhes da ação
        status (str): Resultado da ação (padrão: 'success')
        
    Dependencies:
        - Requer contexto de requisição Flask ativo para capturar IP.
        - Requer logger 'audit' configurado na aplicação.
    """
    try:
        ip_addr = request.remote_addr if request else "unknown"
    except RuntimeError:
        # Fora do contexto de request (ex: CLI, tasks background)
        ip_addr = "system/internal"
        
    audit_logger = logging.getLogger('audit')
    audit_logger.info(
        f"ACTION={action} | USER_ID={user_id} | USER={user_name} | "
        f"STATUS={status} | IP={ip_addr} | DETAILS={details}"
    )
