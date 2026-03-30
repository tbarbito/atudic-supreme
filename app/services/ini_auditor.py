"""
Serviço do Auditor de INI Protheus.

Parseia arquivos .ini de servidores Protheus (appserver.ini, dbaccess.ini, etc.),
compara contra boas práticas armazenadas no PostgreSQL e usa LLM apenas para
gerar insights humanizados sobre as diferenças encontradas.
"""

import configparser
import io
import json
import logging
import re
from datetime import datetime

from app.database import get_db, release_db_connection

logger = logging.getLogger(__name__)


# =================================================================
# PARSER DE INI
# =================================================================

def parse_ini_file(content, filename=""):
    """Parseia conteúdo de arquivo .ini com análise completa.

    Detecta: chaves ativas, comentadas, seções comentadas,
    linhas com sujeira/malformadas e problemas de encoding.

    Returns:
        dict com sections, commented, commented_sections, dirty_lines,
        encoding_info e meta
    """
    sections = {}
    commented = {}
    commented_sections = []  # Seções inteiras comentadas: ;[NomeSecao]
    dirty_lines = []  # Linhas malformadas ou com sujeira
    current_section = None
    in_commented_section = False
    total_keys = 0
    total_commented = 0

    # === ANÁLISE DE ENCODING ===
    encoding_info = _analyze_encoding(content if isinstance(content, bytes) else content.encode("utf-8", errors="replace"))

    # Garantir que content é string
    if isinstance(content, bytes):
        try:
            content = content.decode("utf-8")
        except UnicodeDecodeError:
            content = content.decode("cp1252", errors="replace")

    for line_num, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue

        # Detectar seção comentada: ;[NomeSecao] ou #[NomeSecao]
        commented_sec_match = re.match(r"^[;#]\s*\[(.+)\]", stripped)
        if commented_sec_match:
            sec_name = commented_sec_match.group(1)
            commented_sections.append({
                "line": line_num,
                "section": sec_name,
                "raw": stripped,
            })
            # Marcar que estamos dentro de uma seção comentada
            # Chaves abaixo pertencem a ESTA seção (não à anterior)
            current_section = sec_name
            in_commented_section = True
            if sec_name not in commented:
                commented[sec_name] = {}
            continue

        # Detectar seção ativa [NomeDaSecao]
        match = re.match(r"^\[(.+)\]$", stripped)
        if match:
            raw_section = match.group(1)
            # Merge case-insensitive: se [TSSTASKPROC] e [tsstaskproc] existem, unificar
            existing = next((s for s in sections if s.lower() == raw_section.lower()), None)
            current_section = existing if existing else raw_section
            in_commented_section = False
            if current_section not in sections:
                sections[current_section] = {}
            continue

        if not current_section:
            # Linha fora de qualquer seção (sujeira)
            if not stripped.startswith(";") and not stripped.startswith("#"):
                dirty_lines.append({
                    "line": line_num,
                    "content": stripped,
                    "reason": "Linha fora de qualquer seção. Será ignorada pelo Protheus.",
                })
            continue

        # Se estamos numa seção comentada, TODAS as chaves são comentadas
        # (mesmo que não tenham ; na frente — pertencem à seção desabilitada)
        if in_commented_section:
            # Chave ativa dentro de seção comentada — tratar como comentada
            if "=" in stripped and not stripped.startswith(";") and not stripped.startswith("#"):
                key, _, value = stripped.partition("=")
                key = key.strip()
                value = value.strip()
                commented[current_section][key] = value
                total_commented += 1
                continue

        # Detectar chave comentada: ;key=value ou #key=value
        commented_match = re.match(r"^[;#]\s*([A-Za-z_]\w*)\s*=\s*(.*)", stripped)
        if commented_match:
            key = commented_match.group(1)
            value = commented_match.group(2).strip()
            commented_sec = current_section
            if commented_sec not in commented:
                commented[commented_sec] = {}
            commented[commented_sec][key] = value
            total_commented += 1
            continue

        # Ignorar comentários puros (;texto sem =)
        if stripped.startswith(";") or stripped.startswith("#"):
            continue

        # Chave ativa: key=value
        if "=" in stripped:
            key, _, value = stripped.partition("=")
            key = key.strip()
            value = value.strip()

            # Detectar nomes de chave inválidos (sujeira)
            if not re.match(r"^[A-Za-z_][\w.]*$", key):
                dirty_lines.append({
                    "line": line_num,
                    "content": stripped,
                    "reason": f"Nome de chave inválido: '{key}'. Nomes devem conter apenas letras, números e underscore.",
                })
                # Ainda adiciona — o Protheus pode aceitar
            sections[current_section][key] = value
            total_keys += 1

            # Detectar valor vazio em chave que parece importante
            if not value and key.lower() not in {"memo", "trace", "debug"}:
                dirty_lines.append({
                    "line": line_num,
                    "content": stripped,
                    "reason": f"Chave '{key}' com valor vazio. Verifique se é intencional.",
                })
        else:
            # Linha sem '=' e sem ser comentário — sujeira
            dirty_lines.append({
                "line": line_num,
                "content": stripped,
                "reason": "Linha sem formato chave=valor. Pode causar erro no parse do Protheus.",
            })

    ini_type = _detect_ini_type(filename, sections)
    ini_role = _detect_ini_role(filename, sections, ini_type)

    return {
        "ini_type": ini_type,
        "ini_role": ini_role,
        "sections": sections,
        "commented": commented,
        "commented_sections": commented_sections,
        "dirty_lines": dirty_lines,
        "encoding_info": encoding_info,
        "meta": {
            "total_sections": len(sections),
            "total_keys": total_keys,
            "total_commented": total_commented,
            "total_commented_sections": len(commented_sections),
            "total_dirty_lines": len(dirty_lines),
        },
    }


def _analyze_encoding(content_bytes):
    """Analisa encoding do arquivo INI.

    Protheus OBRIGA ANSI (Windows-1252 / CP1252).
    Detecta: UTF-8 BOM, UTF-8 sem BOM, Latin-1, CP1252.
    """
    result = {
        "detected": "unknown",
        "is_valid": False,
        "has_bom": False,
        "issues": [],
    }

    # Detectar BOM (Byte Order Mark)
    if content_bytes.startswith(b"\xef\xbb\xbf"):
        result["has_bom"] = True
        result["detected"] = "UTF-8 com BOM"
        result["issues"].append(
            "Arquivo possui BOM (Byte Order Mark) UTF-8. "
            "O Protheus NÃO suporta BOM. Remover os 3 bytes iniciais (EF BB BF)."
        )
        content_bytes = content_bytes[3:]  # Remover BOM para análise
    elif content_bytes.startswith(b"\xff\xfe"):
        result["detected"] = "UTF-16 LE"
        result["issues"].append(
            "Arquivo em UTF-16 (Little Endian). Protheus requer ANSI (CP1252). "
            "Converter antes de usar."
        )
        return result
    elif content_bytes.startswith(b"\xfe\xff"):
        result["detected"] = "UTF-16 BE"
        result["issues"].append(
            "Arquivo em UTF-16 (Big Endian). Protheus requer ANSI (CP1252). "
            "Converter antes de usar."
        )
        return result

    # Verificar se tem caracteres acima de 0x7F (indica encoding não-ASCII)
    high_bytes = [b for b in content_bytes if b > 0x7F]

    if not high_bytes:
        # Puramente ASCII — compatível com qualquer encoding
        result["detected"] = "ASCII puro"
        result["is_valid"] = True
        return result

    # Tentar decodificar como UTF-8 válido
    try:
        content_bytes.decode("utf-8", errors="strict")
        is_valid_utf8 = True
    except UnicodeDecodeError:
        is_valid_utf8 = False

    # Tentar decodificar como CP1252
    try:
        content_bytes.decode("cp1252", errors="strict")
        is_valid_cp1252 = True
    except UnicodeDecodeError:
        is_valid_cp1252 = False

    if is_valid_cp1252 and not is_valid_utf8:
        result["detected"] = "ANSI (CP1252)"
        result["is_valid"] = True
    elif is_valid_utf8 and not result["has_bom"]:
        # UTF-8 sem BOM — pode funcionar se não tiver caracteres multi-byte
        has_multibyte = any(b > 0xC0 for b in high_bytes)
        if has_multibyte:
            result["detected"] = "UTF-8 (sem BOM)"
            result["is_valid"] = False
            result["issues"].append(
                "Arquivo em UTF-8 com caracteres multi-byte (acentos). "
                "Protheus requer ANSI (CP1252). Caracteres acentuados podem "
                "ser exibidos incorretamente. Converter para ANSI."
            )
        else:
            result["detected"] = "Compatível ANSI/UTF-8"
            result["is_valid"] = True
    elif is_valid_utf8 and result["has_bom"]:
        result["is_valid"] = False
    elif is_valid_cp1252:
        result["detected"] = "ANSI (CP1252)"
        result["is_valid"] = True
    else:
        result["detected"] = "Encoding desconhecido"
        result["issues"].append(
            "Não foi possível determinar o encoding. "
            "Verifique se o arquivo está em ANSI (CP1252)."
        )

    return result


def _detect_ini_type(filename, sections):
    """Detecta tipo de INI pelo nome do arquivo ou conteúdo.

    Detecção de TSS: presença de seções/chaves específicas do TSS como
    [JOB_WS], [tsstaskproc], [IPC_DISTMAIL], SPED_SAVEWSDL, [TSSOFFLINE].
    """
    fname = filename.lower()

    # Detecção por conteúdo — TSS tem prioridade sobre appserver genérico
    section_names = {s.lower() for s in sections}
    all_keys_lower = set()
    for sec_data in sections.values() if isinstance(sections, dict) else []:
        if isinstance(sec_data, dict):
            all_keys_lower.update(k.lower() for k in sec_data.keys())

    # TSS markers — APENAS seções/chaves EXCLUSIVAS do TSS
    # topmemomega e xmlsaveall existem em appservers comuns — NÃO são markers
    # job_ws como SEÇÃO é marker, mas JOB_WS como valor de Jobs= no OnStart NÃO é
    tss_section_markers = {"tsstaskproc", "ipc_distmail", "tssoffline", "ipc_smtp"}
    tss_key_markers = {"sped_savewsdl", "tsssecurity"}
    # job_ws só conta se for SEÇÃO (não se for nome de job dentro de OnStart)
    has_job_ws_section = "job_ws" in section_names
    has_tss_sections = bool(section_names & tss_section_markers)
    has_tss_keys = bool(all_keys_lower & tss_key_markers)
    if has_tss_sections or (has_job_ws_section and has_tss_keys):
        return "tss"

    if "appserver" in fname:
        return "appserver"
    if "dbaccess" in fname:
        return "dbaccess"
    if "smartclient" in fname:
        return "smartclient"
    if "totvsappserver" in fname:
        return "totvsappserver"

    # Detecção por conteúdo — outros tipos
    if "dbaccess" in section_names or "mssql" in section_names or "oracle" in section_names:
        return "dbaccess"
    if "general" in section_names and ("drivers" in section_names or "licenseserver" in section_names):
        return "appserver"
    if "config" in section_names and "drivers" in section_names:
        return "smartclient"

    return "custom"


def _detect_ini_role(filename, sections, ini_type):
    """Detecta o PAPEL funcional do INI no ecossistema Protheus.

    O papel é mais granular que o tipo — descreve a função do servidor:
    - tss: TOTVS Service SOA (transmissão fiscal)
    - broker_http: Broker de balanceamento HTTP/WebApp
    - broker_soap: Broker de Web Services SOAP
    - broker_rest: Broker de Web Services REST
    - slave: Servidor secundário de broker (atende conexões SmartClient/WebApp)
    - slave_ws: Servidor secundário dedicado a Web Services SOAP
    - job_server: Servidor de jobs/schedulers
    - rest_server: Servidor REST dedicado
    - standalone: Servidor autônomo sem broker
    - dbaccess_master: DBAccess broker (master)
    - dbaccess_slave: DBAccess secundário (slave)
    - dbaccess_standalone: DBAccess autônomo (sem distribuição)
    """
    fname = filename.lower()
    section_names = {s.lower() for s in sections}

    # Coletar todas as chaves e valores (case-insensitive)
    all_keys_lower = {}
    for sec_name, sec_data in sections.items():
        if isinstance(sec_data, dict):
            for k, v in sec_data.items():
                all_keys_lower[k.lower()] = str(v).lower().strip()

    # --- TSS ---
    if ini_type == "tss":
        return "tss"

    # --- DBAccess ---
    if ini_type == "dbaccess":
        mode = all_keys_lower.get("mode", "")
        if mode == "master":
            return "dbaccess_master"
        if mode == "slave":
            return "dbaccess_slave"
        return "dbaccess_standalone"

    # --- Brokers (detectar ANTES de slaves) ---
    # Broker HTTP/WebAgent: seção BALANCE_HTTP
    broker_sections = {s for s in section_names if s.startswith("balance_")}
    if broker_sections:
        if "balance_http" in section_names:
            return "broker_http"
        if "balance_web_services" in section_names:
            # Distinguir SOAP vs REST pelo contexto
            # Se tem REMOTE_SERVER apontando para portas REST conhecidas ou nome contém rest
            if "rest" in fname:
                return "broker_rest"
            return "broker_soap"
        return "broker_http"

    # --- Servidores AppServer por papel ---
    has_onstart = "onstart" in section_names
    has_httprest = "httprest" in section_names
    has_httpjob = "httpjob" in section_names
    has_job_sections = any(
        all_keys_lower.get(f"main") or
        (isinstance(sections.get(s, {}), dict) and "main" in {k.lower() for k in sections[s]})
        for s in sections if s.lower() not in (
            "general", "drivers", "tcp", "webapp", "http", "dbaccess",
            "service", "licenseclient", "tds", "sslconfigure", "webapp/webapp",
            "onstart", "app_monitor", "webagent", "webmonitor",
        )
    )

    # Job server: tem OnStart com jobs customizados (não WS)
    if has_onstart and has_job_sections and not has_httprest:
        jobs_val = ""
        for sec_name, sec_data in sections.items():
            if sec_name.lower() == "onstart" and isinstance(sec_data, dict):
                for k, v in sec_data.items():
                    if k.lower() == "jobs":
                        jobs_val = str(v).lower()
        # Se os jobs NÃO são WS/HTTP, é job server
        ws_indicators = {"job_ws", "job_http", "httpjob"}
        job_names = {j.strip() for j in jobs_val.split(",")}
        if job_names and not (job_names & ws_indicators):
            return "job_server"

    # REST: slave_rest (atrás de broker) ou rest_server (standalone)
    if has_httprest and has_httpjob and "job_ws" not in section_names:
        # Se tem licenseclient → é slave de broker REST
        if "licenseclient" in section_names:
            return "slave_rest"
        return "rest_server"

    # Slave de WS SOAP: tem JOB_WS com SIGAWEB/SIGAWS + seção de host:porta
    ws_job_sections = {s for s in section_names if s.startswith("job_ws") or s.startswith("job_")}
    host_port_sections = {s for s in section_names if ":" in s}
    if ws_job_sections and host_port_sections:
        if any("ws" in s.lower() for s in ws_job_sections):
            return "slave_ws"

    # Slave genérico: tem [LicenseClient] + [Drivers] + [WebApp] sem broker
    if "licenseclient" in section_names and "webapp" in section_names:
        # Sem balance_* e sem muitos environments → slave
        env_count = sum(1 for s in sections if _is_environment_section(s, sections))
        if env_count <= 2:
            return "slave"

    # Standalone: tem múltiplos environments ou configuração autônoma
    env_count = sum(1 for s in sections if _is_environment_section(s, sections))
    if env_count >= 3:
        return "standalone_multi_env"

    return "standalone"


def _is_environment_section(sec_name, sections):
    """Verifica se uma seção é um environment Protheus (tem RootPath, SourcePath, etc)."""
    env_keys = {"rootpath", "sourcepath", "startpath", "rpodb", "rpoversion", "rpolanguage"}
    sec_data = sections.get(sec_name, {})
    if isinstance(sec_data, dict):
        sec_keys_lower = {k.lower() for k in sec_data}
        return bool(sec_keys_lower & env_keys)
    return False


# =================================================================
# MOTOR DE COMPARAÇÃO (determinístico, sem LLM)
# =================================================================

