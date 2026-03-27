"""
Agent Sandbox — Camada de seguranca para acoes do agente no sistema.

Controla quais paths podem ser acessados, quais comandos podem ser executados,
e registra toda acao em audit log. Seguranca ANTES de tools de sistema.

Principio: TUDO e bloqueado por padrao, exceto o que esta na allowlist.
"""

import os
import re
import json
import shlex
import fnmatch
import logging
from datetime import datetime

from app.database import get_db, release_db_connection

logger = logging.getLogger(__name__)


class SandboxPolicy:
    """Politica de sandbox para acoes do agente no sistema."""

    # Paths SEMPRE bloqueados (prioridade sobre allowed)
    BLOCKED_PATHS = [
        ".env",
        "config.env",
        ".encryption_key",
        ".encryption_key.backup",
        "/etc/shadow",
        "/etc/passwd",
        "/root",
        "*.pem",
        "*.key",
        "*.p12",
        "__pycache__",
        ".git/objects",
        "node_modules",
    ]

    # Comandos permitidos (allowlist — base do comando)
    ALLOWED_COMMANDS = [
        "ls",
        "cat",
        "head",
        "tail",
        "wc",
        "grep",
        "find",
        "diff",
        "file",
        "stat",
        "du",
        "git",
        "python3",
        "pip",
        "df",
        "free",
        "uptime",
        "ps",
        "curl",
        "echo",
    ]

    # Patterns de comando SEMPRE bloqueados
    BLOCKED_COMMAND_PATTERNS = [
        r"rm\s+-rf",
        r"rm\s+-r\s+/",
        r"shutdown|reboot|halt|poweroff",
        r"chmod\s+[0-7]*7[0-7]*",
        r">\s*/dev/",
        r"mkfs",
        r"dd\s+if=",
        r":\(\)\s*\{",
        r"\|\s*mail\b",
        r"curl.*-X\s*(POST|PUT|DELETE|PATCH)",
        r"wget\s.*-O\s*/",
        r"pip\s+install",
        r"sudo\s",
        r"su\s+-",
    ]

    # Limites padrao
    MAX_FILE_READ_SIZE = 1_048_576  # 1MB
    MAX_FILE_WRITE_SIZE = 102_400  # 100KB
    COMMAND_TIMEOUT = 30  # segundos
    MAX_ITERATIONS = 10
    TOKEN_BUDGET = 50_000

    def __init__(self, environment_id=None):
        self.environment_id = environment_id
        self.max_iterations = self.MAX_ITERATIONS
        self.token_budget = self.TOKEN_BUDGET
        self.command_timeout = self.COMMAND_TIMEOUT
        self.react_enabled = False
        self.system_tools_enabled = False
        self._extra_allowed_paths = []
        self._extra_blocked_commands = []
        self._load_config()

    def _load_config(self):
        """Carrega config de sandbox do banco (por ambiente)."""
        if not self.environment_id:
            return

        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM agent_sandbox_config WHERE environment_id = %s",
                (self.environment_id,),
            )
            row = cursor.fetchone()
            if row:
                config = dict(row)
                self.max_iterations = config.get("max_iterations", self.MAX_ITERATIONS)
                self.token_budget = config.get("token_budget", self.TOKEN_BUDGET)
                self.command_timeout = config.get("command_timeout", self.COMMAND_TIMEOUT)
                self.react_enabled = config.get("react_enabled", False)
                self.system_tools_enabled = config.get("system_tools_enabled", False)

                if config.get("allowed_paths"):
                    try:
                        self._extra_allowed_paths = json.loads(config["allowed_paths"])
                    except (json.JSONDecodeError, TypeError):
                        pass

                if config.get("blocked_commands"):
                    try:
                        self._extra_blocked_commands = json.loads(config["blocked_commands"])
                    except (json.JSONDecodeError, TypeError):
                        pass
        except Exception as e:
            # Tabela pode nao existir ainda (pre-migration)
            logger.debug("Sandbox config nao carregada: %s", e)
        finally:
            release_db_connection(conn)

    def _get_allowed_paths(self):
        """Resolve paths permitidos a partir de variaveis do ambiente."""
        paths = []

        # Diretorio base do AtuDIC (sempre permitido)
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        paths.append(base_dir)

        # Variaveis do ambiente (se configuradas)
        if self.environment_id:
            conn = get_db()
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT name, value FROM server_variables WHERE name LIKE %s",
                    ("%_DIR_%",),
                )
                for row in cursor.fetchall():
                    val = row["value"]
                    if val and os.path.isabs(val):
                        paths.append(val)
            except Exception:
                pass
            finally:
                release_db_connection(conn)

        # Paths extras configurados no banco
        for p in self._extra_allowed_paths:
            if p and os.path.isabs(p):
                paths.append(p)

        return paths

    def validate_path(self, path, mode="read"):
        """Valida se o path e acessivel pelo agente.

        Args:
            path: caminho a validar
            mode: 'read' ou 'write'

        Returns:
            tuple: (permitido: bool, razao: str)
        """
        abs_path = os.path.abspath(os.path.expanduser(path))

        # 1. Blocked paths tem prioridade absoluta
        for blocked in self.BLOCKED_PATHS:
            if fnmatch.fnmatch(os.path.basename(abs_path), blocked):
                return False, f"Arquivo bloqueado por politica: {blocked}"
            if blocked in abs_path:
                return False, f"Path contem segmento bloqueado: {blocked}"

        # 2. Path traversal check
        if ".." in path:
            # Resolver e verificar se nao escapou dos permitidos
            pass  # A verificacao abaixo ja cobre isso

        # 3. Deve estar dentro de um allowed path
        allowed_paths = self._get_allowed_paths()
        in_allowed = any(abs_path.startswith(ap) for ap in allowed_paths)

        if not in_allowed:
            return False, "Path fora dos diretorios permitidos"

        # 4. Verificacoes extras para escrita
        if mode == "write":
            if os.path.exists(abs_path):
                size = os.path.getsize(abs_path)
                if size > self.MAX_FILE_WRITE_SIZE:
                    return False, f"Arquivo existente grande ({size} bytes > {self.MAX_FILE_WRITE_SIZE})"

        # 5. Verificacao de tamanho para leitura
        if mode == "read" and os.path.exists(abs_path):
            size = os.path.getsize(abs_path)
            if size > self.MAX_FILE_READ_SIZE:
                return False, f"Arquivo muito grande ({size} bytes > {self.MAX_FILE_READ_SIZE})"

        return True, "OK"

    def validate_command(self, command):
        """Valida se o comando e permitido pelo sandbox.

        Returns:
            tuple: (permitido: bool, razao: str)
        """
        if not command or not command.strip():
            return False, "Comando vazio"

        # 1. Blocked patterns tem prioridade absoluta
        for pattern in self.BLOCKED_COMMAND_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return False, "Comando bloqueado por politica de seguranca"

        # 2. Blocked commands extras (configurados por ambiente)
        for blocked in self._extra_blocked_commands:
            if blocked.lower() in command.lower():
                return False, f"Comando bloqueado por configuracao do ambiente"

        # 3. Extrair comando base (primeiro token)
        try:
            tokens = shlex.split(command)
            cmd_base = os.path.basename(tokens[0]) if tokens else ""
        except ValueError:
            return False, "Comando com sintaxe invalida"

        # 4. Verificar contra allowlist
        allowed = any(cmd_base == ac for ac in self.ALLOWED_COMMANDS)

        if not allowed:
            return False, f"Comando '{cmd_base}' nao esta na allowlist"

        return True, "OK"

    def validate_tool_call(self, tool_name, params):
        """Valida um tool call do agente contra o sandbox.

        Despacha para validate_path ou validate_command conforme a tool.
        """
        if tool_name == "read_file":
            path = params.get("path", "")
            return self.validate_path(path, mode="read")

        elif tool_name == "write_file":
            path = params.get("path", "")
            return self.validate_path(path, mode="write")

        elif tool_name == "list_directory":
            path = params.get("path", "")
            return self.validate_path(path, mode="read")

        elif tool_name == "search_files":
            path = params.get("path", "")
            return self.validate_path(path, mode="read")

        elif tool_name == "get_file_info":
            path = params.get("path", "")
            return self.validate_path(path, mode="read")

        elif tool_name == "run_command":
            command = params.get("command", "")
            return self.validate_command(command)

        return True, "OK"

    def audit_log(self, action, params, result, user_info, session_id=None, iteration=0, tokens_used=0):
        """Registra acao do agente no audit log (PostgreSQL)."""
        username = (user_info or {}).get("username", "unknown")
        user_id = (user_info or {}).get("user_id")

        # Log arquivo
        result_status = "success"
        if isinstance(result, dict) and result.get("error"):
            result_status = "error"
        if action.startswith("BLOCKED:"):
            result_status = "blocked"

        logger.info(
            "AGENT_AUDIT: %s | %s | %s | %s",
            username,
            action,
            result_status,
            json.dumps(params, default=str)[:200],
        )

        # PostgreSQL
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO agent_audit_log
                    (user_id, username, environment_id, session_id, action,
                     params, result_status, result_summary, tokens_used, iteration)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    username,
                    self.environment_id,
                    session_id,
                    action,
                    json.dumps(params, default=str)[:2000],
                    result_status,
                    json.dumps(result, default=str)[:500] if isinstance(result, dict) else str(result)[:500],
                    tokens_used,
                    iteration,
                ),
            )
            conn.commit()
        except Exception as e:
            logger.warning("Erro ao salvar audit log: %s", e)
        finally:
            release_db_connection(conn)
