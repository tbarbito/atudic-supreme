"""
Configuração de logging com rotação de arquivos.

Formato JSON estruturado para app.log e errors.log (facilita aggregação).
Formato texto para console e audit.log (legibilidade humana).
"""
import os
import sys
import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from app.config import get_base_directory


class JSONFormatter(logging.Formatter):
    """Formatter que gera JSON estruturado por linha (JSONL).

    Inclui request_id do Flask g quando disponível.
    """

    def format(self, record):
        log_entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "func": record.funcName,
            "msg": record.getMessage(),
        }

        # Request ID do middleware (quando dentro de request context)
        try:
            from flask import g
            request_id = getattr(g, "request_id", None)
            if request_id:
                log_entry["request_id"] = request_id
        except RuntimeError:
            pass  # Fora do request context

        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False, default=str)


def setup_logging(app):
    """Configura logging com JSON estruturado (arquivos) e texto (console)."""
    log_dir = os.path.join(get_base_directory(), 'logs')
    os.makedirs(log_dir, exist_ok=True)

    print(f"📝 Logs do sistema: {log_dir}")
    print(f"   - app.log: JSON estruturado (INFO+)")
    print(f"   - errors.log: JSON estruturado (ERROR+)")
    print(f"   - audit.log: Auditoria (texto)")

    app.logger.handlers.clear()

    # Formatters
    json_formatter = JSONFormatter()
    text_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    )

    # Handler para arquivo geral — JSON (INFO+)
    general_handler = RotatingFileHandler(
        os.path.join(log_dir, 'app.log'),
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
        encoding='utf-8'
    )
    general_handler.setLevel(logging.INFO)
    general_handler.setFormatter(json_formatter)

    # Handler para erros — JSON (ERROR+)
    error_handler = RotatingFileHandler(
        os.path.join(log_dir, 'errors.log'),
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(json_formatter)

    # Handler para console — texto legível
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if app.debug else logging.INFO)
    console_handler.setFormatter(text_formatter)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    app.logger.addHandler(general_handler)
    app.logger.addHandler(error_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(logging.DEBUG if app.debug else logging.INFO)

    # Logger de auditoria separado — texto (legibilidade em revisão manual)
    audit_handler = RotatingFileHandler(
        os.path.join(log_dir, 'audit.log'),
        maxBytes=10 * 1024 * 1024,
        backupCount=20,
        encoding='utf-8'
    )
    audit_handler.setLevel(logging.INFO)
    audit_handler.setFormatter(text_formatter)

    audit_logger = logging.getLogger('audit')
    audit_logger.addHandler(audit_handler)
    audit_logger.setLevel(logging.INFO)

    app.logger.info("Sistema de logging configurado com sucesso")

    return audit_logger