def get_best_practices(ini_type):
    """Busca boas práticas ativas para o tipo de INI."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, ini_type, section, key_name, recommended_value,
                   value_type, min_value, max_value, enum_values,
                   severity, description, tdn_url, is_required
            FROM ini_best_practices
            WHERE ini_type = %s AND is_active = TRUE
            ORDER BY severity DESC, section, key_name
            """,
            (ini_type,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        release_db_connection(conn)


# =====================================================================
# REGRAS POR PAPEL — Filtro de seções e chaves relevantes
# =====================================================================
#
# Cada papel define QUAIS seções do INI são relevantes para auditoria.
# Regras de seções fora desta lista são DESCARTADAS antes da comparação.
# None = sem filtro (usar todas as regras do ini_type).
#
# Referência: TDN - Application Server - Arquivo de configuração
# https://tdn.totvs.com/pages/viewpage.action?pageId=6064745
#
# Baseado em 11 INIs reais de produção:
# - broker_http: AppServer_webagent_broker.ini (balanceador WebApp/HTML5)
# - broker_soap: appserver_broker_soap.ini (balanceador WS SOAP)
# - broker_rest: appserver_broker_rest.ini (balanceador WS REST)
# - slave: AppServer_slv01.ini (secundário SmartClient/WebApp)
# - slave_ws: AppServer_ws05.ini (secundário WS SOAP)
# - slave_rest: AppServer_ws_rest02.ini (secundário WS REST)
# - job_server: AppServer_job01.ini (servidor de jobs)
# - standalone_multi_env: appserver_sust.ini (sustentação multi-ambiente)
# - tss: AppServer_TSS.ini (transmissão fiscal)
# - dbaccess_master: dbaccess_broker.ini (broker de banco)
# - dbaccess_slave: dbaccess_slave.ini (secundário de banco)
# =====================================================================
_ROLE_RELEVANT_SECTIONS = {
    # --- BROKERS: balanceadores SIMPLES, sem environment, sem banco ---
    # Só têm [General] para log e [BALANCE_*] para distribuição.
    # NÃO possuem: DBAccess, Environment, Drivers, TCP, Broker, SSLConfigure,
    # LicenseClient, WebApp, HTTP, OnStart, TDS, WebAgent.
    "broker_http": {"general"},
    "broker_soap": {"general"},
    "broker_rest": {"general"},

    # --- SLAVES: servidores que atendem conexões via broker ---
    # Possuem Environment, DBAccess, Drivers, TCP, WebApp, LicenseClient.
    # NÃO possuem: Broker, HTTPREST, HTTPJOB (exceto slave_rest).
    "slave": {
        "general", "drivers", "tcp", "webapp", "dbaccess", "topconnect", "environment",
        "licenseclient", "service", "sslconfigure", "webagent",
    },
    "slave_ws": {
        "general", "drivers", "tcp", "webapp", "http", "dbaccess", "topconnect", "environment",
        "licenseclient", "service", "sslconfigure", "onstart",
    },
    "slave_rest": {
        "general", "drivers", "tcp", "webapp", "http", "dbaccess", "topconnect", "environment",
        "licenseclient", "service", "sslconfigure", "onstart",
        "httpjob", "httpv11", "httprest", "httpuri",
    },

    # --- JOB SERVER: executa jobs/schedulers em background ---
    # Tem Environment, DBAccess/TopConnect, OnStart, mas NÃO atende WebApp/HTTP.
    "job_server": {
        "general", "drivers", "tcp", "dbaccess", "topconnect", "environment",
        "licenseclient", "service", "onstart",
    },

    # --- REST SERVER: APIs REST dedicado (sem broker na frente) ---
    "rest_server": {
        "general", "drivers", "tcp", "http", "dbaccess", "topconnect", "environment",
        "service", "sslconfigure", "onstart",
        "httpjob", "httpv11", "httprest", "httpuri",
    },

    # --- STANDALONE: servidor completo autônomo ---
    # Pode ter qualquer seção — sem filtro.
    "standalone": None,
    "standalone_multi_env": None,

    # --- TSS: todas as regras TSS (já filtrado por ini_type=tss) ---
    "tss": None,

    # --- DBACCESS: sem seções de AppServer ---
    # Só General, Service e seções de banco de dados.
    # DBAccess master: gerencia locks e distribuição — NÃO conecta ao banco diretamente
    "dbaccess_master": {
        "general", "service",
    },
    # DBAccess slave: conecta ao banco — precisa de driver sections
    "dbaccess_slave": {
        "general", "service", "oracle", "mssql", "postgresql",
    },
    "dbaccess_standalone": None,
}

# Chaves de [General] que NÃO se aplicam a brokers
# (brokers não processam RPO, não conectam a banco, não têm environments)
_BROKER_IRRELEVANT_KEYS = {
    # Brokers NÃO processam RPO, NÃO conectam a banco, NÃO têm environments.
    # Só fazem roteamento de conexões — as únicas chaves relevantes são de LOG.
    # Tudo que for de memória, string, timeout, monitor, segurança, jobs etc
    # é irrelevante para o balanceador.
    "maxstringsize", "servermemoryinfo", "servermemoryinfocache",
    "servermemorycache", "servermemoryinfolog", "servermemorycachefree",
    "maxbucketcommittime", "inactivetimeout", "canacceptmonitor",
    "canacceptdebugger", "canacceptfsremote", "buildkillusers",
    "canacceptlb", "heaplimit", "servermemoryinfo",
    "logtimestamp", "showfulllog", "showipclient", "showipclients",
    "servermemoryinfo", "servermemorylimit",
    "servertype", "app_environment", "installpath",
    "maxquerysize", "checkspecialkey", "canrunjobs",
    "echoconsolelog", "debugthreadusedmemory", "enablediagnosticsfile",
    "enablememinfoccsv", "enablememinfocsvcsv", "enablememinfocsv",
    "monitorconnections", "monitorcontrolusermsg", "monitorcontrolusermmsgs",
    "minidumpmode", "file_max", "canacceptrpc",
    "changeencodingbehavior", "logmessages",
    "sslredirect", "ipc_activetimeout", "workthreadqtdmin",
    "latencylog", "latencylogfile", "latencylogmaxsize", "latencypinginterval",
    "floatingpointprecise", "newerclientconnection",
    "servermemoryinfo", "writeconsole", "writeconsolelog",
    "idismessages", "idemessages", "inicustomization",
    "kv_engine", "loghttpfuncs", "copytodelaim", "copytodelaim",
    "ctreemode", "usegdb", "usegdbcorename", "useprocdump",
    "wsdlstreamtype", "gt_reinsertall", "gt_reinsertall_time",
    "filecopy", "filecopyonedebug", "filecopy", "filecopyonedebug",
    "servermemoryinfo", "servermemoryinfolog",
    "errormaxsize", "servermemoryinfo", "servermemorycache",
    "servermemoryinfolog", "servermemoryinfocache",
    "servermemorycachefree", "servermemoryinfo",
    "servermemoryinfolog", "servermemoryinfo",
    "showipclients", "showipclients", "showfulllog",
    "servermemoryinfo", "servermemoryinfo", "servermemoryinfo",
    "servermemoryinfo", "servermemoryinfo",
    "powerschemeshowupgradesuggestion", "powerschemetimeinterval",
    "sqlite_collateritrim", "sqlite_rebuildtables", "sqlite_trailspace",
    "socketdefaultipv6", "socketsdefaultipv6",
}


# =====================================================================
# CHAVES CONHECIDAS DO PROTHEUS — para detecção de sujeira/typos
# =====================================================================
# Fonte: TDN (tdn.totvs.com) + regras de boas práticas + INIs reais
# Chaves fora desta lista + fora das regras são marcadas como "desconhecidas"
# O set é case-insensitive (tudo lowercase)

_KNOWN_KEYS_BY_SECTION = {
    # [General]
    "general": {
        "maxstringsize", "consolelog", "consolemaxsize", "consolelogdate", "consolefile",
        "asyncconsolelog", "asyncmaxfiles", "echoconsolelog", "writeconsolelog",
        "logtimestamp", "showfulllog", "showipclient", "showipclients",
        "canacceptmonitor", "canacceptdebugger", "canacceptfsremote", "canacceptlb",
        "canacceptrpc", "canrunjobs", "buildkillusers",
        "servertype", "servermemoryinfo", "servermemorylimit", "servermemoryinfocache",
        "heaplimit", "maxbucketcommittime", "inactivetimeout", "maxquerysize",
        "app_environment", "installpath", "ctreemode", "checkspecialkey",
        "debugthreadusedmemory", "enablediagnosticsfile", "enablememinfocsv",
        "monitorconnections", "monitorcontrolusermsg", "minidumpmode",
        "file_max", "changeencodingbehavior", "logmessages", "sslredirect",
        "ipc_activetimeout", "workthreadqtdmin", "latencylog", "latencylogfile",
        "latencylogmaxsize", "latencypinginterval", "floatingpointprecise",
        "newerclientconnection", "inicustomization", "kv_engine", "loghttpfuncs",
        "usegdb", "usegdbcorename", "useprocdump", "wsdlstreamtype",
        "gt_reinsertall", "gt_reinsertall_time", "filecopyonedebug",
        "errormaxsize", "powerschemeshowupgradesuggestion", "powerschemetimeinterval",
        "sqlite_collateritrim", "sqlite_rebuildtables", "sqlite_trailspace",
        "socketsdefaultipv6", "idemessages", "disabledeviceport", "copytodelim",
        "console", "filecopyonedebug", "filecopy", "regionallanguage",
        "skip_msg_appbld_bc68a",
        # DBAccess General
        "mode", "masterserver", "masterport", "port", "licenseserver", "licenseport",
        "licenselimit", "byyouproc", "threadinfo", "logfull", "glbprofiler",
        "addcolumnsonline", "threadmin", "threadmax", "threadinc",
        "maxconnections", "logfile", "monitorport", "monitorall",
        "uselargerecno", "releaseinactiveconn", "checkdeadlock", "allowhosts",
        "showallerrors", "dbwarnings", "dbpulse",
    },
    # [Environment] — chaves de environment (nome customizado pelo cliente)
    "environment": {
        "sourcepath", "rootpath", "startpath", "rpodb", "rpoversion", "rpolanguage",
        "rpointerface", "localfiles", "trace", "localdbextension", "topmemomega",
        "changeencodingbehavior", "rpocustom", "x2_path", "pictformat",
        "regionallanguage", "specialkey", "startsysindb", "consolelog",
        "maxstringsize", "killstack", "inactivetimeout",
        "dbdatabase", "dbserver", "dbalias", "dbport",
        "topconntype", "maxquerysize",
        "tracestack", "logprofiler", "ixblog", "fwtracelog",
        "advsqlreplay", "advsqlreplayiop", "advsqlreplaylog",
        "advsqlreplaymaxsize", "advsqlreplaypath", "advsqlreplaystackdepth",
        "canlogadvplfunctions", "ctreerootpath",
        # TSS SPED
        "sped_savewsdl", "sped_hverao", "xmlsaveall", "topmemomega",
        "tssondemand", "loginfo", "logerro", "sped_delmail",
        "log_period", "log_period_tr2", "systimeadjust",
    },
    # [Drivers]
    "drivers": {
        "active", "multiprotocolport", "multiprotocolportsecure", "secure",
    },
    # [TCP]
    "tcp": {
        "type", "port", "ip",
    },
    # [SSL]
    "ssl": {
        "type", "port", "ip",
    },
    # [DBAccess] / [TopConnect]
    "dbaccess": {
        "server", "port", "database", "alias", "driver", "memomega", "protheusonly",
    },
    "topconnect": {
        "server", "port", "database", "alias", "driver", "memomega", "protheusonly",
        "topcontype",
    },
    # [WebApp]
    "webapp": {
        "port", "envserver", "lastmainprog", "websocket", "hideparamsform",
        "interface", "etags", "httpheaders", "httpheaders_options",
        "maxbodysize", "maxheadersize", "maxrequesttime", "nonstoperror",
        "obfuscate_protocol", "onlyhostnames",
        "sslcacertificate", "sslcacertificatefile", "sslcertificate",
        "sslclientauth", "sslkey", "sslmethod", "sslpassphrase", "threadcookie",
    },
    # [HTTP]
    "http": {
        "enable", "port", "path", "instances", "sessiontimeout", "maxstringsize",
        "environment",
    },
    # [SSLConfigure]
    "sslconfigure": {
        "hsm", "verbose", "ssl2", "ssl3", "tls1", "tls1_0", "tls1_1", "tls1_2",
        "bugs", "state", "certificateclient", "keyclient", "passphrase",
        "certificateserver", "keyserver",
    },
    # [OnStart]
    "onstart": {
        "jobs", "refreshrate",
    },
    # [Service]
    "service": {
        "name", "displayname",
    },
    # [LicenseClient]
    "licenseclient": {
        "server", "port",
    },
    # [LicenseServer]
    "licenseserver": {
        "port", "enable", "enabledisabledsessions",
    },
    # [WebAgent]
    "webagent": {
        "port", "version", "windows_x86", "windows_x64",
        "linux_x64_deb", "linux_x64_rpm",
        "darwin_universal", "darwin_arm64", "darwin_x64",
        "disableincompatibleso",
    },
    # [TDS]
    "tds": {
        "allowapplypatch", "allowedit",
    },
    # [FTP]
    "ftp": {
        "enable", "port", "path", "rootpath",
    },
    # [Broker]
    "broker": {
        "enable", "port", "type", "servers", "balancebyresource",
        "maxconnections", "sslcertificate", "sslkey", "webmonitorport",
    },
    # [BrokerAgent]
    "brokeragent": {
        "enable", "port", "brokerserver",
    },
    # [HTTPJOB] / [HTTPREST] / [HTTPURI] / [HTTPV11]
    "httpjob": {
        "main", "environment",
    },
    "httpv11": {
        "enable", "sockets", "timeout",
    },
    "httprest": {
        "port", "ipsbind", "uris", "security",
    },
    "httpuri": {
        "url", "preparein", "instances", "corsenable", "alloworigin",
        "expirationtime", "expirationdelta",
    },
    # [App_Monitor]
    "app_monitor": {
        "enable",
    },
    # [WebMonitor]
    "webmonitor": {
        "enable",
    },
    # [Mail]
    "mail": {
        "smtppopserver", "smtppopport", "smtpauth", "smtppopuser", "smtppoppassword",
    },
    # [Proxy]
    "proxy": {
        "enable", "server", "port", "user", "password", "noproxyfor",
    },
    # [LockServer]
    "lockserver": {
        "enable", "server", "port",
    },
    # Seções de JOB genérico
    "_job_generic": {
        "type", "main", "environment", "instances", "instancename",
        "sigaweb", "sigaws", "onstart", "onconnect",
        "expirationtime", "expirationdelta", "abendlock",
        "responsejob", "defaultpage", "enable", "path",
        "preparein", "security", "nparms", "parm1", "parm2", "parm3",
        "xmlsaveall", "tsssecurity", "profile", "profiletimer", "trace",
    },
    # [ENABLE_WS] — TSS
    "enable_ws": set(),  # Chaves dinâmicas (nomes de WS) — aceitar tudo
    # DBAccess driver sections
    "oracle": {
        "environments", "clientlibrary",
    },
    "mssql": {
        "environments", "clientlibrary", "server", "database", "port",
        "integratedsecurity",
    },
    "postgresql": {
        "environments", "clientlibrary", "server", "database", "port",
    },
    # DBAccess [DRIVER/ENVIRONMENT] sections (ex: [ORACLE/PROTHEUS])
    # Chaves de conexão específicas por environment do DBAccess
    "_dbaccess_driver_env": {
        "user", "password", "tablespace", "indexspace", "lobspace",
        "logaction", "memoasblob", "memoinquery", "userowstamp",
        "userowinsdot", "compression", "seekbind", "usebind", "usehint",
        "indexhint", "uselockindb", "useddltrace", "usesystables",
        "deadlockexit", "locktimeout",
    },
    # Balance sections (broker)
    "balance_http": set(),  # Chaves dinâmicas (REMOTE_SERVER_*) — aceitar tudo
    "balance_web_services": set(),  # idem
}

# Seções que aceitam QUALQUER chave (dinâmicas)
_DYNAMIC_SECTIONS = {
    "enable_ws", "balance_http", "balance_web_services",
    "webapp/webapp",
}


def _detect_unknown_keys(parsed):
    """Detecta chaves desconhecidas/sujeira em cada seção do INI.

    Compara contra _KNOWN_KEYS_BY_SECTION. Seções de environment
    e host:porta são tratadas especialmente. Retorna lista de findings.
    """
    sections = parsed.get("sections", {})
    unknown = []

    # Coletar chaves conhecidas de todas as regras de boas práticas
    from app.services.ini_auditor import _get_known_rules
    rules = _get_known_rules()
    rules_keys = {}
    for r in rules:
        sec = r["section"].lower()
        if sec not in rules_keys:
            rules_keys[sec] = set()
        rules_keys[sec].add(r["key_name"].lower())

    for sec_name, sec_data in sections.items():
        if not isinstance(sec_data, dict):
            continue

        sec_lower = sec_name.lower()

        # Seções dinâmicas — aceitar tudo
        if sec_lower in _DYNAMIC_SECTIONS:
            continue

        # Seções com host:porta (ex: [SPDWVPTH002D:8391]) — aceitar tudo
        if ":" in sec_name:
            continue

        # Seções DRIVER/ENVIRONMENT do DBAccess (ex: [ORACLE/PROTHEUS]) — usar chaves específicas
        if "/" in sec_name:
            known = set(_KNOWN_KEYS_BY_SECTION.get("_dbaccess_driver_env", set()))
            known.update(rules_keys.get(sec_lower, set()))
            for key in sec_data:
                if key.lower() not in known:
                    unknown.append({
                        "section": sec_name, "key_name": key, "value": sec_data[key],
                        "severity": "warning",
                        "reason": f"Chave '{key}' não é reconhecida na seção [{sec_name}].",
                    })
            continue

        # Determinar quais chaves são conhecidas para esta seção
        known = set()

        # 1. Chaves do _KNOWN_KEYS_BY_SECTION
        if sec_lower in _KNOWN_KEYS_BY_SECTION:
            known.update(_KNOWN_KEYS_BY_SECTION[sec_lower])
        else:
            # Seção não registrada — verificar se é environment
            env_keys = {"rootpath", "sourcepath", "startpath", "rpodb", "rpoversion", "rpolanguage"}
            sec_keys_lower = {k.lower() for k in sec_data}
            if sec_keys_lower & env_keys:
                # É um environment — usar chaves de environment
                known.update(_KNOWN_KEYS_BY_SECTION.get("environment", set()))
            else:
                # Seção de job customizado ou desconhecida — usar chaves genéricas de job
                known.update(_KNOWN_KEYS_BY_SECTION.get("_job_generic", set()))

        # 2. Chaves das regras de boas práticas
        known.update(rules_keys.get(sec_lower, set()))

        # 3. Verificar cada chave do arquivo
        for key in sec_data:
            key_lower = key.lower()
            if key_lower not in known:
                unknown.append({
                    "section": sec_name,
                    "key_name": key,
                    "value": sec_data[key],
                    "severity": "warning",
                    "reason": f"Chave '{key}' não é reconhecida na seção [{sec_name}]. "
                              f"Pode ser erro de digitação ou chave obsoleta.",
                })

    return unknown


def compare_against_best_practices(parsed, ini_type=None):
    """Compara INI parseado contra boas práticas do banco.

    Análise contextual:
    - Filtra regras pelo PAPEL (ini_role) — broker não precisa de [DBAccess]
    - Só avalia regras para seções que EXISTEM no arquivo (exceto obrigatórias)
    - Detecta chaves comentadas que podem impactar operação
    - Gera INI sugerido com correções

    Returns:
        dict com findings, commented_findings, score, summary, suggested_ini
    """
    ini_type = ini_type or parsed.get("ini_type", "appserver")
    ini_role = parsed.get("ini_role", "standalone")
    practices = get_best_practices(ini_type)

    if not practices:
        return {
            "findings": [], "commented_findings": [],
            "score": 100.0,
            "summary": {"ok": 0, "mismatch": 0, "missing": 0, "commented": 0},
            "suggested_ini": "",
        }

    # Filtrar regras pelo papel — descartar seções irrelevantes
    is_broker = ini_role in ("broker_http", "broker_soap", "broker_rest")
    relevant_sections = _ROLE_RELEVANT_SECTIONS.get(ini_role)
    if relevant_sections is not None:
        practices = [
            bp for bp in practices
            if bp["section"].lower() in relevant_sections
        ]
    # Para brokers: filtrar também chaves de [General] que não fazem sentido
    if is_broker:
        practices = [
            bp for bp in practices
            if bp["key_name"].lower() not in _BROKER_IRRELEVANT_KEYS
        ]

    sections = parsed.get("sections", {})
    commented = parsed.get("commented", {})
    findings = []
    commented_findings = []
    ok_count = 0
    mismatch_count = 0
    missing_count = 0

    weights = {"critical": 3.0, "warning": 1.5, "info": 0.5}
    total_weight = 0
    ok_weight = 0

    # Seções presentes no arquivo (case-insensitive)
    present_sections = {s.lower() for s in sections}

    # Detectar seções de Environment dinâmicas (nome definido pelo cliente)
    # Chaves indicadoras de environment: RootPath, SourcePath, StartPath, RpoDb, RpoVersion
    env_indicator_keys = {"rootpath", "sourcepath", "startpath", "rpodb", "rpoversion", "rpolanguage"}
    detected_environments = []
    for sec_name, sec_keys in sections.items():
        sec_keys_lower = {k.lower() for k in sec_keys}
        if sec_keys_lower & env_indicator_keys:  # Interseção — tem ao menos 1 chave de env
            detected_environments.append(sec_name)

    # Seções conhecidas do INI que NÃO são environments
    known_sections = {
        "general", "drivers", "dbaccess", "topconnect", "licenseserver", "licenseclient",
        "webapp", "webagent", "update", "http", "https", "httpserver",
        "ftp", "telnet", "mail", "sslconfigure", "onstart", "service",
        "lockserver", "servernetwork", "rpc", "proxy", "tds",
        "btmonitor", "btmonitorappd", "app_monitor", "coverage",
        "ctreeserver", "ctreeservermaster", "sqliteserver",
        "tec.appserver.memory", "tec.appserver.smartheap",
        "serverprinters", "nettest", "mpp", "logclient",
        "totvstec_tlpp",
    }

    # Detectar conexão com banco — 3 formas alternativas:
    # 1. [DBAccess] — padrão atual
    # 2. [TopConnect] — legado, mesma função
    # 3. Chaves DB* dentro do [Environment] (DBDataBase, DBServer, DBAlias, DBPort)
    has_dbaccess = "dbaccess" in present_sections
    has_topconnect = "topconnect" in present_sections
    has_db_in_env = False
    db_env_keys = {"dbdatabase", "dbserver", "dbalias", "dbport"}
    for env_name in detected_environments:
        env_data = sections.get(env_name, {})
        env_keys_lower = {k.lower() for k in env_data}
        if env_keys_lower & db_env_keys:
            has_db_in_env = True
            break
    has_db_connection = has_dbaccess or has_topconnect or has_db_in_env

    # Detectar conflito de configuração de banco (múltiplas fontes)
    db_sources = []
    if has_dbaccess:
        db_sources.append("[DBAccess]")
    if has_topconnect:
        db_sources.append("[TopConnect]")
    if has_db_in_env:
        db_sources.append("chaves DB* no [Environment]")
    # Papéis que NÃO precisam de conexão com banco
    roles_without_db = {"broker_http", "broker_soap", "broker_rest", "dbaccess_master", "dbaccess_slave", "dbaccess_standalone"}

    if len(db_sources) > 1:
        findings.append({
            "section": "General", "key_name": "ConexãoBanco",
            "current_value": " + ".join(db_sources),
            "recommended_value": "apenas uma fonte",
            "severity": "warning", "status": "mismatch",
            "best_practice_id": None,
            "description": (
                f"Múltiplas configurações de banco detectadas: {', '.join(db_sources)}. "
                f"Podem conflitar — verifique qual está sendo usada efetivamente."
            ),
            "tdn_url": None,
        })
    elif not has_db_connection and ini_role not in roles_without_db:
        findings.append({
            "section": "General", "key_name": "ConexãoBanco",
            "current_value": None,
            "recommended_value": "[DBAccess], [TopConnect] ou chaves DB* no [Environment]",
            "severity": "critical", "status": "missing",
            "best_practice_id": None,
            "description": (
                "Nenhuma configuração de conexão com banco detectada. "
                "Defina [DBAccess], [TopConnect] ou chaves DB* (DBDataBase, DBServer, DBAlias, DBPort) "
                "no environment para conectar ao banco."
            ),
            "tdn_url": None,
        })

    for bp in practices:
        sec = bp["section"]
        key = bp["key_name"]
        weight = weights.get(bp["severity"], 1.0)

        # Regra especial para [Environment]: aplicar em CADA environment detectado
        if sec.lower() == "environment" and detected_environments:
            for env_name in detected_environments:
                ctr = {"ok": 0, "mismatch": 0, "missing": 0, "weight": 0, "ok_weight": 0}
                _evaluate_bp_against_section(
                    bp, env_name, key, weight, weights,
                    sections, commented,
                    findings, commented_findings,
                    ctr, is_environment=True,
                )
                ok_count += ctr["ok"]
                mismatch_count += ctr["mismatch"]
                missing_count += ctr["missing"]
                total_weight += ctr["weight"]
                ok_weight += ctr["ok_weight"]
            continue

        is_section_present = sec.lower() in present_sections

        # Regra especial: [DBAccess] — pular se banco configurado via [TopConnect] ou DB* no environment
        if sec.lower() == "dbaccess" and not has_dbaccess and has_db_connection:
            continue  # Banco configurado por outra via — [DBAccess] não é necessário

        # Regra contextual: só avaliar se a seção existe no arquivo OU a regra é obrigatória
        if not is_section_present and not bp["is_required"]:
            continue  # Seção não existe e chave não é obrigatória — ignorar

        total_weight += weight

        # Buscar valor atual (case-insensitive)
        current_value = _find_key_in_sections(sections, sec, key)

        # Verificar se está comentada
        commented_value = _find_key_in_sections(commented, sec, key)

        if current_value is None:
            if commented_value is not None:
                # Chave está COMENTADA — avisar
                commented_findings.append({
                    "section": sec,
                    "key_name": key,
                    "commented_value": commented_value,
                    "recommended_value": bp["recommended_value"],
                    "severity": bp["severity"],
                    "status": "commented",
                    "best_practice_id": bp["id"],
                    "description": bp["description"],
                    "tdn_url": bp["tdn_url"],
                    "reason": _explain_commented(bp, commented_value),
                })
                # Penalizar como missing (a chave está desativada)
                if bp["is_required"]:
                    missing_count += 1
                else:
                    ok_weight += weight * 0.3
                continue

            if bp["is_required"]:
                status = "missing"
                missing_count += 1
            elif is_section_present:
                # Seção existe mas chave ausente — sugerir apenas se relevante
                status = "missing"
                missing_count += 1
                ok_weight += weight * 0.5  # Penalidade menor (seção presente, chave ausente)
            else:
                continue  # Seção não presente + chave não obrigatória = ignorar

            findings.append({
                "section": sec, "key_name": key,
                "current_value": None,
                "recommended_value": bp["recommended_value"],
                "severity": bp["severity"], "status": status,
                "best_practice_id": bp["id"],
                "description": bp["description"], "tdn_url": bp["tdn_url"],
            })
            continue

        # Chave existe — avaliar valor
        is_ok = _evaluate_value(current_value, bp)

        if is_ok:
            status = "ok"
            ok_count += 1
            ok_weight += weight
        else:
            status = "mismatch"
            mismatch_count += 1

        findings.append({
            "section": sec, "key_name": key,
            "current_value": current_value,
            "recommended_value": bp["recommended_value"],
            "severity": bp["severity"], "status": status,
            "best_practice_id": bp["id"],
            "description": bp["description"], "tdn_url": bp["tdn_url"],
        })

    # Score ponderado — apenas critical e warning impactam
    # Info-level ausente/incorreto NÃO reduz o score (são dicas, não erros)
    score_weight = 0
    score_ok = 0
    for f in findings:
        w = weights.get(f["severity"], 0.5)
        if f["severity"] == "info":
            # Info: conta como OK no score (não penaliza)
            score_weight += w
            score_ok += w
        elif f["status"] == "ok":
            score_weight += w
            score_ok += w
        else:
            # critical/warning com mismatch/missing — penaliza
            score_weight += w
            # Penalidade parcial para missing não-required
            if f["status"] == "missing" and not f.get("is_required"):
                score_ok += w * 0.3
    score = (score_ok / score_weight * 100) if score_weight > 0 else 100.0
    score = round(min(100.0, max(0.0, score)), 1)

    # Detectar chaves desconhecidas/sujeira
    unknown_keys = _detect_unknown_keys(parsed)

    # Gerar INI sugerido (com sujeira comentado)
    suggested_ini = _generate_suggested_ini(parsed, findings, commented_findings, practices, unknown_keys)

    return {
        "findings": findings,
        "commented_findings": commented_findings,
        "score": score,
        "summary": {
            "ok": ok_count, "mismatch": mismatch_count,
            "missing": missing_count, "commented": len(commented_findings),
            "unknown_keys": len(unknown_keys),
        },
        "suggested_ini": suggested_ini,
        "unknown_keys": unknown_keys,
    }


def _evaluate_bp_against_section(bp, sec_name, key, weight, weights,
                                  sections, commented,
                                  findings, commented_findings,
                                  counter, is_environment=False):
    """Avalia uma regra contra uma seção específica. Usado para environments dinâmicos."""
    counter["weight"] += weight
    display_section = f"{sec_name}" if is_environment else bp["section"]

    current_value = _find_key_in_sections(sections, sec_name, key)
    commented_value = _find_key_in_sections(commented, sec_name, key)

    if current_value is None:
        if commented_value is not None:
            commented_findings.append({
                "section": display_section,
                "key_name": key,
                "commented_value": commented_value,
                "recommended_value": bp["recommended_value"],
                "severity": bp["severity"],
                "status": "commented",
                "best_practice_id": bp["id"],
                "description": bp["description"],
                "tdn_url": bp["tdn_url"],
                "reason": _explain_commented(bp, commented_value),
            })
            if bp["is_required"]:
                counter["missing"] += 1
            else:
                counter["ok_weight"] += weight * 0.3
            return

        if bp["is_required"]:
            counter["missing"] += 1
        else:
            counter["ok_weight"] += weight * 0.5
            # Chave opcional ausente em environment detectado — só reportar se relevante
            if not is_environment:
                return

        findings.append({
            "section": display_section, "key_name": key,
            "current_value": None,
            "recommended_value": bp["recommended_value"],
            "severity": bp["severity"],
            "status": "missing",
            "best_practice_id": bp["id"],
            "is_required": bp.get("is_required", False),
            "description": bp["description"], "tdn_url": bp["tdn_url"],
        })
        return

    is_ok = _evaluate_value(current_value, bp)
    if is_ok:
        counter["ok"] += 1
        counter["ok_weight"] += weight
        status = "ok"
    else:
        counter["mismatch"] += 1
        status = "mismatch"

    findings.append({
        "section": display_section, "key_name": key,
        "current_value": current_value,
        "recommended_value": bp["recommended_value"],
        "severity": bp["severity"], "status": status,
        "best_practice_id": bp["id"],
        "is_required": bp.get("is_required", False),
        "description": bp["description"], "tdn_url": bp["tdn_url"],
    })


def _find_key_in_sections(sections_dict, section, key):
    """Busca valor de chave em dicionário de seções (case-insensitive)."""
    for s_name, s_vals in sections_dict.items():
        if s_name.lower() == section.lower():
            for k, v in s_vals.items():
                if k.lower() == key.lower():
                    return v
    return None


def _explain_commented(bp, commented_value):
    """Gera explicação de por que uma chave comentada pode ser problema."""
    key = bp["key_name"]
    severity = bp["severity"]

    if bp["is_required"]:
        return (f"A chave {key} é OBRIGATÓRIA mas está comentada (;{key}={commented_value}). "
                f"O servidor pode não funcionar corretamente sem ela.")

    if severity == "critical":
        return (f"A chave {key} é CRÍTICA para o funcionamento e está desabilitada. "
                f"Valor comentado: {commented_value}. Recomendado: {bp['recommended_value'] or 'definir'}.")

    if severity == "warning":
        return (f"A chave {key} está comentada (;{key}={commented_value}). "
                f"Isso pode afetar {bp['description'].lower()}")

    return f"A chave {key} está desabilitada (comentada). Valor: {commented_value}."


def _generate_suggested_ini(parsed, findings, commented_findings, practices, unknown_keys=None):
    """Gera conteúdo de um INI corrigido baseado no arquivo enviado.

    Regra: o arquivo enviado é SEMPRE a base. O sugerido contém:
    - TODAS as chaves originais do arquivo (preservadas)
    - Correções APENAS em chaves critical/warning com valor incorreto
    - Adições APENAS de chaves obrigatórias (is_required) ou critical ausentes
    - Chaves desconhecidas/sujeira são COMENTADAS com aviso
    - Chaves info-level NÃO são adicionadas (são apenas dicas)
    """
    sections = parsed.get("sections", {})
    commented = parsed.get("commented", {})
    ini_type = parsed.get("ini_type", "appserver")

    # Coletar correções necessárias — APENAS critical e warning
    corrections = {}  # {section_lower: {key_lower: {...}}}
    for f in findings:
        if f["status"] not in ("mismatch", "missing"):
            continue
        rec_val = f.get("recommended_value")
        if not rec_val:
            rec_val = "<PREENCHER_VALOR_CORRETO>"

        # Apenas critical/warning impactam o sugerido
        if f["severity"] == "info":
            continue

        # Missing: só adicionar se obrigatório (is_required) ou crítico (critical)
        # Warnings ausentes não entram no INI sugerido para evitar poluição visual (bom senso do auditor)
        if f["status"] == "missing" and not (f.get("is_required") or f["severity"] == "critical"):
            continue

        sec_key = f["section"].lower()
        if sec_key not in corrections:
            corrections[sec_key] = {}
        corrections[sec_key][f["key_name"].lower()] = {
            "key": f["key_name"],
            "value": rec_val,
            "status": f["status"],
            "severity": f["severity"],
        }

    # Descomentar APENAS chaves critical/warning
    for cf in commented_findings:
        if cf["severity"] == "info":
            continue
        rec_val = cf.get("recommended_value")
        if not rec_val:
            rec_val = "<PREENCHER_VALOR_CORRETO>"

        sec_key = cf["section"].lower()
        if sec_key not in corrections:
            corrections[sec_key] = {}
        corrections[sec_key][cf["key_name"].lower()] = {
            "key": cf["key_name"],
            "value": rec_val,
            "status": "uncommented",
            "severity": cf["severity"],
        }

    # Indexar chaves desconhecidas para remoção no sugerido
    unknown_set = set()
    if unknown_keys:
        for uk in unknown_keys:
            unknown_set.add((uk["section"].lower(), uk["key_name"].lower()))

    # Se não há correções NEM chaves desconhecidas — arquivo está OK
    if not corrections and not unknown_set:
        return ""

    # === BOM SENSO DO AUDITOR ===
    # Só gera o arquivo INI sugerido se houver algo realmente relevante para corrigir.
    # Evita poluir a análise com um INI inteiro se o arquivo base já tem bom funcionamento,
    # contendo apenas ausências de chaves "warning" ou "info".
    has_critical = any(c["severity"] == "critical" for sec in corrections.values() for c in sec.values())
    has_mismatch = any(c["status"] == "mismatch" for sec in corrections.values() for c in sec.values())
    
    if not has_critical and not has_mismatch and not unknown_set:
        return ""

    # Montar INI sugerido — arquivo original como base
    lines = []
    lines.append(f"; === INI SUGERIDO (gerado pelo Auditor AtuDIC) ===")
    lines.append(f"; Base: arquivo enviado ({ini_type})")
    lines.append(f"; Correções de impacto + chaves desconhecidas comentadas")
    lines.append(f"; Marcadores: [CORRIGIDO], [DESCOMENTADO], [ADICIONADO-CRITICO], [SUJEIRA]")
    lines.append("")

    for sec_name, sec_keys in sections.items():
        lines.append(f"[{sec_name}]")
        sec_lower = sec_name.lower()
        sec_corrections = corrections.get(sec_lower, {})
        applied_keys = set()

        # Chaves existentes — corrigir, comentar sujeira, ou manter
        for key, value in sec_keys.items():
            key_lower = key.lower()
            if (sec_lower, key_lower) in unknown_set:
                # Chave desconhecida/sujeira — comentar com aviso
                lines.append(f"; [SUJEIRA] Chave desconhecida — verificar se é erro de digitação")
                lines.append(f";{key}={value}")
            elif key_lower in sec_corrections and sec_corrections[key_lower]["status"] == "mismatch":
                rec = sec_corrections[key_lower]
                sev = rec["severity"].upper()
                lines.append(f"; [{sev}][CORRIGIDO] era: {key}={value}")
                lines.append(f"{rec['key']}={rec['value']}")
                applied_keys.add(key_lower)
            else:
                lines.append(f"{key}={value}")

        # Chaves comentadas que devem ser ativadas (critical/warning)
        if sec_lower in (commented or {}):
            for ckey, cval in commented.get(sec_name, commented.get(sec_lower, {})).items():
                key_lower = ckey.lower()
                if key_lower in sec_corrections and key_lower not in applied_keys:
                    rec = sec_corrections[key_lower]
                    sev = rec["severity"].upper()
                    lines.append(f"; [{sev}][DESCOMENTADO] era: ;{ckey}={cval}")
                    lines.append(f"{rec['key']}={rec['value']}")
                    applied_keys.add(key_lower)

        # Chaves CRÍTICAS ausentes — adicionar apenas as essenciais
        for key_lower, rec in sec_corrections.items():
            if key_lower not in applied_keys and rec["status"] == "missing":
                sev = rec["severity"].upper()
                lines.append(f"; [{sev}][ADICIONADO-CRITICO]")
                lines.append(f"{rec['key']}={rec['value']}")

        lines.append("")

    return "\n".join(lines)


def _evaluate_value(current, bp):
    """Avalia se o valor atual está de acordo com a boa prática."""
    vtype = bp.get("value_type", "string")
    recommended = bp.get("recommended_value")

    # Tipo "client_config": escolha do cliente (porta, path, servidor, environment).
    # Apenas verifica existência e valor não-vazio — NUNCA compara valor.
    if vtype == "client_config":
        return current is not None and str(current).strip() != ""

    if not recommended:
        # Sem valor recomendado — só verifica existência
        return True

    current_str = str(current).strip()
    recommended_str = str(recommended).strip()

    if vtype == "boolean":
        true_vals = {"1", "true", "yes", "sim", ".t."}
        false_vals = {"0", "false", "no", "nao", ".f."}
        c_bool = current_str.lower() in true_vals
        r_bool = recommended_str.lower() in true_vals
        return c_bool == r_bool

    if vtype == "integer":
        try:
            c_int = int(current_str)
            # Se tiver range, verificar
            if bp.get("min_value") is not None and bp.get("max_value") is not None:
                return int(bp["min_value"]) <= c_int <= int(bp["max_value"])
            if bp.get("min_value") is not None:
                return c_int >= int(bp["min_value"])
            if bp.get("max_value") is not None:
                return c_int <= int(bp["max_value"])
            return c_int == int(recommended_str)
        except (ValueError, TypeError):
            return False

    if vtype == "range":
        try:
            c_int = int(current_str)
            min_v = int(bp.get("min_value", 0))
            max_v = int(bp.get("max_value", 999999))
            return min_v <= c_int <= max_v
        except (ValueError, TypeError):
            return False

    if vtype == "enum":
        enum_vals = bp.get("enum_values", "[]")
        if isinstance(enum_vals, str):
            try:
                enum_vals = json.loads(enum_vals)
            except (json.JSONDecodeError, TypeError):
                enum_vals = [v.strip() for v in enum_vals.split(",")]
        return current_str.lower() in [str(v).lower() for v in enum_vals]

    # Tipo "contains": verifica se o valor recomendado está CONTIDO na lista (ex: Jobs=A,B,C contém B)
    if vtype == "contains":
        items = {v.strip().lower() for v in current_str.split(",")}
        return recommended_str.lower() in items

    # string: comparação case-insensitive
    return current_str.lower() == recommended_str.lower()


# =================================================================
# INTEGRAÇÃO LLM (apenas para gerar insights humanizados)
# =================================================================

def generate_llm_insights(findings, ini_type, environment_id=None, commented_findings=None,
                          ini_role=None, parsed=None, filename=None, unknown_keys=None):
    """Gera resumo executivo humanizado usando LLM configurado.

    O LLM SEMPRE atua quando configurado — recebe ficha técnica com dados
    reais do arquivo para evitar alucinação.
    Retorna None se LLM não configurado — o módulo funciona 100% sem LLM.
    """
    ini_role = ini_role or "standalone"

    # Tentar carregar LLM
    try:
        import app.utils.crypto as crypto
        from app.services.llm_providers import create_provider_from_config
    except ImportError:
        logger.debug("Módulo LLM não disponível")
        return None

    if not environment_id:
        return None

    # Buscar configuração LLM do ambiente
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT provider_id, api_key_encrypted, model, base_url, options
            FROM llm_provider_configs
            WHERE environment_id = %s AND is_active = TRUE
            ORDER BY id LIMIT 1
            """,
            (environment_id,),
        )
        row = cursor.fetchone()
    finally:
        release_db_connection(conn)

    if not row:
        return None

    # Descriptografar API key
    api_key = None
    if row.get("api_key_encrypted"):
        try:
            api_key = crypto.token_encryption.decrypt_token(row["api_key_encrypted"])
        except Exception:
            logger.warning("Erro ao descriptografar API key para auditor")
            return None

    config = {
        "provider_id": row["provider_id"],
        "api_key": api_key,
        "model": row.get("model"),
        "base_url": row.get("base_url"),
        "options": row.get("options"),
    }

    try:
        provider = create_provider_from_config(config)
    except Exception as e:
        logger.warning("Erro ao criar provider LLM: %s", e)
        return None

    # Separar findings por categoria para contexto completo
    problems = [f for f in findings if f["status"] in ("mismatch", "missing")]
    ok_items = [f for f in findings if f["status"] == "ok"]

    # Montar ficha técnica + problemas para o LLM
    user_content = _build_user_prompt(
        findings, commented_findings, ini_type, ini_role,
        parsed=parsed, filename=filename, ok_count=len(ok_items),
        unknown_keys=unknown_keys,
    )

    system_prompt = _build_specialist_prompt(ini_type, ini_role)

    messages = [{"role": "user", "content": user_content}]

    # Log diagnóstico: verificar se o prompt está sendo montado corretamente
    logger.info(
        "Auditor LLM: provider=%s, model=%s, ini_type=%s, ini_role=%s, "
        "findings=%d, system_len=%d, user_len=%d",
        row["provider_id"], row.get("model"), ini_type, ini_role,
        len(findings), len(system_prompt), len(user_content),
    )
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("Auditor LLM system_prompt (primeiros 500 chars): %s", system_prompt[:500])
        logger.debug("Auditor LLM user_content (primeiros 500 chars): %s", user_content[:500])

    try:
        result = provider.chat(
            messages,
            system_prompt=system_prompt,
            temperature=0.1,
            max_tokens=2000,
        )
        summary = result.get("content", "")

        # Validação anti-alucinação: detecta se LLM ignorou o contexto Protheus
        if _is_hallucinated_response(summary, ini_type):
            logger.warning(
                "LLM retornou análise genérica (alucinação detectada) — descartando resposta. "
                "Modelo: %s, provider: %s",
                result.get("model", "?"), row["provider_id"],
            )
            return {
                "summary": _build_fallback_summary(findings, commented_findings,
                                                   ini_type, ini_role, ok_count=len(ok_items),
                                                   unknown_keys=unknown_keys),
                "provider": "fallback",
                "model": "deterministic",
            }

        return {
            "summary": summary,
            "provider": row["provider_id"],
            "model": result.get("model", row.get("model")),
        }
    except Exception as e:
        logger.warning("Erro ao gerar insights LLM: %s", e)
        return None


def _is_hallucinated_response(summary, ini_type):
    """Detecta se a resposta do LLM é uma alucinação genérica.

    Verifica sinais claros de que o modelo ignorou o contexto Protheus:
    - Menção a tecnologias erradas (Apache, Nginx, IIS)
    - Ausência total de termos Protheus
    - Formato categorizado genérico em vez do resumo executivo
    """
    if not summary:
        return True

    lower = summary.lower()

    # Sinais de alucinação: tecnologias que NÃO são Protheus
    hallucination_markers = [
        "apache", "nginx", "iis ", "tomcat", "caddy",
        "servidor web genérico", "servidor web,",
        "provavelmente um",  # "provavelmente um Apache/Nginx"
    ]
    for marker in hallucination_markers:
        if marker in lower:
            return True

    # Se a resposta não menciona NENHUM termo Protheus, é suspeita
    protheus_terms = ["protheus", "totvs", "appserver", "dbaccess", "smartclient",
                      "tss", "environment", "rpo", "ini", "licenseserver"]
    has_protheus = any(term in lower for term in protheus_terms)
    if not has_protheus:
        return True

    return False


def _build_fallback_summary(findings, commented_findings, ini_type, ini_role,
                            ok_count=0, unknown_keys=None):
    """Gera resumo determinístico quando LLM falha ou alucina.

    Produz uma análise estruturada usando apenas os dados reais da auditoria,
    sem depender de LLM.
    """
    problems = [f for f in findings if f["status"] in ("mismatch", "missing")]
    critical = [p for p in problems if p["severity"] == "critical"]
    warning = [p for p in problems if p["severity"] == "warning"]

    type_labels = {
        "appserver": "AppServer Protheus",
        "dbaccess": "DBAccess",
        "tss": "TSS (transmissão fiscal)",
        "smartclient": "SmartClient",
    }
    title = type_labels.get(ini_type, "Arquivo INI Protheus")

    role_labels = {
        "broker_http": "Broker HTTP/WebApp",
        "broker_soap": "Broker SOAP",
        "broker_rest": "Broker REST",
        "slave": "Application Server",
        "slave_ws": "Application Server com WS SOAP",
        "slave_rest": "Application Server com REST",
        "job_server": "Servidor de Jobs",
        "rest_server": "Servidor REST",
        "standalone": "Standalone",
        "standalone_multi_env": "Multi-environment",
        "tss": "TSS Fiscal",
        "dbaccess_master": "DBAccess Master",
        "dbaccess_slave": "DBAccess Slave",
        "dbaccess_standalone": "DBAccess Standalone",
    }
    role_label = role_labels.get(ini_role, ini_role)

    lines = [f"### {title} ({role_label})"]

    total = ok_count + len(problems)
    if not problems:
        lines.append("Arquivo em conformidade — nenhum problema detectado na auditoria.")
    elif not critical:
        lines.append(f"Arquivo em bom estado. {ok_count}/{total} chaves OK, "
                     f"com {len(warning)} alertas menores.")
    else:
        lines.append(f"Atenção necessária: {len(critical)} problema(s) crítico(s) "
                     f"e {len(warning)} alerta(s) entre {total} chaves avaliadas.")

    if critical or warning:
        lines.append("")
        lines.append("### Pontos de atenção")
        shown = 0
        for p in critical + warning:
            if shown >= 5:
                break
            sev = "CRÍTICO" if p["severity"] == "critical" else "ALERTA"
            status = "ausente" if p["status"] == "missing" else "incorreto"
            desc = p.get("description", "")
            bullet = f"- **[{sev}]** `[{p['section']}] {p['key_name']}` — {status}"
            if p.get("current_value") is not None and p.get("recommended_value"):
                bullet += f" (atual: `{p['current_value']}`, recomendado: `{p['recommended_value']}`)"
            elif p.get("recommended_value"):
                bullet += f" (recomendado: `{p['recommended_value']}`)"
            if desc:
                bullet += f". {desc}"
            lines.append(bullet)
            shown += 1

    if unknown_keys:
        lines.append("")
        lines.append("### Sujeira detectada")
        for uk in unknown_keys[:5]:
            lines.append(f"- `[{uk['section']}] {uk['key_name']}` — chave não documentada na TDN")

    if commented_findings:
        commented_critical = [cf for cf in commented_findings if cf["severity"] == "critical"]
        if commented_critical:
            lines.append("")
            lines.append("### Chaves comentadas importantes")
            for cf in commented_critical[:3]:
                lines.append(f"- `[{cf['section']}] ;{cf['key_name']}={cf['commented_value']}`")

    lines.append("")
    lines.append("*Análise gerada automaticamente a partir das regras TDN.*")

    return "\n".join(lines)


def _build_user_prompt(findings, commented_findings, ini_type, ini_role,
                      parsed=None, filename=None, ok_count=0, unknown_keys=None):
    """Monta user prompt com FICHA TÉCNICA extraída do arquivo real.

    A ficha técnica ancora o LLM em dados reais — seções, servidores, portas
    e bancos que EXISTEM no arquivo. Isso evita alucinação.

    IMPORTANTE: As instruções de formato são replicadas aqui (não apenas no
    system prompt) porque modelos mais leves ignoram systemInstruction.
    """
    sections = parsed.get("sections", {}) if parsed else {}
    problems = [f for f in findings if f["status"] in ("mismatch", "missing")]
    critical = [p for p in problems if p["severity"] == "critical"]
    warning = [p for p in problems if p["severity"] == "warning"]
    info = [p for p in problems if p["severity"] == "info"]

    # Âncora de contexto — reforça no user prompt para modelos que ignoram system prompt
    type_labels = {
        "appserver": "TOTVS Protheus Application Server",
        "dbaccess": "TOTVS DBAccess",
        "tss": "TOTVS TSS (transmissão fiscal)",
        "smartclient": "TOTVS SmartClient",
    }
    type_label = type_labels.get(ini_type, "TOTVS Protheus")

    lines = [
        f"CONTEXTO: Este é um arquivo INI do **{type_label}** (papel: {ini_role}). "
        "NÃO é Apache, Nginx ou qualquer outro servidor web genérico. "
        "É um ERP TOTVS Protheus.\n",
        "## Ficha Técnica do Arquivo",
    ]
    lines.append(f"- **Arquivo:** {filename or 'desconhecido'}")
    lines.append(f"- **Tipo detectado:** {ini_type}")
    lines.append(f"- **Papel na infraestrutura:** {ini_role}")

    # Seções encontradas
    sec_names = list(sections.keys())
    lines.append(f"- **Seções encontradas ({len(sec_names)}):** {', '.join(f'[{s}]' for s in sec_names)}")

    # Extrair servidores, portas, bancos reais do arquivo
    infra_keys = {"server", "dbserver", "masterserver", "port", "dbport", "masterport",
                  "database", "alias", "dbalias"}
    for sec_name, sec_data in sections.items():
        if not isinstance(sec_data, dict):
            continue
        for key, val in sec_data.items():
            if key.lower() in infra_keys and val:
                lines.append(f"- **{key} ({sec_name}):** {val}")

    # Panorama dos findings
    lines.append("")
    lines.append(f"## Panorama da Auditoria")
    lines.append(f"- {ok_count} OK, {len(critical)} críticos, {len(warning)} alertas, {len(info)} info")
    lines.append("")

    if not problems and not (commented_findings or []):
        lines.append("NENHUM PROBLEMA ENCONTRADO — arquivo em conformidade.")
    else:
        lines.append("## Problemas Encontrados")
        lines.append("")
        for p in problems:
            severity = p["severity"].upper()
            status = "AUSENTE" if p["status"] == "missing" else "INCORRETO"
            line = f"[{severity}] [{p['section']}] {p['key_name']}: {status}"
            if p["current_value"] is not None:
                line += f" (atual: {p['current_value']}"
                if p["recommended_value"]:
                    line += f", recomendado: {p['recommended_value']}"
                line += ")"
            elif p["recommended_value"]:
                line += f" (recomendado: {p['recommended_value']})"
            if p.get("description"):
                line += f" — {p['description']}"
            lines.append(line)

        if commented_findings:
            lines.append("")
            lines.append(f"Chaves COMENTADAS ({len(commented_findings)}):")
            for cf in commented_findings:
                line = f"[{cf['severity'].upper()}] [{cf['section']}] ;{cf['key_name']}={cf['commented_value']}"
                if cf.get("reason"):
                    line += f" — {cf['reason']}"
                lines.append(line)

    # Chaves desconhecidas/sujeira
    if unknown_keys:
        lines.append("")
        lines.append(f"## Chaves Desconhecidas ({len(unknown_keys)})")
        lines.append("Estas chaves NÃO existem na documentação TDN. Podem ser erro de digitação ou sujeira:")
        for uk in unknown_keys:
            lines.append(f"- [{uk['section']}] {uk['key_name']}={uk['value']} — {uk['reason']}")

    # Instruções de formato reforçadas no final do user prompt
    # (modelos mais leves prestam mais atenção ao final da mensagem)
    lines.append("")
    lines.append("---")
    lines.append("## INSTRUÇÕES DE RESPOSTA (OBRIGATÓRIO)")
    lines.append(f"Este arquivo é do **{type_label}** — NÃO é Apache, Nginx ou servidor web genérico.")
    lines.append("Responda EXATAMENTE neste formato markdown, sem desviar:")
    lines.append("")
    lines.append("### [Título: tipo do servidor, ex: 'AppServer Protheus', 'Broker HTTP', 'TSS Fiscal']")
    lines.append("[1-2 frases sobre estado geral]")
    lines.append("")
    lines.append("### Pontos de atenção")
    lines.append("[máximo 5 bullets com problemas REAIS da auditoria acima]")
    lines.append("")
    lines.append("### Dicas")
    lines.append("[máximo 3 bullets opcionais]")
    lines.append("")
    lines.append("REGRAS: máximo 200 palavras. NÃO invente dados. NÃO organize por categorias "
                 "genéricas (Segurança, Cache, etc). Use APENAS os dados da ficha técnica acima.")

    return "\n".join(lines)


def _build_specialist_prompt(ini_type, ini_role="standalone"):
    """Constrói system prompt especializado em configuração Protheus.

    O prompt é contextualizado pelo TIPO (appserver/dbaccess/tss) e pelo PAPEL
    funcional (broker, slave, job_server, rest_server, standalone, etc).
    """
    type_context = {
        "appserver": "arquivo appserver.ini do TOTVS Protheus Application Server",
        "dbaccess": "arquivo dbaccess.ini do TOTVS DBAccess",
        "tss": "arquivo appserver.ini do TOTVS TSS (TOTVS Service SOA / transmissão fiscal)",
        "smartclient": "arquivo smartclient.ini do TOTVS SmartClient",
    }

    role_context = {
        "tss": (
            "**TSS — TOTVS Service SOA (transmissão fiscal)**\n"
            "Servidor dedicado à transmissão de documentos fiscais eletrônicos (NFe, CTe, MDFe, NFSe).\n"
            "IMPORTANTE: O TSS é DIFERENTE do AppServer Protheus comum:\n"
            "- O environment principal geralmente se chama [SPED] (não [PRODUCAO])\n"
            "- Possui seções exclusivas: [JOB_WS], [TSSTASKPROC], [IPC_SMTP], [IPC_DISTMAIL]\n"
            "- [SSLConfigure] é CRÍTICO — TLS 1.2 obrigatório para comunicação com SEFAZ\n"
            "- TSSSECURITY controla autenticação dos web services do TSS\n"
            "- SPED_SAVEWSDL e XMLSAVEALL são chaves de DEBUG — devem estar desabilitadas em produção\n"
            "- NÃO confundir seções do TSS com seções do AppServer Protheus padrão"
        ),
        "broker_http": (
            "**Broker HTTP/WebApp**\n"
            "Balanceador de carga para conexões WebApp (HTML5).\n"
            "- Distribui conexões entre servidores Protheus via [BALANCE_HTTP]\n"
            "- NÃO possui [Environment], [DBAccess] nem jobs — é apenas balanceador\n"
            "- A partir do release 12.1.2410, WebApp é o modo único de acesso ao Protheus"
        ),
        "broker_soap": (
            "**Broker de Web Services SOAP**\n"
            "Balanceador de carga para Web Services SOAP do Protheus.\n"
            "- Distribui requisições entre servidores WS via [BALANCE_WEB_SERVICES]\n"
            "- NÃO possui [Environment] nem [DBAccess] — apenas roteia"
        ),
        "broker_rest": (
            "**Broker de Web Services REST**\n"
            "Balanceador de carga para APIs REST do Protheus.\n"
            "- Distribui requisições REST entre servidores backend via [BALANCE_WEB_SERVICES]"
        ),
        "slave": (
            "**Application Server Protheus**\n"
            "Servidor que atende conexões SmartClient/WebApp.\n"
            "- Possui environment(s) configurado(s) com RPO e conexão a banco\n"
            "- Conecta a LicenseServer e DBAccess"
        ),
        "slave_ws": (
            "**Application Server Protheus com Web Services SOAP configurado**\n"
            "Servidor com exposição de métodos WS (SOAP) via JOB_WS.\n"
            "- Possui JOB_WS com SIGAWEB para atendimento de requisições WS\n"
            "- Seções de host:porta mapeiam o roteamento HTTP para o job"
        ),
        "slave_rest": (
            "**Application Server Protheus com APIs REST configurado**\n"
            "Servidor com exposição de APIs REST via [HTTPREST].\n"
            "- Configuração [HTTPJOB] + [HTTPREST] + [HTTPURI] para exposição das APIs\n"
            "- PrepareIn na [HTTPURI] define empresa/filial de conexão automática"
        ),
        "job_server": (
            "**Servidor de Jobs Protheus**\n"
            "Servidor dedicado a executar jobs/schedulers automatizados.\n"
            "- [OnStart] lista os jobs a inicializar: cada job tem sua seção com Main e Environment\n"
            "- NÃO atende SmartClient/WebApp — apenas processa tarefas em background\n"
            "- Jobs customizados (U_*) são rotinas AdvPL da empresa"
        ),
        "rest_server": (
            "**Application Server Protheus com APIs REST**\n"
            "Servidor com APIs REST do Protheus configuradas.\n"
            "- Configuração [HTTPJOB] + [HTTPREST] + [HTTPURI]\n"
            "- PrepareIn na [HTTPURI] define empresa/filial de conexão automática"
        ),
        "standalone": (
            "**Application Server Protheus**\n"
            "Servidor Protheus autônomo.\n"
            "- Atende conexões SmartClient/WebApp diretamente\n"
            "- Pode ter um ou mais environments configurados"
        ),
        "standalone_multi_env": (
            "**Application Server Protheus com múltiplos environments**\n"
            "Servidor com vários environments (equipes de sustentação, desenvolvimento, etc).\n"
            "- Cada environment pode apontar para RPO diferente (customizado por equipe)\n"
            "- APP_ENVIRONMENT define qual é o environment padrão"
        ),
        "dbaccess_master": (
            "**DBAccess Master (distribuído)**\n"
            "Gerencia distribuição de conexões entre servidores DBAccess.\n"
            "- mode=master na [General]\n"
            "- ThreadMin/ThreadMax/ThreadInc dimensionam capacidade"
        ),
        "dbaccess_slave": (
            "**DBAccess (distribuído)**\n"
            "Servidor DBAccess que atende conexões de banco via master.\n"
            "- mode=slave, masterserver e masterport apontam para o master"
        ),
        "dbaccess_standalone": (
            "**DBAccess**\n"
            "Servidor DBAccess autônomo.\n"
            "- Atende todas as conexões diretamente"
        ),
    }

    type_desc = type_context.get(ini_type, "arquivo INI de configuração TOTVS Protheus")
    role_desc = role_context.get(ini_role, role_context.get("standalone"))

    return (
        "Você é um especialista sênior em infraestrutura TOTVS Protheus com 15+ anos de experiência "
        "em configuração, tunning e troubleshooting.\n\n"
        f"## Arquivo analisado\n{type_desc}\n\n{role_desc}\n\n"
        "## Princípios da análise:\n"
        "- **Portas, paths, servidores, environments e nomes de banco são ESCOLHA DO CLIENTE** — "
        "NUNCA critique o valor de uma porta ou path. Critique apenas se estiver AUSENTE quando obrigatório\n"
        "- A seção [Environment] tem nome customizado pelo cliente (ex: [PRODUCAO], [SPED], [APPJOB01])\n"
        "- O encoding OBRIGATÓRIO dos INIs é ANSI (Windows-1252 / CP1252)\n"
        "- Chaves comentadas (;key=value) podem ser intencionais (debug) ou esquecidas\n"
        "- MaxStringSize DEVE ser 10 (100 é valor antigo incorreto, 40 ou 8 são incompatíveis)\n"
        "- SSL2=0, SSL3=0, TLS1_2=1 são obrigatórios para qualquer comunicação SSL\n"
        "- Cada tipo de servidor (broker, slave, job, TSS) tem configurações específicas — "
        "não exija seções que não fazem sentido para o papel do arquivo\n\n"
        "## Premissas OBRIGATÓRIAS (respeite SEMPRE):\n"
        "- O arquivo enviado JÁ FUNCIONAVA em produção — o objetivo é identificar riscos, não reescrever\n"
        "- **NUNCA use a palavra 'slave'** — o controle de quem é secundário é implícito pelo broker\n"
        "- Se o appserver tem REST ou SOAP configurado, apenas MENCIONE que tem — não classifique como tipo\n"
        "- **NUNCA critique valores de**: portas, paths, servidores, nomes de banco, environments, aliases, "
        "ThreadMin/Max/Inc, Instances, métricas de performance, nomes de serviço, LicenseServer/Port. "
        "Estes são ESCOLHA DO CLIENTE conforme infraestrutura\n"
        "- Seções de drivers de banco (MSSQL, Oracle, PostgreSQL) só avalia SE EXISTIREM no arquivo\n"
        "- Seções como [Broker], [WebAgent], [HTTPREST], [FTP] são OPCIONAIS — só avalie se existirem\n"
        "- Chaves opcionais ausentes NÃO são erro — no máximo uma dica sutil\n"
        "- MaxStringSize NÃO se aplica a DBAccess\n"
        "- **TSS é DIFERENTE do AppServer Protheus**: tem seções exclusivas ([JOB_WS], [TSSTASKPROC], "
        "[IPC_SMTP]), environment [SPED] em vez de [PRODUCAO], e chaves como TSSSECURITY e SPED_SAVEWSDL. "
        "NÃO confundir regras de AppServer com regras de TSS\n"
        "- Chaves como ConsoleMaxSize, InactiveTimeout, ServerMemoryLimit com valores diferentes "
        "do padrão NÃO são erro — o cliente ajustou conforme ambiente\n\n"
        "## Formato da resposta — RESUMO EXECUTIVO (OBRIGATÓRIO):\n"
        "Responda APENAS neste formato. NÃO faça análise item-por-item. NÃO invente dados.\n\n"
        "### Título (1 linha)\n"
        "Descreva o tipo de configuração (ex: 'TSS com REST configurado', 'AppServer Protheus', "
        "'Broker HTTP/WebApp'). NÃO mencione nomes de servidores, IPs ou portas no título. "
        "NUNCA use a palavra 'slave'. Se tem REST/SOAP, apenas mencione que está configurado.\n\n"
        "### Estado geral (1-2 frases)\n"
        "Avaliação concisa da saúde do arquivo para o papel detectado.\n\n"
        "### Pontos de atenção (máximo 5 bullets)\n"
        "APENAS itens que REALMENTE impactam. Se a auditoria reportou algo que não faz sentido "
        "para o papel, IGNORE.\n\n"
        "### Sujeira detectada (se houver)\n"
        "Se a ficha técnica listar 'Chaves Desconhecidas', MENCIONE-AS aqui. "
        "São chaves que NÃO existem na documentação TDN — possíveis erros de digitação, "
        "chaves obsoletas ou configurações inválidas. Liste as chaves e a seção onde foram encontradas.\n\n"
        "### Dicas (opcional, máximo 3 bullets)\n"
        "Sugestões práticas e rápidas.\n\n"
        "REGRAS ABSOLUTAS:\n"
        "- Máximo 200 palavras no total\n"
        "- NÃO repita 'O que está errado / Por que importa / Como corrigir' — os findings já mostram isso\n"
        "- NÃO invente nomes de servidores, IPs ou paths que não estejam na ficha técnica\n"
        "- Use APENAS dados da ficha técnica fornecida no prompt do usuário\n"
        "- Português brasileiro, markdown"
    )


def _build_rules_context(problems, commented_findings=None):
    """Constrói contexto das regras de boas práticas para o LLM."""
    lines = ["## Referência de Boas Práticas (base de conhecimento TDN)"]
    lines.append("")

    # Agrupar por seção para contexto organizado
    by_section = {}
    for p in problems:
        sec = p["section"]
        if sec not in by_section:
            by_section[sec] = []
        entry = f"- **{p['key_name']}**"
        if p.get("description"):
            entry += f": {p['description']}"
        if p.get("tdn_url"):
            entry += f" [TDN]({p['tdn_url']})"
        by_section[sec].append(entry)

    if commented_findings:
        for cf in commented_findings:
            sec = cf["section"]
            if sec not in by_section:
                by_section[sec] = []
            entry = f"- **;{cf['key_name']}** (comentada): {cf.get('reason', cf.get('description', ''))}"
            if cf.get("tdn_url"):
                entry += f" [TDN]({cf['tdn_url']})"
            by_section[sec].append(entry)

    for sec, entries in by_section.items():
        lines.append(f"### [{sec}]")
        lines.extend(entries)
        lines.append("")

    return "\n".join(lines)


def _format_problems_for_llm(problems, ini_type, commented_findings=None, ini_role=None, ok_count=0):
    """Formata panorama completo para o LLM gerar resumo executivo."""
    role_label = ini_role or "standalone"
    critical = [p for p in problems if p["severity"] == "critical"]
    warning = [p for p in problems if p["severity"] == "warning"]
    info = [p for p in problems if p["severity"] == "info"]

    lines = [
        f"Arquivo: {ini_type}.ini",
        f"Papel detectado: {role_label}",
        f"Panorama: {ok_count} OK, {len(critical)} críticos, {len(warning)} alertas, {len(info)} info",
        "",
    ]

    if not problems and not (commented_findings or []):
        lines.append("NENHUM PROBLEMA ENCONTRADO — arquivo em conformidade com as boas práticas avaliadas.")
        return "\n".join(lines)

    lines.append("Problemas encontrados:")
    lines.append("")

    for p in problems:
        severity = p["severity"].upper()
        status = "AUSENTE" if p["status"] == "missing" else "INCORRETO"
        line = f"[{severity}] [{p['section']}] {p['key_name']}: {status}"
        if p["current_value"] is not None:
            line += f" (atual: {p['current_value']}"
            if p["recommended_value"]:
                line += f", recomendado: {p['recommended_value']}"
            line += ")"
        elif p["recommended_value"]:
            line += f" (recomendado: {p['recommended_value']})"
        if p.get("description"):
            line += f" — {p['description']}"
        lines.append(line)

    if commented_findings:
        lines.append("")
        lines.append(f"Chaves COMENTADAS detectadas ({len(commented_findings)}):")
        for cf in commented_findings:
            line = f"[{cf['severity'].upper()}] [{cf['section']}] ;{cf['key_name']}={cf['commented_value']}"
            if cf.get("reason"):
                line += f" — {cf['reason']}"
            lines.append(line)

    return "\n".join(lines)


# =================================================================
# ORQUESTRADOR PRINCIPAL
# =================================================================

def run_audit(content, filename, user_id=None, environment_id=None):
    """Executa auditoria completa: parse → compare → LLM → salvar.

    Returns:
        dict com resultado completo da auditoria
    """
    # 1. Parsear INI
    parsed = parse_ini_file(content, filename)
    ini_type = parsed["ini_type"]
    ini_role = parsed.get("ini_role", "standalone")

    # 2. Salvar auditoria como pendente
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO ini_audits
                (environment_id, user_id, filename, ini_type, raw_content,
                 parsed_json, total_sections, total_keys, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending')
            RETURNING id
            """,
            (
                environment_id, user_id, filename, ini_type, content,
                json.dumps(parsed["sections"], ensure_ascii=False),
                parsed["meta"]["total_sections"],
                parsed["meta"]["total_keys"],
            ),
        )
        audit_id = cursor.fetchone()["id"]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        release_db_connection(conn)

    # 3. Comparar contra boas práticas
    comparison = compare_against_best_practices(parsed, ini_type)

    # 4. Salvar resultados detalhados
    conn = get_db()
    cursor = conn.cursor()
    try:
        for f in comparison["findings"]:
            cursor.execute(
                """
                INSERT INTO ini_audit_results
                    (audit_id, best_practice_id, section, key_name,
                     current_value, recommended_value, severity, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    audit_id, f.get("best_practice_id"), f["section"], f["key_name"],
                    f["current_value"], f["recommended_value"], f["severity"], f["status"],
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        release_db_connection(conn)

    # 5. Gerar insights via LLM (opcional — inclui chaves comentadas e papel no prompt)
    llm_result = generate_llm_insights(
        comparison["findings"], ini_type, environment_id,
        commented_findings=comparison.get("commented_findings"),
        ini_role=ini_role,
        parsed=parsed,
        filename=filename,
        unknown_keys=comparison.get("unknown_keys", []),
    )

    # 6. Atualizar audit com score e summary
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE ini_audits
            SET score = %s, llm_summary = %s, llm_provider = %s,
                llm_model = %s, status = 'analyzed'
            WHERE id = %s
            """,
            (
                comparison["score"],
                llm_result["summary"] if llm_result else None,
                llm_result["provider"] if llm_result else None,
                llm_result["model"] if llm_result else None,
                audit_id,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        release_db_connection(conn)

    return {
        "audit_id": audit_id,
        "filename": filename,
        "ini_type": ini_type,
        "ini_role": ini_role,
        "score": comparison["score"],
        "summary": comparison["summary"],
        "findings": comparison["findings"],
        "commented_findings": comparison.get("commented_findings", []),
        "commented_sections": parsed.get("commented_sections", []),
        "dirty_lines": parsed.get("dirty_lines", []),
        "unknown_keys": comparison.get("unknown_keys", []),
        "encoding_info": parsed.get("encoding_info", {}),
        "suggested_ini": comparison.get("suggested_ini", ""),
        "llm_summary": llm_result["summary"] if llm_result else None,
        "llm_provider": llm_result["provider"] if llm_result else None,
        "llm_model": llm_result["model"] if llm_result else None,
        "parsed": {
            "total_sections": parsed["meta"]["total_sections"],
            "total_keys": parsed["meta"]["total_keys"],
            "total_commented": parsed["meta"].get("total_commented", 0),
            "total_commented_sections": parsed["meta"].get("total_commented_sections", 0),
            "total_dirty_lines": parsed["meta"].get("total_dirty_lines", 0),
        },
    }


# =================================================================
# CONSULTAS (histórico e detalhes)
# =================================================================

def get_audit_history(environment_id=None, limit=20, offset=0):
    """Retorna histórico de auditorias."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        conditions = []
        params = []

        if environment_id:
            conditions.append("environment_id = %s")
            params.append(environment_id)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        cursor.execute(f"SELECT COUNT(*) as total FROM ini_audits {where}", params)
        total = cursor.fetchone()["total"]

        cursor.execute(
            f"""
            SELECT id, environment_id, user_id, filename, ini_type,
                   total_sections, total_keys, score, status,
                   llm_provider, llm_model, created_at
            FROM ini_audits {where}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )

        audits = []
        for row in cursor.fetchall():
            audit = dict(row)
            if audit.get("created_at"):
                audit["created_at"] = audit["created_at"].isoformat()
            audits.append(audit)

        return {"audits": audits, "total": total}
    finally:
        release_db_connection(conn)


def get_audit_detail(audit_id):
    """Retorna detalhes completos de uma auditoria."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM ini_audits WHERE id = %s", (audit_id,))
        audit = cursor.fetchone()
        if not audit:
            return None

        audit = dict(audit)
        if audit.get("created_at"):
            audit["created_at"] = audit["created_at"].isoformat()

        # Buscar resultados detalhados
        cursor.execute(
            """
            SELECT r.*, bp.description as bp_description, bp.tdn_url as bp_tdn_url
            FROM ini_audit_results r
            LEFT JOIN ini_best_practices bp ON r.best_practice_id = bp.id
            WHERE r.audit_id = %s
            ORDER BY
                CASE r.severity
                    WHEN 'critical' THEN 1
                    WHEN 'warning' THEN 2
                    ELSE 3
                END,
                r.section, r.key_name
            """,
            (audit_id,),
        )

        results = []
        for row in cursor.fetchall():
            r = dict(row)
            if r.get("created_at"):
                r["created_at"] = r["created_at"].isoformat()
            results.append(r)

        audit["results"] = results
        return audit
    finally:
        release_db_connection(conn)


# =================================================================
# SEED DE BOAS PRÁTICAS
# =================================================================

def seed_best_practices():
    """Popula boas práticas a partir do conhecimento TDN + regras conhecidas.

    Retorna quantidade de regras inseridas.
    """
    rules = _get_known_rules()
    inserted = 0

    conn = get_db()
    cursor = conn.cursor()
    try:
        for rule in rules:
            try:
                cursor.execute(
                    """
                    INSERT INTO ini_best_practices
                        (ini_type, section, key_name, recommended_value,
                         value_type, min_value, max_value, enum_values,
                         severity, description, tdn_url, is_required)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ini_type, section, key_name) DO UPDATE SET
                        recommended_value = EXCLUDED.recommended_value,
                        value_type = EXCLUDED.value_type,
                        min_value = EXCLUDED.min_value,
                        max_value = EXCLUDED.max_value,
                        enum_values = EXCLUDED.enum_values,
                        severity = EXCLUDED.severity,
                        description = EXCLUDED.description,
                        tdn_url = EXCLUDED.tdn_url,
                        is_required = EXCLUDED.is_required
                    """,
                    (
                        rule["ini_type"], rule["section"], rule["key_name"],
                        rule.get("recommended_value"),
                        rule.get("value_type", "string"),
                        rule.get("min_value"),
                        rule.get("max_value"),
                        json.dumps(rule["enum_values"]) if rule.get("enum_values") else None,
                        rule.get("severity", "info"),
                        rule.get("description"),
                        rule.get("tdn_url"),
                        rule.get("is_required", False),
                    ),
                )
                if cursor.rowcount > 0:
                    inserted += 1
            except Exception as e:
                logger.warning("Erro ao inserir regra %s.%s: %s", rule["section"], rule["key_name"], e)
                conn.rollback()
                continue

        # Limpar regras órfãs do banco que não existem mais no código
        valid_keys = {(r["ini_type"], r["section"], r["key_name"]) for r in rules}
        cursor.execute("SELECT id, ini_type, section, key_name FROM ini_best_practices")
        orphans = []
        for row in cursor.fetchall():
            key = (row["ini_type"], row["section"], row["key_name"])
            if key not in valid_keys:
                orphans.append(row["id"])
        if orphans:
            # Limpar referências FK em ini_audit_results antes de deletar
            cursor.execute(
                "UPDATE ini_audit_results SET best_practice_id = NULL WHERE best_practice_id = ANY(%s)",
                (orphans,),
            )
            cursor.execute(
                "DELETE FROM ini_best_practices WHERE id = ANY(%s)", (orphans,)
            )
            logger.info("Seed: %d regras órfãs removidas do banco", len(orphans))

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        release_db_connection(conn)

    logger.info("Seed de boas práticas: %d regras inseridas/atualizadas", inserted)
    return inserted


def _get_known_rules():
    """Retorna lista de regras conhecidas de boas práticas para INIs Protheus.

    Regras extraídas da documentação TDN (TOTVS Developer Network) e
    experiência prática com ambientes Protheus em produção.
    """
    rules = []

    def r(section, key, **kwargs):
        rules.append({
            "ini_type": kwargs.get("ini_type", "appserver"),
            "section": section, "key_name": key,
            "recommended_value": kwargs.get("val"),
            "value_type": kwargs.get("vtype", "string"),
            "min_value": kwargs.get("min_val"), "max_value": kwargs.get("max_val"),
            "enum_values": kwargs.get("enum"),
            "severity": kwargs.get("sev", "info"),
            "description": kwargs.get("desc", f"Chave {key} da seção [{section}]."),
            "tdn_url": kwargs.get("url"),
            "is_required": kwargs.get("req", False),
        })

    # =====================================================
    # APPSERVER.INI — [General]
    # =====================================================
    r("General", "MaxStringSize", val="10", vtype="integer", min_val="10", sev="critical", req=True,
      desc="Tamanho máximo de strings. Deve ser 10 para compatibilidade com campos memo/CLOB.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=161349793")
    r("General", "ConsoleLog", val="1", vtype="boolean", sev="warning",
      desc="Habilita log no console. Essencial para diagnóstico.",
      url="https://tdn.totvs.com/display/tec/ConsoleLog")
    r("General", "ConsoleMaxSize", vtype="integer", min_val="50", max_val="500", sev="info",
      desc="Tamanho máximo do arquivo de log em MB. Evita consumo excessivo de disco.",
      url="https://tdn.totvs.com/display/tec/ConsoleMaxSize")
    r("General", "ConsoleLogDate", val="1", vtype="boolean", sev="info",
      desc="Adiciona data no nome do arquivo de log do console.",
      url="https://tdn.totvs.com/display/tec/ConsoleLogDate")
    r("General", "LogTimeStamp", val="1", vtype="boolean", sev="warning",
      desc="Adiciona timestamp nos logs. Essencial para rastreabilidade.",
      url="https://tdn.totvs.com/display/tec/LogTimeStamp")
    r("General", "ShowIPClient", val="1", vtype="boolean", sev="info",
      desc="Exibe IP do cliente nos logs. Útil para auditoria de acessos.",
      url="https://tdn.totvs.com/display/tec/ShowIPClient")
    r("General", "ServerType", vtype="enum", enum=["Master", "Slave", ""], sev="info",
      desc="Tipo do servidor. Master para principal, Slave para secundários.",
      url="https://tdn.totvs.com/display/tec/ServerType")
    r("General", "InactiveTimeout", vtype="integer", min_val="300", sev="warning",
      desc="Timeout de inatividade em segundos. Mínimo recomendado: 300s (5 min).",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=388237222")
    r("General", "MaxBucketCommitTime", vtype="integer", min_val="10", sev="warning",
      desc="Tempo máximo para commit de bucket em segundos.",
      url="https://tdn.totvs.com/display/tec/MaxBucketCommitTime")
    r("General", "ServerMemoryLimit", vtype="integer", min_val="512", sev="warning",
      desc="Limite de memória do servidor em MB. Definir para evitar out-of-memory.",
      url="https://tdn.totvs.com/display/tec/ServerMemoryLimit")
    r("General", "HeapLimit", vtype="integer", min_val="256", sev="info",
      desc="Limite de heap por thread em MB.",
      url="https://tdn.totvs.com/display/tec/HeapLimit")
    r("General", "CanAcceptMonitor", val="1", vtype="boolean", sev="warning",
      desc="Permite conexão do TOTVS Monitor. Necessário para monitoramento remoto.",
      url="https://tdn.totvs.com/display/tec/CanAcceptMonitor")
    r("General", "CanAcceptDebugger", val="0", vtype="boolean", sev="warning",
      desc="Permite conexão de debugger. Desativar em produção por segurança.",
      url="https://tdn.totvs.com/display/tec/CanAcceptDebugger")
    r("General", "CanAcceptLB", vtype="boolean", sev="info",
      desc="Permite receber conexões via Load Balancer.",
      url="https://tdn.totvs.com/display/tec/CanAcceptLB")
    r("General", "CanRunJobs", vtype="boolean", sev="info",
      desc="Habilita execução de jobs agendados. Ativar apenas em servidores designados.",
      url="https://tdn.totvs.com/display/tec/CanRunJobs")
    r("General", "EchoConsoleLog", val="0", vtype="boolean", sev="info",
      desc="Ecoar log no terminal. Desativar em produção para performance.",
      url="https://tdn.totvs.com/display/tec/EchoConsoleLog")
    r("General", "AsyncConsoleLog", val="1", vtype="boolean", sev="info",
      desc="Log assíncrono do console. Melhora performance de I/O.",
      url="https://tdn.totvs.com/display/tec/AsyncConsoleLog")
    r("General", "WriteConsoleLog", val="1", vtype="boolean", sev="info",
      desc="Grava log do console em arquivo.",
      url="https://tdn.totvs.com/display/tec/WriteConsoleLog")
    r("General", "ErrorMaxSize", vtype="integer", min_val="10", max_val="200", sev="info",
      desc="Tamanho máximo do arquivo de erro em MB.",
      url="https://tdn.totvs.com/display/tec/ErrorMaxSize")
    r("General", "ShowFullLog", val="0", vtype="boolean", sev="info",
      desc="Exibe log completo. Desativar em produção.",
      url="https://tdn.totvs.com/display/tec/ShowFullLog")
    r("General", "Console", val="0", vtype="boolean", sev="info",
      desc="Exibe janela de console do AppServer. Desativar em serviço Windows.",
      url="https://tdn.totvs.com/display/tec/Console")
    r("General", "DebugThreadUsedMemory", val="0", vtype="boolean", sev="info",
      desc="Log de uso de memória por thread. Ativar apenas para diagnóstico.",
      url="https://tdn.totvs.com/display/tec/DebugThreadUsedMemory")
    r("General", "EnableDiagnosticsFile", val="0", vtype="boolean", sev="info",
      desc="Gera arquivo de diagnóstico. Ativar apenas para análise.",
      url="https://tdn.totvs.com/display/tec/EnableDiagnosticsFile")
    r("General", "EnableMemInfoCSV", val="0", vtype="boolean", sev="info",
      desc="Gera CSV com informações de memória.",
      url="https://tdn.totvs.com/display/tec/EnableMemInfoCSV")
    r("General", "MonitorConnections", val="1", vtype="boolean", sev="info",
      desc="Monitora conexões ativas no servidor.",
      url="https://tdn.totvs.com/display/tec/MonitorConnections")
    r("General", "MiniDumpMode", vtype="integer", sev="info",
      desc="Modo de geração de dump em caso de crash.",
      url="https://tdn.totvs.com/display/tec/MiniDumpMode")
    r("General", "MaxQuerySize", vtype="integer", min_val="1000", sev="info",
      desc="Tamanho máximo de queries SQL em KB.",
      url="https://tdn.totvs.com/display/tec/MaxQuerySize")
    r("General", "FILE_MAX", vtype="integer", min_val="500", sev="info",
      desc="Número máximo de arquivos abertos simultaneamente.",
      url="https://tdn.totvs.com/display/tec/FILE_MAX")
    r("General", "CanAcceptRPC", vtype="boolean", sev="info",
      desc="Permite chamadas RPC entre AppServers.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=6064808")
    r("General", "CanAcceptFSRemote", val="0", vtype="boolean", sev="warning",
      desc="Acesso remoto ao filesystem. Desativar em produção por segurança.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=181142740")
    r("General", "buildKillUsers", val="0", vtype="boolean", sev="warning",
      desc="Desconectar usuários durante build. Perigoso em produção.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=849084620")
    r("General", "ChangeEncodingBehavior", vtype="integer", sev="info",
      desc="Comportamento de encoding. Verificar compatibilidade com fontes.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=83165270")
    r("General", "logMessages", val="1", vtype="boolean", sev="info",
      desc="Registra mensagens do sistema no log.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=6064812")
    r("General", "ServerMemoryInfo", val="1", vtype="boolean", sev="info",
      desc="Registra informações de memória do servidor.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=6064814")
    r("General", "SSLRedirect", vtype="boolean", sev="info",
      desc="Redireciona HTTP para HTTPS automaticamente.",
      url="https://tdn.totvs.com/display/tec/SSLRedirect")
    r("General", "IPC_ActiveTimeOut", vtype="integer", min_val="30", sev="info",
      desc="Timeout de IPC ativo em segundos.",
      url="https://tdn.totvs.com/display/tec/IPC_ActiveTimeOut")
    r("General", "WorkThreadQtdMin", vtype="integer", min_val="2", sev="info",
      desc="Quantidade mínima de work threads.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=359469114")
    r("General", "LatencyLog", val="0", vtype="boolean", sev="info",
      desc="Habilita log de latência de rede.",
      url="https://tdn.totvs.com/display/tec/LatencyLog")
    r("General", "FloatingPointPrecise", val="1", vtype="boolean", sev="info",
      desc="Precisão de ponto flutuante. Recomendado ativo para cálculos financeiros.",
      url="https://tdn.totvs.com/display/tec/FloatingPointPrecise")
    r("General", "NewerClientConnection", val="1", vtype="boolean", sev="info",
      desc="Permite conexões de clientes mais recentes que o servidor.",
      url="https://tdn.totvs.com/display/tec/NewerClientConnection")

    # =====================================================
    # APPSERVER.INI — [Drivers]
    # =====================================================
    r("Drivers", "Active", val="TCP", sev="critical", req=True,
      desc="Protocolo de comunicação ativo. TCP é o padrão obrigatório.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=6064840")
    r("Drivers", "MultiProtocolPort", val="1", vtype="boolean", sev="info",
      desc="Permite múltiplos protocolos na mesma porta.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=538506039")
    r("Drivers", "MultiProtocolPortSecure", val="0", vtype="boolean", sev="info",
      desc="Múltiplos protocolos na porta segura.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=538506132")
    r("Drivers", "Secure", val="1", vtype="boolean", sev="warning",
      desc="Habilita comunicação segura (SSL/TLS). Recomendado para produção.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=135495976")

    # =====================================================
    # APPSERVER.INI — [DBAccess]
    # =====================================================
    r("DBAccess", "Database", vtype="client_config", sev="warning",
      desc="Nome do banco de dados. Alternativa à seção [TopConnect] ou chaves DB no [Environment].",
      url="https://tdn.totvs.com/display/tec/Application+Server+-+%5BDBAccess%5D+-+Database")
    r("DBAccess", "Server", vtype="client_config", sev="warning",
      desc="Servidor DBAccess. Alternativa à seção [TopConnect] ou chaves DB no [Environment].",
      url="https://tdn.totvs.com/display/tec/Application+Server+-+%5BDBAccess%5D+-+Server")
    r("DBAccess", "Port", vtype="client_config", sev="warning",
      desc="Porta do DBAccess. Alternativa à seção [TopConnect] ou chaves DB no [Environment].",
      url="https://tdn.totvs.com/display/tec/Application+Server+-+%5BDBAccess%5D+-+Port")
    r("DBAccess", "Alias", vtype="client_config", sev="info",
      desc="Alias da conexão DBAccess. Importante para identificar a conexão.",
      url="https://tdn.totvs.com/display/tec/Application+Server+-+%5BDBAccess%5D+-+Alias")
    r("DBAccess", "Driver", sev="info",
      desc="Driver do DBAccess (ex: MSSQL, ORACLE, POSTGRESQL).",
      url="https://tdn.totvs.com/display/tec/Application+Server+-+%5BDBAccess%5D+-+Driver")
    r("DBAccess", "MemoMega", val="1", vtype="boolean", sev="info",
      desc="Habilita campos memo com tamanho extendido.",
      url="https://tdn.totvs.com/display/tec/Application+Server+-+%5BDBAccess%5D+-+MemoMega")

    # =====================================================
    # APPSERVER.INI — [LicenseServer]
    # =====================================================
    r("LicenseServer", "IPCGOTIMEOUT", vtype="integer", min_val="5", sev="info",
      desc="Timeout de IPC para o License Server em segundos.",
      url="https://tdn.totvs.com/display/tec/IPCGOTIMEOUT")
    r("LicenseServer", "IPCRETURNTIMEOUT", vtype="integer", min_val="5", sev="info",
      desc="Timeout de retorno IPC do License Server.",
      url="https://tdn.totvs.com/display/tec/IPCRETURNTIMEOUT")
    r("LicenseServer", "STATELESSREUSECONN", val="1", vtype="boolean", sev="info",
      desc="Reutilizar conexões stateless com o License Server.",
      url="https://tdn.totvs.com/display/tec/STATELESSREUSECONN")

    # =====================================================
    # APPSERVER.INI — [Webapp]
    # =====================================================
    r("Webapp", "Port", vtype="client_config", min_val="80", max_val="65535", sev="info",
      desc="Porta HTTP do WebApp.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=307834845")
    r("Webapp", "MaxBodySize", vtype="integer", min_val="1024", sev="info",
      desc="Tamanho máximo do body HTTP em KB.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=325853432")
    r("Webapp", "MaxHeaderSize", vtype="integer", min_val="512", sev="info",
      desc="Tamanho máximo do header HTTP em KB.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=325853412")
    r("Webapp", "MaxRequestTime", vtype="integer", min_val="30", sev="info",
      desc="Timeout máximo de requisição HTTP em segundos.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=325853787")
    r("Webapp", "EnvServer", vtype="client_config", sev="info",
      desc="Nome do environment associado ao WebApp.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=307835198")
    r("Webapp", "ETags", val="1", vtype="boolean", sev="info",
      desc="Habilita ETags para cache HTTP.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=325853569")
    r("Webapp", "NonStopOnError", val="1", vtype="boolean", sev="warning",
      desc="Não parar o WebApp em caso de erro. Recomendado em produção.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=952668268")
    r("Webapp", "SSLCertificate", sev="warning",
      desc="Caminho do certificado SSL para HTTPS.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=417699647")
    r("Webapp", "SSLKey", sev="warning",
      desc="Caminho da chave privada SSL.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=417699652")
    r("Webapp", "SSLMethod", vtype="enum", enum=["TLSv1.2", "TLSv1.3", ""], sev="warning",
      desc="Método SSL/TLS. Usar TLSv1.2 ou superior.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=417699644")

    # =====================================================
    # APPSERVER.INI — [Update]
    # =====================================================
    r("Update", "Enable", val="0", vtype="boolean", sev="warning",
      desc="Atualização automática de clientes. Verificar impacto antes de ativar.",
      url="https://tdn.totvs.com/display/tec/Application+Server+-+%5BUpdate%5D+-+Enable")
    r("Update", "ForceUpdate", val="0", vtype="boolean", sev="warning",
      desc="Forçar atualização. Pode impactar usuários em uso.",
      url="https://tdn.totvs.com/display/tec/Application+Server+-+%5BUpdate%5D+-+ForceUpdate")

    # =====================================================
    # APPSERVER.INI — [HTTP]
    # =====================================================
    r("HTTP", "Enable", val="1", vtype="boolean", sev="info",
      desc="Habilita servidor HTTP embutido.",
      url="https://tdn.totvs.com/display/tec/Enable+--+29359")
    r("HTTP", "Port", vtype="client_config", min_val="80", max_val="65535", sev="info",
      desc="Porta do servidor HTTP.",
      url="https://tdn.totvs.com/display/tec/Port+--+29363")
    r("HTTP", "CorsEnable", val="1", vtype="boolean", sev="info",
      desc="Habilita CORS para requisições cross-origin.",
      url="https://tdn.totvs.com/display/tec/CorsEnable")
    r("HTTP", "Compression", val="1", vtype="boolean", sev="info",
      desc="Habilita compressão de resposta HTTP (gzip).",
      url="https://tdn.totvs.com/display/tec/Compression")
    r("HTTP", "Instances", vtype="integer", min_val="1", max_val="20", sev="info",
      desc="Número de instâncias do servidor HTTP.",
      url="https://tdn.totvs.com/display/tec/Instances")
    r("HTTP", "RPCTimeOut", vtype="integer", min_val="120", sev="info",
      desc="Timeout de chamadas RPC via HTTP em segundos.",
      url="https://tdn.totvs.com/display/tec/RPCTimeOut")
    r("HTTP", "HSTSEnable", val="1", vtype="boolean", sev="warning",
      desc="Habilita HSTS para forçar HTTPS. Recomendado em produção.",
      url="https://tdn.totvs.com/display/tec/HSTSEnable")
    r("HTTP", "LogRequest", val="0", vtype="boolean", sev="info",
      desc="Registra requisições HTTP no log.",
      url="https://tdn.totvs.com/display/tec/LogRequest")
    r("HTTP", "LogResponse", val="0", vtype="boolean", sev="info",
      desc="Registra respostas HTTP no log.",
      url="https://tdn.totvs.com/display/tec/LogResponse")
    r("HTTP", "AllowMethods", sev="info",
      desc="Métodos HTTP permitidos (GET, POST, PUT, DELETE, etc.).",
      url="https://tdn.totvs.com/display/tec/AllowMethods")

    # =====================================================
    # APPSERVER.INI — [Environment]
    # =====================================================
    r("Environment", "RootPath", vtype="client_config", sev="critical", req=True,
      desc="Diretório raiz do environment Protheus. Obrigatório.",
      url="https://tdn.totvs.com/display/tec/RootPath")
    r("Environment", "SourcePath", vtype="client_config", sev="critical", req=True,
      desc="Diretório dos fontes RPO. Definido pelo cliente conforme ambiente.",
      url="https://tdn.totvs.com/display/tec/SourcePath")
    r("Environment", "StartPath", vtype="client_config", sev="info",
      desc="Diretório inicial do environment.",
      url="https://tdn.totvs.com/display/tec/StartPath")
    r("Environment", "RpoDb", sev="info",
      desc="Banco de dados do RPO.",
      url="https://tdn.totvs.com/display/tec/RpoDb")
    r("Environment", "RpoLanguage", sev="info",
      desc="Idioma do RPO (Portuguese, English, Spanish).",
      url="https://tdn.totvs.com/display/tec/RpoLanguage")
    r("Environment", "RpoVersion", sev="info",
      desc="Versão do RPO (120, 121, 131, etc.).",
      url="https://tdn.totvs.com/display/tec/RpoVersion")
    r("Environment", "RpoCustom", sev="info",
      desc="Caminho do RPO customizado.",
      url="https://tdn.totvs.com/display/tec/RpoCustom")
    r("Environment", "LocalFiles", vtype="enum", enum=["CTREE", "ADS", ""], sev="info",
      desc="Tipo de arquivos locais (CTREE ou ADS).",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=6064766")
    r("Environment", "Trace", val="0", vtype="boolean", sev="info",
      desc="Habilita trace de execução. Desativar em produção.",
      url="https://tdn.totvs.com/display/tec/Trace")
    r("Environment", "TraceStack", val="0", vtype="boolean", sev="info",
      desc="Habilita trace de pilha de execução.",
      url="https://tdn.totvs.com/display/tec/TraceStack")
    r("Environment", "ConnectionTimeout", vtype="integer", min_val="60", sev="info",
      desc="Timeout de conexão em segundos.",
      url="https://tdn.totvs.com/display/tec/ConnectionTimeout")
    r("Environment", "MaxLocks", vtype="integer", min_val="100", sev="info",
      desc="Número máximo de locks simultâneos.",
      url="https://tdn.totvs.com/display/tec/MaxLocks")
    r("Environment", "TOPMemoMega", val="1", vtype="boolean", sev="info",
      desc="Habilita campos memo com tamanho extendido no environment.",
      url="https://tdn.totvs.com/display/tec/TOPMemoMega")
    r("Environment", "ThreadMemLimit", vtype="integer", min_val="256", sev="warning",
      desc="Limite de memória por thread em MB.",
      url="https://tdn.totvs.com/display/tec/ThreadMemLimit")
    r("Environment", "ThreadMemWarning", vtype="integer", min_val="128", sev="info",
      desc="Alerta de memória por thread em MB.",
      url="https://tdn.totvs.com/display/tec/ThreadMemWarning")
    r("Environment", "StringCodePage", sev="info",
      desc="Code page de strings (ex: CP1252).",
      url="https://tdn.totvs.com/display/tec/StringCodePage")
    r("Environment", "InactiveTimeOut", vtype="integer", min_val="300", sev="warning",
      desc="Timeout de inatividade do environment em segundos.",
      url="https://tdn.totvs.com/display/tec/%5BEnvironment%5D+InactiveTimeOut")

    # =====================================================
    # APPSERVER.INI — [BTMonitor]
    # =====================================================
    r("BTMonitor", "Enable", val="0", vtype="boolean", sev="info",
      desc="Habilita Business Tracking Monitor.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=448599027")
    r("BTMonitor", "Type", sev="info",
      desc="Tipo de monitoramento (ex: APPDYNAMICS).",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=448599051")
    r("BTMonitor", "LogLevel", vtype="integer", sev="info",
      desc="Nível de log do BTMonitor.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=490637696")

    # =====================================================
    # APPSERVER.INI — [FTP]
    # =====================================================
    r("FTP", "Enable", val="0", vtype="boolean", sev="warning",
      desc="Habilita servidor FTP embutido. Desativar se não for necessário.",
      url="https://tdn.totvs.com/display/tec/Enable")
    r("FTP", "Port", vtype="client_config", min_val="21", max_val="65535", sev="info",
      desc="Porta do servidor FTP.",
      url="https://tdn.totvs.com/display/tec/Port+--+29337")
    r("FTP", "CheckPassword", val="1", vtype="boolean", sev="warning",
      desc="Verificar senha nas conexões FTP.",
      url="https://tdn.totvs.com/display/tec/CheckPassword")

    # =====================================================
    # APPSERVER.INI — [Tec.AppServer.Memory]
    # =====================================================
    r("Tec.AppServer.Memory", "Enable", val="1", vtype="boolean", sev="info",
      desc="Habilita controle de memória do AppServer.",
      url="https://tdn.totvs.com/display/tec/%5BTec.AppServer.Memory%5D+-+chaves")

    # =====================================================
    # APPSERVER.INI — [APP_MONITOR]
    # =====================================================
    r("APP_MONITOR", "Enable", val="0", vtype="boolean", sev="info",
      desc="Habilita Application Monitor.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=552581338")

    # =====================================================
    # DBACCESS.INI
    # =====================================================
    r("General", "Port", vtype="client_config", sev="critical", req=True, ini_type="dbaccess",
      desc="Porta de escuta do DBAccess. Padrão 7890 mas varia conforme ambiente.")
    r("General", "MaxConnections", vtype="integer", min_val="50", sev="warning", ini_type="dbaccess",
      desc="Número máximo de conexões simultâneas.")
    r("General", "LogFile", vtype="client_config", sev="info", ini_type="dbaccess",
      desc="Caminho do arquivo de log do DBAccess.")
    r("MSSQL", "Server", vtype="client_config", sev="warning", ini_type="dbaccess",
      desc="Endereço do SQL Server. Obrigatório se usar driver MSSQL.")
    r("MSSQL", "Database", vtype="client_config", sev="warning", ini_type="dbaccess",
      desc="Nome do banco de dados no SQL Server. Obrigatório se usar driver MSSQL.")
    r("MSSQL", "Port", vtype="client_config", sev="info", ini_type="dbaccess",
      desc="Porta do SQL Server. Padrão 1433 mas varia conforme instalação.")
    r("MSSQL", "IntegratedSecurity", vtype="boolean", sev="info", ini_type="dbaccess",
      desc="Usar autenticação integrada Windows.")
    r("Oracle", "Server", vtype="client_config", sev="warning", ini_type="dbaccess",
      desc="TNS ou endereço do Oracle. Obrigatório se usar driver Oracle.")
    r("Oracle", "Database", vtype="client_config", sev="warning", ini_type="dbaccess",
      desc="Nome do banco/schema Oracle. Obrigatório se usar driver Oracle.")
    r("PostgreSQL", "Server", vtype="client_config", sev="warning", ini_type="dbaccess",
      desc="Endereço do PostgreSQL. Obrigatório se usar driver PostgreSQL.")
    r("PostgreSQL", "Database", vtype="client_config", sev="warning", ini_type="dbaccess",
      desc="Nome do banco PostgreSQL. Obrigatório se usar driver PostgreSQL.")
    r("PostgreSQL", "Port", vtype="client_config", sev="info", ini_type="dbaccess",
      desc="Porta do PostgreSQL. Padrão 5432 mas varia conforme instalação.")

    # =====================================================
    # APPSERVER.INI — [SSLConfigure] (segurança SSL/TLS)
    # =====================================================
    r("SSLConfigure", "CertificateServer", vtype="client_config", sev="warning",
      desc="Caminho do certificado SSL do servidor.",
      url="https://tdn.totvs.com/display/tec/CertificateServer")
    r("SSLConfigure", "KeyServer", vtype="client_config", sev="warning",
      desc="Caminho da chave privada SSL do servidor.",
      url="https://tdn.totvs.com/display/tec/KeyServer")
    r("SSLConfigure", "PassPhrase", sev="info",
      desc="Senha da chave privada SSL.",
      url="https://tdn.totvs.com/display/tec/PassPhrase")
    r("SSLConfigure", "CertificateClient", sev="info",
      desc="Caminho do certificado SSL do cliente.",
      url="https://tdn.totvs.com/display/tec/CertificateClient")
    r("SSLConfigure", "KeyClient", sev="info",
      desc="Caminho da chave privada SSL do cliente.",
      url="https://tdn.totvs.com/display/tec/KeyClient")
    r("SSLConfigure", "SSL2", val="0", vtype="boolean", sev="critical",
      desc="SSLv2 - INSEGURO. Deve estar desabilitado.",
      url="https://tdn.totvs.com/display/tec/SSL2")
    r("SSLConfigure", "SSL3", val="0", vtype="boolean", sev="critical",
      desc="SSLv3 - INSEGURO. Deve estar desabilitado.",
      url="https://tdn.totvs.com/display/tec/SSL3")
    r("SSLConfigure", "TLS1", val="0", vtype="boolean", sev="warning",
      desc="TLS 1.0 - Obsoleto. Desativar quando possível.",
      url="https://tdn.totvs.com/display/tec/TLS1")
    r("SSLConfigure", "TLS1_0", val="0", vtype="boolean", sev="warning",
      desc="TLS 1.0 - Obsoleto. Desativar quando possível.",
      url="https://tdn.totvs.com/display/tec/TLS1_0")
    r("SSLConfigure", "TLS1_1", val="0", vtype="boolean", sev="warning",
      desc="TLS 1.1 - Obsoleto. Desativar quando possível.",
      url="https://tdn.totvs.com/display/tec/TLS1_1")
    r("SSLConfigure", "TLS1_2", val="1", vtype="boolean", sev="warning",
      desc="TLS 1.2 - Recomendado. Deve estar habilitado.",
      url="https://tdn.totvs.com/display/tec/TLS1_2")
    r("SSLConfigure", "TLS1_3", val="1", vtype="boolean", sev="info",
      desc="TLS 1.3 - Mais seguro e rápido. Habilitar se suportado.",
      url="https://tdn.totvs.com/display/tec/TLS1_3")
    r("SSLConfigure", "Verbose", val="0", vtype="boolean", sev="info",
      desc="Log detalhado de SSL. Desativar em produção.",
      url="https://tdn.totvs.com/display/tec/Verbose")
    r("SSLConfigure", "HSM", val="0", vtype="boolean", sev="info",
      desc="Usar Hardware Security Module para chaves.",
      url="https://tdn.totvs.com/display/tec/HSM")
    r("SSLConfigure", "CacheSize", vtype="integer", sev="info",
      desc="Tamanho do cache de sessões SSL.",
      url="https://tdn.totvs.com/display/tec/CacheSize")
    r("SSLConfigure", "State", val="1", vtype="boolean", sev="warning",
      desc="Habilita SSL/TLS no servidor.",
      url="https://tdn.totvs.com/display/tec/State")

    # =====================================================
    # APPSERVER.INI — [HTTPS]
    # =====================================================
    r("HTTPS", "AllowMethods", sev="info",
      desc="Métodos HTTP permitidos em HTTPS.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=860255477")
    r("HTTPS", "ClientCertVerify", val="0", vtype="boolean", sev="info",
      desc="Verificar certificado do cliente em HTTPS.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=544725908")
    r("HTTPS", "SecureCookie", val="1", vtype="boolean", sev="warning",
      desc="Cookies seguros (flag Secure). Recomendado em produção.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=272152247")

    # =====================================================
    # APPSERVER.INI — [LockServer]
    # =====================================================
    r("LockServer", "Enable", val="0", vtype="boolean", sev="info",
      desc="Habilita servidor de locks centralizado.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=6064851")
    r("LockServer", "Port", vtype="client_config", sev="info",
      desc="Porta do servidor de locks.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=6064854")
    r("LockServer", "Server", vtype="client_config", sev="info",
      desc="Endereço do servidor de locks.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=6064855")
    r("LockServer", "SecureConnection", val="0", vtype="boolean", sev="info",
      desc="Usar conexão segura com o LockServer.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=539526530")

    # =====================================================
    # APPSERVER.INI — [Mail]
    # =====================================================
    r("Mail", "Protocol", vtype="enum", enum=["SMTP", "POP3", "IMAP"], sev="info",
      desc="Protocolo de e-mail.",
      url="https://tdn.totvs.com/display/tec/Protocol")
    r("Mail", "SmtpPopServer", vtype="client_config", sev="info",
      desc="Servidor SMTP/POP.",
      url="https://tdn.totvs.com/display/tec/SmtpPopServer")
    r("Mail", "SmtpPopPort", vtype="client_config", sev="info",
      desc="Porta do servidor SMTP/POP.",
      url="https://tdn.totvs.com/display/tec/SmtpPopPort")
    r("Mail", "AuthSmtp", val="1", vtype="boolean", sev="warning",
      desc="Autenticação SMTP. Recomendado ativo.",
      url="https://tdn.totvs.com/display/tec/AuthSmtp")
    r("Mail", "TLSVersion", sev="info",
      desc="Versão TLS para e-mail.",
      url="https://tdn.totvs.com/display/tec/TLSVersion")

    # =====================================================
    # APPSERVER.INI — [OnStart]
    # =====================================================
    r("OnStart", "Jobs", sev="info",
      desc="Jobs a executar na inicialização do AppServer.",
      url="https://tdn.totvs.com/display/tec/Jobs")
    r("OnStart", "RefreshRate", vtype="integer", min_val="30", sev="info",
      desc="Taxa de refresh dos jobs em segundos.",
      url="https://tdn.totvs.com/display/tec/RefreshRate")

    # =====================================================
    # APPSERVER.INI — [Telnet]
    # =====================================================
    r("Telnet", "Enable", val="0", vtype="boolean", sev="warning",
      desc="Habilita servidor Telnet. Desativar em produção (inseguro).",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=6064909")
    r("Telnet", "InactiveTimeout", vtype="integer", min_val="300", sev="info",
      desc="Timeout de inatividade Telnet.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=117473519")

    # =====================================================
    # APPSERVER.INI — [LicenseServer] (chaves adicionais)
    # =====================================================
    r("LicenseServer", "Enable", val="1", vtype="boolean", sev="warning",
      desc="Habilita License Server.",
      url="https://tdn.totvs.com/display/tec/%5BLicenseServer%5D+Enable")
    r("LicenseServer", "Port", vtype="client_config", sev="warning",
      desc="Porta do License Server.",
      url="https://tdn.totvs.com/display/tec/%5BLicenseServer%5D+Port")
    r("LicenseServer", "ShowStatus", val="1", vtype="boolean", sev="info",
      desc="Exibe status do License Server.",
      url="https://tdn.totvs.com/display/tec/%5BLicenseServer%5D+ShowStatus")

    # =====================================================
    # APPSERVER.INI — [WebAgent]
    # =====================================================
    r("WebAgent", "Port", vtype="client_config", min_val="1024", max_val="65535", sev="info",
      desc="Porta do WebAgent.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=725728366")
    r("WebAgent", "Version", sev="info",
      desc="Versão do WebAgent.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=725269118")

    # =====================================================
    # APPSERVER.INI — [SQLiteServer]
    # =====================================================
    r("SQLiteServer", "Enable", val="0", vtype="boolean", sev="info",
      desc="Habilita servidor SQLite embutido.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=367235924")
    r("SQLiteServer", "Port", vtype="client_config", sev="info",
      desc="Porta do servidor SQLite.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=367235929")
    r("SQLiteServer", "Instances", vtype="integer", min_val="1", sev="info",
      desc="Instâncias do servidor SQLite.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=367235932")

    # =====================================================
    # DBACCESS.INI — [General] (expandido com TDN URLs)
    # =====================================================
    # MaxStringSize NÃO se aplica ao DBAccess — é configuração do AppServer
    r("General", "consoleLog", val="1", vtype="boolean", sev="warning", ini_type="dbaccess",
      desc="Habilita log do console do DBAccess.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=445645676")
    r("General", "ConsoleMaxSize", vtype="integer", min_val="50", max_val="500", sev="info", ini_type="dbaccess",
      desc="Tamanho máximo do log do DBAccess em MB.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=6064710")
    r("General", "EchoConsoleLog", val="0", vtype="boolean", sev="info", ini_type="dbaccess",
      desc="Ecoar log do DBAccess no terminal.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=993707146")
    r("General", "ShowAllErrors", val="1", vtype="boolean", sev="info", ini_type="dbaccess",
      desc="Exibir todos os erros no log.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=256317044")
    r("General", "DBWarnings", val="1", vtype="boolean", sev="info", ini_type="dbaccess",
      desc="Exibir warnings do banco de dados.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=270910540")
    r("General", "DBPulse", val="1", vtype="boolean", sev="info", ini_type="dbaccess",
      desc="Heartbeat de conexão com o banco.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=394209930")
    r("General", "CheckDeadLock", val="1", vtype="boolean", sev="warning", ini_type="dbaccess",
      desc="Detectar deadlocks automaticamente.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=488145641")
    r("General", "ThreadMin", vtype="integer", min_val="2", sev="info", ini_type="dbaccess",
      desc="Mínimo de threads do DBAccess.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=519203974")
    r("General", "ThreadMax", vtype="integer", min_val="50", sev="info", ini_type="dbaccess",
      desc="Máximo de threads do DBAccess.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=519204038")
    r("General", "ThreadInc", vtype="integer", min_val="1", sev="info", ini_type="dbaccess",
      desc="Incremento de threads sob demanda.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=519204196")
    r("General", "ReleaseInactiveConn", val="1", vtype="boolean", sev="info", ini_type="dbaccess",
      desc="Liberar conexões inativas com o banco.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=268813153")
    r("General", "AllowHosts", sev="warning", ini_type="dbaccess",
      desc="Lista de hosts permitidos para conectar ao DBAccess. Segurança.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=606414945")
    r("General", "MonitorAll", val="1", vtype="boolean", sev="info", ini_type="dbaccess",
      desc="Monitorar todas as conexões.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=603113449")
    r("General", "MonitorPort", vtype="client_config", sev="info", ini_type="dbaccess",
      desc="Porta do monitor do DBAccess.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=558264029")
    r("General", "UseLargeRecno", val="1", vtype="boolean", sev="info", ini_type="dbaccess",
      desc="Usar RECNO largo (bigint). Necessário para tabelas grandes.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=514746948")

    # =====================================================
    # DBACCESS.INI — [Environment] (chaves de tunning)
    # =====================================================
    r("Environment", "UseBind", val="1", vtype="boolean", sev="warning", ini_type="dbaccess",
      desc="Usar bind variables. Melhora performance e segurança.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=234611535")
    r("Environment", "UseHint", val="1", vtype="boolean", sev="info", ini_type="dbaccess",
      desc="Usar hints SQL para otimização de queries.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=190518123")
    r("Environment", "IndexHint", val="1", vtype="boolean", sev="info", ini_type="dbaccess",
      desc="Usar hints de índice nas queries.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=190518125")
    r("Environment", "LockTimeOut", vtype="integer", min_val="10", sev="warning", ini_type="dbaccess",
      desc="Timeout de lock em segundos.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=525012915")
    r("Environment", "DeadLockExit", val="1", vtype="boolean", sev="warning", ini_type="dbaccess",
      desc="Encerrar conexão em caso de deadlock.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=489760330")
    r("Environment", "UseLockInDB", val="1", vtype="boolean", sev="info", ini_type="dbaccess",
      desc="Usar locks nativos do banco de dados.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=488145444")
    r("Environment", "MemoAsByte", val="1", vtype="boolean", sev="info", ini_type="dbaccess",
      desc="Tratar campos memo como bytes.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=274303055")
    r("Environment", "MemoInQuery", val="1", vtype="boolean", sev="info", ini_type="dbaccess",
      desc="Incluir campos memo em queries.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=525011927")
    r("Environment", "UseRowStamp", val="1", vtype="boolean", sev="info", ini_type="dbaccess",
      desc="Usar RowStamp para controle de concorrência.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=540880307")
    r("Environment", "UseRowInsDt", val="1", vtype="boolean", sev="info", ini_type="dbaccess",
      desc="Usar data de inserção do registro.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=540891311")
    r("Environment", "Compression", val="1", vtype="boolean", sev="info", ini_type="dbaccess",
      desc="Compressão de dados na comunicação com o banco.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=611799570")
    r("Environment", "SeekBind", val="1", vtype="boolean", sev="info", ini_type="dbaccess",
      desc="Usar bind em operações de seek.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=519725180")
    r("Environment", "LogAction", val="0", vtype="boolean", sev="info", ini_type="dbaccess",
      desc="Registrar ações no log. Impacta performance se ativo.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=283399643")
    r("Environment", "UseDDLTrace", val="0", vtype="boolean", sev="info", ini_type="dbaccess",
      desc="Trace de operações DDL. Ativar apenas para diagnóstico.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=991876799")
    r("Environment", "UseSysTables", val="0", vtype="boolean", sev="info", ini_type="dbaccess",
      desc="Usar tabelas de sistema para metadados.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=368903898")
    r("Environment", "TableSpace", sev="info", ini_type="dbaccess",
      desc="Tablespace para dados.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=751245551")
    r("Environment", "IndexSpace", sev="info", ini_type="dbaccess",
      desc="Tablespace para índices.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=751245585")
    r("Environment", "LobSpace", sev="info", ini_type="dbaccess",
      desc="Tablespace para LOBs.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=616202447")

    # =====================================================
    # DBACCESS.INI — [SSLConfigure]
    # =====================================================
    r("SSLConfigure", "Enable", val="0", vtype="boolean", sev="info", ini_type="dbaccess",
      desc="Habilita SSL no DBAccess.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=525024188")
    r("SSLConfigure", "CertificateFile", sev="info", ini_type="dbaccess",
      desc="Certificado SSL do DBAccess.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=525024161")
    r("SSLConfigure", "KeyFile", sev="info", ini_type="dbaccess",
      desc="Chave privada SSL do DBAccess.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=525024165")

    # =====================================================
    # APPSERVER.INI — [Broker] (Balanceamento de carga)
    # =====================================================
    r("Broker", "Enable", val="1", vtype="boolean", sev="warning",
      desc="Habilita o modo Broker para balanceamento de carga. Necessário apenas se este servidor for broker.",
      url="https://tdn.totvs.com/display/tec/Broker")
    r("Broker", "Port", vtype="client_config", sev="warning",
      desc="Porta TCP do Broker para conexões de clientes.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=396658349")
    r("Broker", "Type", vtype="enum", enum=["TCP", "HTTP", "WEBSERVICE"], sev="warning",
      desc="Tipo de balanceamento: TCP (SmartClient), HTTP (Web/REST), WEBSERVICE.",
      url="https://tdn.totvs.com/display/tec/Broker")
    r("Broker", "Servers", sev="warning",
      desc="Lista de nomes das seções de servidores balanceados (ex: Server01,Server02).",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=396658349")
    r("Broker", "BalanceByResource", val="0", vtype="boolean", sev="info",
      desc="Habilita balanceamento por recursos (CPU/memória dos slaves).",
      url="https://tdn.totvs.com/display/tec/Balanceamento+por+Recursos")
    r("Broker", "MonitorInterval", vtype="integer", min_val="10", sev="info",
      desc="Intervalo em segundos para monitorar servidores balanceados.",
      url="https://tdn.totvs.com/display/tec/Monitoramento+dos+Servidores")
    r("Broker", "WebMonitor", val="1", vtype="boolean", sev="info",
      desc="Habilita WebMonitor para visualizar status do Broker via browser.",
      url="https://tdn.totvs.com/display/tec/WebMonitor")
    r("Broker", "WebMonitorPort", vtype="client_config", min_val="1024", max_val="65535", sev="info",
      desc="Porta HTTP do WebMonitor do Broker.",
      url="https://tdn.totvs.com/display/tec/Uso+do+WebMonitor")
    r("Broker", "MaxConnections", vtype="integer", min_val="100", sev="warning",
      desc="Número máximo de conexões simultâneas no Broker.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=560650660")
    r("Broker", "SSLCertificate", sev="warning",
      desc="Certificado SSL para conexões encriptadas no Broker.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=396659144")
    r("Broker", "SSLKey", sev="warning",
      desc="Chave privada SSL do Broker.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=396659144")
    r("Broker", "MaxRecoveryTime", vtype="integer", min_val="30", sev="info",
      desc="Tempo máximo de recuperação do SmartClient Desktop em segundos.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=396659114")
    r("Broker", "HAEnable", val="0", vtype="boolean", sev="info",
      desc="Habilita alta disponibilidade (HA) entre Brokers.",
      url="https://tdn.totvs.com/display/tec/Broker+HA+-+Alta+Disponibilidade")
    r("Broker", "LogLevel", vtype="integer", min_val="0", max_val="3", sev="info",
      desc="Nível de log do Broker (0=mínimo, 3=máximo).",
      url="https://tdn.totvs.com/display/tec/Broker")
    r("Broker", "Scheduler", val="0", vtype="boolean", sev="info",
      desc="Habilita agendamento para ativar/desativar serviços balanceados.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=563433831")

    # =====================================================
    # APPSERVER.INI — [BrokerAgent]
    # =====================================================
    r("BrokerAgent", "Enable", val="0", vtype="boolean", sev="info",
      desc="Habilita Broker Agent para monitoramento remoto de servidores.",
      url="https://tdn.totvs.com/display/tec/Broker+Agent")
    r("BrokerAgent", "Port", vtype="client_config", min_val="1024", max_val="65535", sev="info",
      desc="Porta do Broker Agent.",
      url="https://tdn.totvs.com/display/tec/Broker+Agent")
    r("BrokerAgent", "BrokerServer", vtype="client_config", sev="info",
      desc="Endereço do Broker principal para o Agent reportar.",
      url="https://tdn.totvs.com/display/tec/Broker+Agent")

    # =====================================================
    # TSS APPSERVER.INI — 63 regras em 14 seções
    # Fonte: Central de Atendimento TOTVS (77 artigos scrapeados)
    # https://centraldeatendimento.totvs.com/hc/pt-br/sections/206834307-TSS
    # =====================================================

    # --- [General] (6 regras) ---
    r("General", "MaxStringSize", ini_type="tss", val="10", vtype="integer", min_val="10", sev="critical", req=True,
      desc="Obrigatório 10 para compatibilidade com XMLs e campos CLOB do TSS.",
      url="https://tdn.totvs.com/pages/viewpage.action?pageId=161349793")
    r("General", "ConsoleLog", ini_type="tss", val="1", vtype="boolean", sev="warning",
      desc="Habilita log no console do TSS. Essencial para diagnóstico de transmissões.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/1500007834222")
    r("General", "ConsoleMaxSize", ini_type="tss", vtype="integer", min_val="50", max_val="500", sev="info",
      desc="Tamanho máximo do log de console em MB. Evita consumo excessivo de disco pelo TSS.")
    r("General", "ConsoleLogDate", ini_type="tss", val="1", vtype="boolean", sev="info",
      desc="Adiciona data no nome do log do console. Facilita rastreabilidade de transmissões.")
    # RootPath fica no [Environment] (ex: [SPED]), NÃO no [General]
    r("General", "CanAcceptMonitor", ini_type="tss", val="1", vtype="boolean", sev="warning",
      desc="Permite conexão do TOTVS Monitor ao TSS para monitoramento de threads e jobs.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/360056411274")

    # --- [Drivers] (2 regras) ---
    r("Drivers", "Active", ini_type="tss", val="TCP", vtype="string", sev="critical", req=True,
      desc="Driver de conexão ativo. Deve ser TCP para comunicação padrão do TSS.")
    r("Drivers", "Secure", ini_type="tss", val="SSL", vtype="string", sev="warning",
      desc="Driver de conexão segura. Definir SSL para comunicação HTTPS com SEFAZ.")

    # --- [SSLConfigure] (8 regras) ---
    r("SSLConfigure", "SSL2", ini_type="tss", val="0", vtype="boolean", sev="critical",
      desc="Desabilitar SSL2 — protocolo inseguro e obsoleto. SEFAZ rejeita.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/1500002745522")
    r("SSLConfigure", "SSL3", ini_type="tss", val="0", vtype="boolean", sev="critical",
      desc="Desabilitar SSL3 — protocolo inseguro (vulnerável a POODLE).",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/1500002745522")
    r("SSLConfigure", "TLS1", ini_type="tss", val="0", vtype="boolean", sev="warning",
      desc="Desabilitar TLS 1.0 — protocolo antigo, SEFAZ não aceita mais.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/1500002745522")
    r("SSLConfigure", "TLS1_1", ini_type="tss", val="0", vtype="boolean", sev="warning",
      desc="Desabilitar TLS 1.1 — protocolo antigo, SEFAZ não aceita mais.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/1500002745522")
    r("SSLConfigure", "TLS1_2", ini_type="tss", val="1", vtype="boolean", sev="critical", req=True,
      desc="Habilitar TLS 1.2 — protocolo mínimo aceito pela SEFAZ para transmissão de DFe.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/1500002745522")
    r("SSLConfigure", "Verbose", ini_type="tss", val="0", vtype="boolean", sev="info",
      desc="Depuração de comunicação SSL. Ativar APENAS para diagnóstico de certificados.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/360058611413")
    r("SSLConfigure", "CertificateClient", ini_type="tss", vtype="client_config", sev="critical",
      desc="Caminho do certificado digital (.crt) para comunicação HTTPS com SEFAZ. Obrigatório se [SSLConfigure] existir.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/1500002745522")
    r("SSLConfigure", "KeyClient", ini_type="tss", vtype="client_config", sev="critical",
      desc="Caminho da chave privada (.pem) do certificado digital. Obrigatório se [SSLConfigure] existir.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/1500002745522")

    # --- [Environment/SPED] (13 regras) ---
    r("SPED", "SourcePath", ini_type="tss", vtype="client_config", sev="critical", req=True,
      desc="Caminho do diretório de fontes do TSS (APO).")
    r("SPED", "RootPath", ini_type="tss", vtype="client_config", sev="critical", req=True,
      desc="Diretório raiz do environment SPED. Definido pelo cliente.")
    r("SPED", "StartPath", ini_type="tss", vtype="client_config", sev="info",
      desc="Diretório inicial do TSS.")
    r("SPED", "RPODb", ini_type="tss", vtype="string", sev="critical", req=True,
      desc="Nome do arquivo RPO do TSS (ex: tss.rpo).",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/360064478214")
    r("SPED", "RPOVersion", ini_type="tss", vtype="string", sev="info",
      desc="Versão do RPO do TSS (ex: 120).",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/360064478214")
    r("SPED", "TOPMEMOMEGA", ini_type="tss", val="1", vtype="boolean", sev="warning",
      desc="Habilita gravação de XMLs completos usando campo Memo. Recomendado para rastreabilidade.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/360057461214")
    r("SPED", "SPED_SAVEWSDL", ini_type="tss", val="0", vtype="boolean", sev="warning",
      desc="Grava XMLs de comunicação TSS<->SEFAZ na pasta System. Ativar APENAS para diagnóstico.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/1500007834222")
    r("SPED", "XMLSAVEALL", ini_type="tss", val="0", vtype="boolean", sev="warning",
      desc="Grava todos os XMLs ERP<->TSS na pasta WSLOGXML. Ativar APENAS para diagnóstico.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/1500007834222")
    r("SPED", "LOG_PERIOD", ini_type="tss", vtype="integer", sev="info",
      desc="Período de retenção de logs do TSS em dias. Controla limpeza automática.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/360057330294")
    r("SPED", "LOG_PERIOD_TR2", ini_type="tss", vtype="integer", sev="info",
      desc="Período de retenção de logs TR2 (transmissão) em dias.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/360057330374")
    r("SPED", "SYSTIMEADJUST", ini_type="tss", vtype="integer", sev="info",
      desc="Ajuste de fuso horário em horas (ex: -1 para GMT-1). Corrige divergência de horário nos XMLs.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/360057466214")
    r("SPED", "DbAlias", ini_type="tss", vtype="client_config", sev="warning",
      desc="Fonte de dados ODBC. Alternativa à seção [DBAccess] ou [TopConnect].")
    r("SPED", "DbServer", ini_type="tss", vtype="client_config", sev="warning",
      desc="Servidor DBAccess. Alternativa à seção [DBAccess] ou [TopConnect].")

    # --- [JOB_WS] (7 regras) ---
    r("JOB_WS", "MAIN", ini_type="tss", val="WS_START", vtype="string", sev="critical", req=True,
      desc="Função principal do web service TSS. Obrigatório WS_START.")
    r("JOB_WS", "Environment", ini_type="tss", vtype="client_config", sev="critical", req=True,
      desc="Environment do job (ex: SPED). Deve corresponder ao environment configurado.")
    r("JOB_WS", "Instances", ini_type="tss", vtype="integer", min_val="1", max_val="10", sev="warning",
      desc="Número de instâncias do job JOB_WS. Ajustar conforme volume de transmissões.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/360058163793")
    r("JOB_WS", "SigaWS", ini_type="tss", val="WS_TSS", vtype="string", sev="critical", req=True,
      desc="Nome do web service do TSS. Obrigatório para exposição dos métodos.")
    r("JOB_WS", "TSSSECURITY", ini_type="tss", val="1", vtype="boolean", sev="critical", req=True,
      desc="Habilita autenticação no TSS. Crítico para segurança — impede acesso não autorizado.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/4412593739287")
    r("JOB_WS", "ExpirationDelta", ini_type="tss", vtype="integer", min_val="30", sev="info",
      desc="Tempo em minutos para expiração do token de autenticação.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/360054804154")
    r("JOB_WS", "XMLSAVEALL", ini_type="tss", val="0", vtype="boolean", sev="warning",
      desc="Grava XMLs ERP<->TSS na pasta WSLOGXML. Ativar APENAS para diagnóstico.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/1500007834222")

    # --- [OnStart] (2 regras) ---
    r("OnStart", "Jobs", ini_type="tss", val="JOB_WS", vtype="contains", sev="critical", req=True,
      desc="Lista de jobs a iniciar. JOB_WS deve estar presente na lista para o TSS funcionar.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/23502598416023")
    r("OnStart", "RefreshRate", ini_type="tss", vtype="integer", min_val="10", sev="info",
      desc="Intervalo em segundos para verificação de novos jobs.")

    # --- [tsstaskproc] (3 regras) ---
    r("tsstaskproc", "Main", ini_type="tss", val="tsstaskproc", vtype="string", sev="warning",
      desc="Job de processamento assíncrono do TSS 3.0.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/360054755053")
    r("tsstaskproc", "Environment", ini_type="tss", vtype="client_config", sev="info",
      desc="Environment do job de processamento de tarefas.")
    r("tsstaskproc", "Instances", ini_type="tss", vtype="integer", min_val="1", max_val="5", sev="info",
      desc="Instâncias do job de processamento. Ajustar conforme volume.")

    # --- [DistMail] (3 regras) ---
    r("DistMail", "Main", ini_type="tss", val="DistMail", vtype="string", sev="warning",
      desc="Job de distribuição de email para envio automático de DANFE/DACTE por email.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/360053938654")
    r("DistMail", "Environment", ini_type="tss", vtype="client_config", sev="info",
      desc="Environment do job DistMail (mesmo nome do environment SPED).")
    r("DistMail", "Instances", ini_type="tss", vtype="integer", min_val="1", sev="info",
      desc="Instâncias do job de distribuição de email.")

    # --- [IPC_DISTMAIL] (3 regras) ---
    r("IPC_DISTMAIL", "Main", ini_type="tss", val="prepareIPCWAIT", vtype="string", sev="warning",
      desc="Job IPC para processamento de fila de emails do DistMail.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/360053938654")
    r("IPC_DISTMAIL", "Environment", ini_type="tss", vtype="client_config", sev="info",
      desc="Environment do job IPC_DISTMAIL.")
    r("IPC_DISTMAIL", "Instances", ini_type="tss", val="1,10,1,1", vtype="string", sev="info",
      desc="Instâncias do IPC_DISTMAIL (min,max,step,initial).")

    # --- [IPC_SMTP] (3 regras) ---
    r("IPC_SMTP", "Main", ini_type="tss", val="prepareIPCWAIT", vtype="string", sev="info",
      desc="Job IPC para envio SMTP com reprocessamento automático.")
    r("IPC_SMTP", "TRYREPROC", ini_type="tss", vtype="integer", min_val="1", max_val="5", sev="warning",
      desc="Número de tentativas de reenvio de email em caso de falha SMTP.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/360057461974")
    r("IPC_SMTP", "Environment", ini_type="tss", vtype="client_config", sev="info",
      desc="Environment do job IPC_SMTP.")

    # --- [HTTPREST] (3 regras) ---
    r("HTTPREST", "Port", ini_type="tss", vtype="client_config", sev="info",
      desc="Porta REST para integração ERP via API (ex: 1322).",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/4414093192087")
    r("HTTPREST", "URIs", ini_type="tss", val="HTTPURI", vtype="string", sev="warning",
      desc="Nome da seção de URIs REST. Padrão: HTTPURI.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/4414093192087")
    r("HTTPREST", "Security", ini_type="tss", val="0", vtype="boolean", sev="info",
      desc="Segurança REST. Manter 0 conforme documentação TOTVS.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/4414093192087")

    # --- [HTTPJOB] (2 regras) ---
    r("HTTPJOB", "MAIN", ini_type="tss", val="HTTP_START", vtype="string", sev="warning",
      desc="Job HTTP para habilitar API REST no TSS. Necessário para Portal do Cliente/SPED059.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/4414093192087")
    r("HTTPJOB", "Environment", ini_type="tss", vtype="client_config", sev="info",
      desc="Environment do job HTTP.")

    # --- [TCP] (2 regras) ---
    r("TCP", "Port", ini_type="tss", vtype="client_config", sev="critical", req=True,
      desc="Porta TCP principal do TSS. Padrão 8080 mas varia conforme ambiente. Deve ser única no servidor.")
    r("TCP", "SecureConnection", ini_type="tss", val="1", vtype="boolean", sev="warning",
      desc="Habilita conexão segura na porta TCP. Recomendado para produção.")

    # --- [DBAccess] (3 regras) ---
    r("DBAccess", "Server", ini_type="tss", vtype="client_config", sev="warning",
      desc="Servidor DBAccess. Alternativa à seção [TopConnect] ou chaves DB no [SPED].",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/23502657258647")
    r("DBAccess", "Port", ini_type="tss", vtype="client_config", sev="warning",
      desc="Porta do DBAccess. Alternativa à seção [TopConnect] ou chaves DB no [SPED].",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/23502657258647")
    r("DBAccess", "Database", ini_type="tss", vtype="client_config", sev="warning",
      desc="Fonte de dados ODBC. Alternativa à seção [TopConnect] ou chaves DB no [SPED].",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/23502657258647")

    # --- [TSSOFFLINE] (3 regras) ---
    r("TSSOFFLINE", "TSSOFFLINE", ini_type="tss", val="1", vtype="boolean", sev="info",
      desc="Habilita modo offline do TSS. Para emissão de DFe sem conexão com TSS Online.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/360062042954")
    r("TSSOFFLINE", "ONLINEURL", ini_type="tss", vtype="client_config", sev="info",
      desc="Endereço do TSS Online para sincronização quando a conexão for restabelecida.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/360062042954")
    r("TSSOFFLINE", "ONLINEPORT", ini_type="tss", vtype="client_config", sev="info",
      desc="Porta do TSS Online para sincronização (ex: 8080).",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/360062042954")

    # --- [PROXY] (3 regras — essenciais) ---
    r("PROXY", "Enable", ini_type="tss", vtype="boolean", sev="info",
      desc="Habilita proxy para comunicação com SEFAZ. Necessário se o TSS não acessa internet direto.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/360056653873")
    r("PROXY", "Server", ini_type="tss", vtype="client_config", sev="info",
      desc="Endereço do servidor proxy para comunicação com SEFAZ.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/360056653873")
    r("PROXY", "Port", ini_type="tss", vtype="client_config", sev="info",
      desc="Porta do servidor proxy.",
      url="https://centraldeatendimento.totvs.com/hc/pt-br/articles/360056653873")

    return rules

