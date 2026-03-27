"""
AtuDIC - Protheus Log Parser & Monitor

Parser para console.log e error.log do TOTVS Protheus AppServer.
Identifica padrões de erro, warning e métricas operacionais.
"""

import os
import re
import threading
import time
import traceback
import subprocess
import shlex
from datetime import datetime

from app.database import get_db, release_db_connection
from app.services.events import event_manager
from app.services.notifier import send_email_async

# =====================================================================
# PADRÕES DE LOG DO PROTHEUS
# =====================================================================

# Formato do timestamp ISO do console.log
RE_TIMESTAMP = re.compile(
    r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+[+-]\d{2}:\d{2})\s+(\d+)\|'
)

# Formato do THREAD ERROR no error.log
RE_THREAD_ERROR = re.compile(
    r'THREAD ERROR\s*\(\[(\d+)\],\s*(\w+),\s*\w+\)\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2}:\d{2})'
)

# Erros Oracle ORA-XXXXX
RE_ORA_ERROR = re.compile(r'(ORA-\d+):\s*(.*?)(?:\n|$)')

# Erros TOPCONN
RE_TOPCONN = re.compile(r'Error\s*-\s*TOPCONN\s*-\s*(.*?)(?:\n|$)')

# Thread finished (usuario desconectou)
RE_THREAD_FINISHED = re.compile(
    r'Thread finished\s*\((\w+),\s*([\w-]+)\)\s*(.*?)$'
)

# Error ending thread
RE_ERROR_ENDING_THREAD = re.compile(
    r'Error ending thread\s*\((\w+),\s*([\w-]+)\)\s*(.*?)$'
)

# Memory info do OS
RE_MEMORY_OS = re.compile(
    r'Physical memory\s*\.\s*([\d.]+)\s*MB\.\s*Used\s*([\d.]+)\s*MB\.\s*Free\s*([\d.]+)\s*MB'
)

# Memory do AppServer
RE_MEMORY_APP = re.compile(
    r'Service Resident Memory\s*\.\.\.\s*([\d.]+)\s*MB'
)

# Server start time
RE_START_TIME = re.compile(
    r'Application Server Start Time:\s*([\d.]+)\s*s'
)

# AD Authentication errors
RE_AD_ERROR = re.compile(
    r'\[ADUSERVALID ERROR\].*?Error in LogonUser function\s*\(code\s*(\d+)\):\s*(.*?)$'
)

# SSL connection failures
RE_SSL_FAIL = re.compile(
    r'Failed to connect socket SSL.*?\(timeout\).*?srv=([^\s/]+)'
)

# HTTP Server fail to start
RE_HTTP_FAIL = re.compile(
    r'HTTP Server.*?fail to start.*?(\d+)'
)

# Connection finished by inactivity
RE_INACTIVITY = re.compile(
    r'Connection finished by inactivity'
)

# INACTIVETIMEOUT changed
RE_TIMEOUT_CHANGED = re.compile(
    r'INACTIVETIMEOUT changed from \[(\d+)\].*?to \[(\d+)\]'
)

# OPEN EMPTY RPO
RE_EMPTY_RPO = re.compile(
    r'OPEN EMPTY RPO.*?Environment\s+(\w+).*?File\s+(.*?)$'
)

# Shutdown messages
RE_SHUTDOWN = re.compile(
    r'Application Server.*?in shutdown|Application SHUTDOWN in progress|APPSERVER WAS NOT SHUTDOWN PROPERLY'
)

# Server running (startup complete)
RE_SERVER_RUNNING = re.compile(
    r'Totvs Application Server is running'
)

# REST API errors
RE_REST_ERROR = re.compile(
    r'Fail to write response.*?Error:\s*(-?\d+)'
)

# Closing connections retries (shutdown lento)
RE_CLOSING_CONN = re.compile(
    r'Closing connections\.\.\s*Retry:\s*(\d+)'
)

# WARNING genérico do Protheus
RE_WARNING_GENERIC = re.compile(
    r'\[WARNING\]\s*-?\s*(.*?)$'
)

# SQL com erro (no error.log)
RE_SQL_ERROR = re.compile(
    r'(SELECT|INSERT|UPDATE|DELETE)\s+.*?\s+on\s+(\w+\.\w+)\s+', re.IGNORECASE
)

# Error 500 (REST)
RE_ERROR_500 = re.compile(r'Error 500')

# CheckAuth ERROR
RE_CHECK_AUTH = re.compile(r'CheckAuth ERROR:\s*(.*?)$')

# Syntax Error (compilação)
RE_SYNTAX_ERROR = re.compile(r'(\w+\.PRW)\((\d+)\)\s+(C\d+)\s+Syntax Error')

# Compile/build error genérico
RE_COMPILE_ERROR = re.compile(r'(\w+\.PRW)\((\d+)\)\s+(C\d+)\s+(.*?)$')

# =====================================================================
# DICAS DE CORREÇÃO (baseado na base de conhecimento erros_protheus.md)
# Mapeamento: (category, regex no message/raw_line) → dica de correção
# =====================================================================

CORRECTION_TIPS = [
    # --- DATABASE / TOPCONN ---
    ('database', re.compile(r'TOPCONN.*TC_Blob_Length', re.IGNORECASE),
     'Verificar campo Memo/BLOB no banco. Pode estar corrompido ou excedendo limite. '
     'Confirmar compatibilidade TopConnect x banco de dados.'),

    ('database', re.compile(r'TOPCONN.*NO CONNECTION|TC_FilterEx.*NO CONNECTION', re.IGNORECASE),
     'Conexão com banco perdida. Verificar: rede, serviço do banco ativo, '
     'timeout de conexão no appserver.ini. Usar TCIsConnected() antes de operar.'),

    ('database', re.compile(r'TOPCONN.*FILE_IN_USE|Create error.*-15', re.IGNORECASE),
     'Tabela em uso por outro processo. Verificar transações pendentes e sessões '
     'ativas no banco (sp_who2 no SQL Server).'),

    ('database', re.compile(r'TOPCONN.*COMMAND_FAILED|Create error.*-19', re.IGNORECASE),
     'Comando SQL falhou. Verificar: sintaxe SQL, permissões do usuário de conexão, '
     'se o objeto já existe no banco.'),

    ('database', re.compile(r'TOPCONN.*Insert.*-27|Cannot Insert Duplicate', re.IGNORECASE),
     'Violação de constraint (chave duplicada ou NOT NULL). Verificar unicidade da chave '
     'e campos obrigatórios antes da gravação.'),

    ('database', re.compile(r'TOPCONN.*field value size.*not 8.*SetField', re.IGNORECASE),
     'Campo Date recebendo valor com tamanho incorreto. Usar DToS(dData) para '
     'converter para formato "YYYYMMDD" antes do SetField.'),

    ('database', re.compile(r'Query greater than 15980', re.IGNORECASE),
     'Query SQL excede 15980 bytes. Quebrar em múltiplas queries ou usar tabela '
     'temporária para a lista de valores.'),

    ('database', re.compile(r'Too many fields.*255', re.IGNORECASE),
     'Query com mais de 255 campos. Selecionar apenas campos necessários ao invés de SELECT *.'),

    ('database', re.compile(r'ORA-', re.IGNORECASE),
     'Erro Oracle detectado. Verificar o código ORA-XXXXX na documentação Oracle. '
     'Causas comuns: lock de registro, tablespace cheio, sessões excedidas.'),

    ('database', re.compile(r'TC_ALTER FAILED.*INVALID.*CORRUPTED', re.IGNORECASE),
     'Tabela com estrutura corrompida. Fazer backup, verificar integridade com '
     'ferramentas do banco e recriar a tabela via SX3 se necessário.'),

    # --- THREAD ERROR (sub-padrões específicos baseados na raw_line) ---
    ('thread_error', re.compile(r'type mismatch', re.IGNORECASE),
     'Thread Error causado por type mismatch (tipos incompatíveis). '
     'Verificar ValType() das variáveis na linha indicada do fonte .PRW. '
     'Causas: operação aritmética com string, comparação entre tipos diferentes, '
     'retorno NIL de função onde se esperava outro tipo. Usar Val(), Str(), CToD() para converter.'),

    ('thread_error', re.compile(r'Array.*out of bounds|array.*index', re.IGNORECASE),
     'Thread Error causado por array out of bounds (acesso a posição inexistente). '
     'Validar com Len(aArray) antes de acessar. Verificar se o array foi '
     'inicializado e se o índice não excede o tamanho.'),

    ('thread_error', re.compile(r'Variable does not exist', re.IGNORECASE),
     'Thread Error causado por variável inexistente. '
     'Declarar a variável com Local/Private/Public no início da função. '
     'Verificar escopo e ortografia do nome da variável.'),

    ('thread_error', re.compile(r'Alias already in use', re.IGNORECASE),
     'Thread Error causado por alias já em uso. '
     'Fechar a work area antes de reabrir: If Select("ALIAS") > 0; '
     'ALIAS->(DBCloseArea()); EndIf antes do DBUseArea().'),

    ('thread_error', re.compile(r'Alias does not exist', re.IGNORECASE),
     'Thread Error causado por alias inexistente. A tabela pode ter sido fechada '
     'anteriormente ou não foi aberta. Verificar com Select("ALIAS") > 0 antes de acessar.'),

    ('thread_error', re.compile(r'invalid field name', re.IGNORECASE),
     'Thread Error causado por campo inexistente na tabela. '
     'Verificar a estrutura da tabela no SX3 e confirmar o nome do campo. '
     'Pode ser campo removido em atualização ou alias trocado.'),

    ('thread_error', re.compile(r'Update error.*lock required', re.IGNORECASE),
     'Thread Error causado por tentativa de gravação sem lock. '
     'Sempre usar RLock() antes de REPLACE/FieldPut() e DBUnlock() após.'),

    ('thread_error', re.compile(r'Data width error', re.IGNORECASE),
     'Thread Error causado por valor maior que o tamanho do campo. '
     'Usar SubStr() ou PadR() para limitar o valor antes de gravar.'),

    ('thread_error', re.compile(r'Memory.*Allocation|memory full', re.IGNORECASE),
     'Thread Error causado por falta de memória. '
     'Liberar objetos com FreeObj(), reduzir arrays grandes, aumentar RAM/swap.'),

    ('thread_error', re.compile(r'String size overflow', re.IGNORECASE),
     'Thread Error causado por string excedendo 64KB. '
     'Usar arquivo temporário (FCreate + FWrite) ao invés de concatenar em string.'),

    ('thread_error', re.compile(r'Division by zero|divisão por zero', re.IGNORECASE),
     'Thread Error causado por divisão por zero. '
     'Validar o divisor antes da operação: If nDivisor != 0.'),

    ('thread_error', re.compile(r'invalid typecast', re.IGNORECASE),
     'Thread Error causado por conversão de tipo inválida. '
     'Verificar os tipos antes de converter: Val() em string não numérica, '
     'CToD() com formato inválido.'),

    ('thread_error', re.compile(r'ORA-', re.IGNORECASE),
     'Thread Error com erro Oracle associado. Verificar o código ORA-XXXXX '
     'no log e na documentação Oracle. Causas comuns: lock, tablespace cheio, sessões excedidas.'),

    ('thread_error', re.compile(r'TOPCONN|NO CONNECTION', re.IGNORECASE),
     'Thread Error relacionado a perda de conexão com o banco. '
     'Verificar rede, serviço do banco ativo e timeout de conexão no appserver.ini.'),

    ('thread_error', re.compile(r'Thread Error', re.IGNORECASE),
     'Erro em thread do AppServer. Analisar o error.log completo: verificar os 5 blocos '
     '(info geral, AppServer, call stack, variáveis, arquivos abertos). '
     'Identificar a linha e função no fonte .PRW indicado no log.'),

    # --- RPO ---
    ('rpo', re.compile(r'CheckAuth ERROR|Falha autenticação RPO', re.IGNORECASE),
     'Falha na autenticação do RPO. Verificar se o RPO não está corrompido, '
     'se a versão é compatível com o AppServer e se o ambiente está configurado corretamente.'),

    ('rpo', re.compile(r'EMPTY RPO|RPO vazio', re.IGNORECASE),
     'RPO vazio no ambiente. Verificar se o arquivo RPO existe no caminho configurado, '
     'se não está corrompido e se o ambiente no appserver.ini aponta para o RPO correto.'),

    ('rpo', re.compile(r'compilation problems.*Rebuild', re.IGNORECASE),
     'RPO com problemas de compilação. Executar Rebuild RPO pelo TDS. '
     'Verificar se não há fragmentação excessiva.'),

    ('rpo', re.compile(r'cannot find function.*AppMap', re.IGNORECASE),
     'Função não encontrada no AppMap. Verificar se está compilada no RPO correto '
     'e se o nome da função está correto.'),

    ('rpo', re.compile(r'Invalid function type.*RPO', re.IGNORECASE),
     'Tipo de função inválido no RPO. Verificar compatibilidade de versão RPO x AppServer. '
     'Recompilar com a versão correta do compilador.'),

    ('rpo', re.compile(r'Invalid repository.*incomplete compil', re.IGNORECASE),
     'RPO inválido por compilação incompleta. Restaurar backup do RPO anterior '
     'ou executar Rebuild RPO do zero.'),

    # --- NETWORK / SSL ---
    ('network', re.compile(r'SSL.*timeout|SSL.*fail', re.IGNORECASE),
     'Falha de conexão SSL. Verificar: certificado válido/expirado, compatibilidade '
     'de protocolo TLS, firewall/proxy, e conectividade de rede com o host remoto.'),

    ('network', re.compile(r'SSL.*Unable to receive.*zero return', re.IGNORECASE),
     'Conexão SSL encerrada pelo lado remoto. Verificar certificado SSL, versão de '
     'protocolo TLS e se o firewall não está interceptando.'),

    ('network', re.compile(r'TLS Initialization Error', re.IGNORECASE),
     'Falha ao inicializar TLS. Verificar arquivos .pem/.crt/.key nos caminhos '
     'configurados e seção [HTTPS] no appserver.ini.'),

    ('network', re.compile(r'bind error 10048', re.IGNORECASE),
     'Porta TCP já em uso. Verificar processos na porta com netstat/ss. '
     'Encerrar processos duplicados ou alterar porta no appserver.ini.'),

    # --- CONNECTION ---
    ('connection', re.compile(r'inatividade|inactivity', re.IGNORECASE),
     'Desconexão por inatividade. Se frequente, verificar INACTIVETIMEOUT no appserver.ini. '
     'Pode indicar que usuários deixam sessões abertas sem uso.'),

    ('connection', re.compile(r'Error ending thread', re.IGNORECASE),
     'Erro ao encerrar thread. Pode indicar que o processo tinha recursos não liberados '
     '(tabelas abertas, objetos não destruídos). Verificar o fluxo de finalização.'),

    ('connection', re.compile(r'Too Many users', re.IGNORECASE),
     'Limite de licenças atingido. Encerrar sessões fantasma pelo Monitor do AppServer. '
     'Verificar jobs automáticos que não liberam conexão.'),

    ('connection', re.compile(r'pthread_create.*12', re.IGNORECASE),
     'Limite de threads do Linux atingido. Aumentar ulimit -u e ulimit -s. '
     'Monitorar número de conexões simultâneas.'),

    # --- SERVICE ---
    ('service', re.compile(r'HTTP Server.*fail', re.IGNORECASE),
     'HTTP Server falhou ao iniciar. Verificar se a porta já está em uso, '
     'configuração da seção [HTTP] no appserver.ini e permissões.'),

    # --- REST API ---
    ('rest_api', re.compile(r'Error 500|Fail to write response', re.IGNORECASE),
     'Erro 500 na REST API. Verificar logs detalhados do erro, '
     'parâmetros da requisição e se o serviço REST está configurado corretamente.'),

    # --- COMPILATION ---
    ('compilation', re.compile(r'Syntax Error', re.IGNORECASE),
     'Erro de sintaxe na compilação. Verificar o fonte .PRW na linha indicada. '
     'Causas comuns: parênteses, aspas não fechadas, palavra-chave mal escrita.'),

    # --- AUTHENTICATION ---
    ('authentication', re.compile(r'AD.*Auth|ADUSERVALID|LogonUser', re.IGNORECASE),
     'Erro de autenticação AD/LDAP. Verificar: credenciais do domínio, '
     'conectividade com o servidor AD, e configuração LDAP no appserver.ini.'),

    # --- SHUTDOWN ---
    ('shutdown', re.compile(r'Closing connections.*Retry', re.IGNORECASE),
     'Shutdown lento com retries. Há conexões que não estão sendo liberadas. '
     'Verificar processos/jobs travados que impedem o encerramento limpo.'),

    # --- LIFECYCLE ---
    ('lifecycle', re.compile(r'NOT SHUTDOWN PROPERLY|crash|kill', re.IGNORECASE),
     'AppServer não foi encerrado corretamente (crash ou kill forçado). '
     'Verificar logs anteriores ao crash para identificar a causa raiz. '
     'Pode causar corrupção em tabelas CTree/DBF.'),

    # --- APPLICATION (WARNING genérico) ---
    ('application', re.compile(r'Alias already in use', re.IGNORECASE),
     'Alias já em uso. Fechar a work area antes de reabrir: '
     'If Select("ALIAS") > 0; ALIAS->(DBCloseArea()); EndIf.'),

    ('application', re.compile(r'Alias does not exist', re.IGNORECASE),
     'Alias não existe. A tabela pode ter sido fechada anteriormente. '
     'Sempre verificar com Select("ALIAS") > 0 antes de acessar.'),

    ('application', re.compile(r'Array.*out of bounds|Array.*index', re.IGNORECASE),
     'Acesso a posição inexistente do array. Validar com Len(aArray) antes de acessar. '
     'Verificar se o array foi inicializado corretamente.'),

    ('application', re.compile(r'Variable does not exist', re.IGNORECASE),
     'Variável não declarada. Declarar com Local/Private/Public no início da função. '
     'Ativar warnings do compilador para detectar.'),

    ('application', re.compile(r'type mismatch', re.IGNORECASE),
     'Tipos incompatíveis na operação. Verificar ValType() das variáveis envolvidas. '
     'Usar Val(), Str(), CToD(), DToS() para converter adequadamente.'),

    ('application', re.compile(r'Memory.*Allocation.*Failure|memory full', re.IGNORECASE),
     'Memória esgotada. Liberar objetos com FreeObj(). Substituir arrays grandes '
     'por queries. Aumentar RAM/swap do servidor.'),

    ('application', re.compile(r'String size overflow', re.IGNORECASE),
     'String excedeu 64KB. Usar arquivo temporário ao invés de acumular em string. '
     'FCreate() + FWrite() para conteúdo grande.'),

    ('application', re.compile(r'Update error.*lock required', re.IGNORECASE),
     'Tentativa de gravar sem lock. Sempre usar RLock() antes de REPLACE/FieldPut() '
     'e DBUnlock() após a gravação.'),

    ('application', re.compile(r'Data width error', re.IGNORECASE),
     'Valor maior que o tamanho do campo. Usar SubStr() ou PadR() para limitar '
     'o tamanho antes de gravar.'),

    ('application', re.compile(r'Filter greater than 2000', re.IGNORECASE),
     'Filtro excede 2000 bytes. Dividir em múltiplas passagens ou usar tabela temporária. '
     'Converter para query SQL quando possível.'),

    ('application', re.compile(r'Number of locks exceeded', re.IGNORECASE),
     'Limite de 10000 locks atingido. Garantir DBUnlock() após cada RLock() em loops. '
     'Não manter locks abertos em transações longas.'),
]


def get_correction_tip(category, message, raw_line=''):
    """
    Retorna uma dica de correção baseada na categoria e mensagem do alerta.
    Busca no dicionário CORRECTION_TIPS por match de regex.

    Returns:
        str ou None: dica de correção encontrada
    """
    text = f"{message} {raw_line}"
    for tip_category, tip_pattern, tip_text in CORRECTION_TIPS:
        if tip_category == category and tip_pattern.search(text):
            return tip_text
    # Fallback por categoria genérica
    category_fallbacks = {
        'database': 'Verificar conexão com banco de dados, logs do TopConnect e status do serviço SQL.',
        'thread_error': 'Analisar o error.log completo (5 blocos: info, AppServer, call stack, variáveis, arquivos).',
        'rpo': 'Verificar integridade do RPO, compatibilidade de versão e executar Rebuild se necessário.',
        'network': 'Verificar conectividade de rede, certificados SSL e configurações de firewall.',
        'connection': 'Verificar timeout de sessão e status das conexões no Monitor do AppServer.',
        'service': 'Verificar configuração de portas e serviços no appserver.ini.',
        'rest_api': 'Verificar configuração da REST API e logs detalhados do erro.',
        'compilation': 'Verificar o fonte .PRW na linha indicada e recompilar.',
        'authentication': 'Verificar credenciais e conectividade com servidor de autenticação.',
        'shutdown': 'Verificar processos travados que impedem encerramento limpo.',
        'lifecycle': 'Evento de ciclo de vida do AppServer. Verificar logs adjacentes para contexto.',
        'application': 'Verificar o error.log para detalhes do erro e análise do call stack.',
    }
    return category_fallbacks.get(category)


# =====================================================================
# REGRAS DE CLASSIFICAÇÃO
# =====================================================================

ALERT_RULES = [
    # (regex, severity, category, description_fn)
    # --- CRITICAL ---
    (RE_TOPCONN, 'critical', 'database',
     lambda m: f"TOPCONN: {m.group(1).strip()}"),

    (RE_ORA_ERROR, 'critical', 'database',
     lambda m: f"{m.group(1)}: {m.group(2).strip()}"),

    (RE_THREAD_ERROR, 'critical', 'thread_error',
     lambda m: f"Thread Error na rotina {m.group(2)} (Thread {m.group(1)})"),

    (RE_CHECK_AUTH, 'critical', 'rpo',
     lambda m: f"Falha autenticação RPO: {m.group(1).strip()}"),

    (RE_SYNTAX_ERROR, 'critical', 'compilation',
     lambda m: f"Erro de compilação: {m.group(1)} linha {m.group(2)} ({m.group(3)})"),

    (RE_HTTP_FAIL, 'critical', 'service',
     lambda m: f"HTTP Server falhou ao iniciar (erro {m.group(1)})"),

    (RE_ERROR_500, 'critical', 'rest_api',
     lambda m: "Erro 500 na REST API"),

    (RE_REST_ERROR, 'critical', 'rest_api',
     lambda m: f"Falha na resposta REST (erro {m.group(1)})"),

    # --- WARNING ---
    (RE_AD_ERROR, 'warning', 'authentication',
     lambda m: f"AD Auth erro {m.group(1)}: {m.group(2).strip()}"),

    (RE_SSL_FAIL, 'warning', 'network',
     lambda m: f"Falha SSL timeout: {m.group(1)}"),

    (RE_EMPTY_RPO, 'warning', 'rpo',
     lambda m: f"RPO vazio - Ambiente {m.group(1)}: {m.group(2).strip()}"),

    (RE_ERROR_ENDING_THREAD, 'warning', 'connection',
     lambda m: f"Erro encerrando thread ({m.group(1)}, {m.group(2)}): {m.group(3).strip()}"),

    (RE_CLOSING_CONN, 'warning', 'shutdown',
     lambda m: f"Shutdown lento - Retry {m.group(1)} fechando conexões"),

    (RE_INACTIVITY, 'warning', 'connection',
     lambda m: "Desconexão por inatividade"),

    (RE_WARNING_GENERIC, 'warning', 'application',
     lambda m: m.group(1).strip()[:200]),

    # --- INFO ---
    (RE_SHUTDOWN, 'info', 'lifecycle',
     lambda m: m.group(0).strip()),

    (RE_SERVER_RUNNING, 'info', 'lifecycle',
     lambda m: "AppServer iniciado com sucesso"),

    (RE_THREAD_FINISHED, 'info', 'connection',
     lambda m: f"Usuário desconectou: {m.group(1)} ({m.group(2)})"),
]

# Regras de métricas (não geram alerta, mas são parseadas para dashboard)
METRIC_RULES = [
    (RE_MEMORY_OS, 'memory_os',
     lambda m: {'total_mb': float(m.group(1)), 'used_mb': float(m.group(2)), 'free_mb': float(m.group(3))}),

    (RE_MEMORY_APP, 'memory_app',
     lambda m: {'resident_mb': float(m.group(1))}),

    (RE_START_TIME, 'start_time',
     lambda m: {'seconds': float(m.group(1))}),

    (RE_TIMEOUT_CHANGED, 'timeout_change',
     lambda m: {'from_seconds': int(m.group(1)), 'to_seconds': int(m.group(2))}),
]

# Padrões que devem ser ignorados (ruído operacional)
IGNORE_PATTERNS = [
    re.compile(r'deleting thread Pool'),
    re.compile(r'deleting server,'),
    re.compile(r'Deleting jobs from Threadpool'),
    re.compile(r'Function \'\w+\' has more than 10 characters'),
    re.compile(r'has more than 10 characters in a "\.prw" source'),
    re.compile(r'POWERSCHEMES.*Thread'),
    re.compile(r'^\s*Field \d+:'),
    re.compile(r'^\s*Index \(\d+\)'),
    re.compile(r'^\s*Public \d+:'),
    re.compile(r'^\s*Local \d+:'),
    re.compile(r'^\s*Private \d+:'),
    re.compile(r'^\s*Static \d+:'),
]


def _should_ignore(line):
    """Verifica se a linha deve ser ignorada (ruído operacional)."""
    for pattern in IGNORE_PATTERNS:
        if pattern.search(line):
            return True
    return False


def _extract_timestamp(line):
    """Extrai timestamp ISO da linha do console.log."""
    m = RE_TIMESTAMP.match(line)
    if m:
        ts_str = m.group(1)
        try:
            return datetime.fromisoformat(ts_str)
        except (ValueError, TypeError):
            pass
    return None


def _extract_thread_id(line):
    """Extrai thread ID da linha."""
    m = re.search(r'\[Thread\s+(\d+)\]', line)
    if m:
        return m.group(1)
    m = RE_TIMESTAMP.match(line)
    if m:
        return m.group(2)
    return None


def parse_log_lines(lines, source_file='console.log', start_line=0):
    """
    Parseia linhas de log do Protheus e retorna alertas e métricas encontrados.

    Args:
        lines: lista de strings (linhas do log)
        source_file: nome do arquivo de origem
        start_line: número da primeira linha (para offset)

    Returns:
        tuple: (alerts, metrics)
            alerts: list of dict com campos para log_alerts
            metrics: list of dict com métricas extraídas
    """
    alerts = []
    metrics = []
    current_timestamp = None
    current_thread_error_block = None

    def _get_next_line(idx):
        """Retorna a próxima linha não-vazia (contexto do erro)."""
        for j in range(idx + 1, min(idx + 6, len(lines))):
            nl = lines[j].rstrip('\n\r').strip()
            if nl:
                return nl
        return None

    for i, line in enumerate(lines):
        line = line.rstrip('\n\r')
        if not line.strip():
            continue

        # Atualiza timestamp corrente
        ts = _extract_timestamp(line)
        if ts:
            current_timestamp = ts

        # Ignora ruído
        if _should_ignore(line):
            continue

        # Detecta bloco THREAD ERROR (error.log)
        m = RE_THREAD_ERROR.search(line)
        if m:
            current_thread_error_block = {
                'thread_id': m.group(1),
                'routine': m.group(2),
                'date': m.group(3),
                'time': m.group(4),
            }
            try:
                current_timestamp = datetime.strptime(
                    f"{m.group(3)} {m.group(4)}", "%d/%m/%Y %H:%M:%S"
                )
            except ValueError:
                pass
            _msg = f"Thread Error na rotina {m.group(2)} (Thread {m.group(1)})"
            _raw = (line[:500] + ('\n' + _get_next_line(i) if _get_next_line(i) else ''))[:1000]
            _tip = get_correction_tip('thread_error', _msg, _raw)
            _details = dict(current_thread_error_block) if current_thread_error_block else {}
            if _tip:
                _details['correction_tip'] = _tip
            alerts.append({
                'severity': 'critical',
                'category': 'thread_error',
                'message': _msg,
                'raw_line': _raw,
                'source_file': source_file,
                'line_number': start_line + i + 1,
                'thread_id': m.group(1),
                'occurred_at': current_timestamp,
                'details': _details or None,
            })
            continue

        # Verifica erros Oracle dentro do bloco de THREAD ERROR
        m = RE_ORA_ERROR.search(line)
        if m:
            _msg = f"{m.group(1)}: {m.group(2).strip()}"[:200]
            _raw = (line[:500] + ('\n' + _get_next_line(i) if _get_next_line(i) else ''))[:1000]
            _tip = get_correction_tip('database', _msg, _raw)
            _details = {'ora_code': m.group(1)}
            if _tip:
                _details['correction_tip'] = _tip
            alerts.append({
                'severity': 'critical',
                'category': 'database',
                'message': _msg,
                'raw_line': _raw,
                'source_file': source_file,
                'line_number': start_line + i + 1,
                'thread_id': _extract_thread_id(line),
                'occurred_at': current_timestamp,
                'details': _details,
            })
            continue

        # Verifica erros TOPCONN
        m = RE_TOPCONN.search(line)
        if m:
            _msg = f"TOPCONN: {m.group(1).strip()}"[:200]
            _raw = (line[:500] + ('\n' + _get_next_line(i) if _get_next_line(i) else ''))[:1000]
            _tip = get_correction_tip('database', _msg, _raw)
            _details = {}
            if _tip:
                _details['correction_tip'] = _tip
            alerts.append({
                'severity': 'critical',
                'category': 'database',
                'message': _msg,
                'raw_line': _raw,
                'source_file': source_file,
                'line_number': start_line + i + 1,
                'thread_id': _extract_thread_id(line),
                'occurred_at': current_timestamp,
                'details': _details or None,
            })
            continue

        # Verifica shutdown impróprio (linha especial sem prefixo)
        if 'APPSERVER WAS NOT SHUTDOWN PROPERLY' in line:
            _msg = 'AppServer NÃO foi encerrado corretamente (crash ou kill forçado)'
            _raw = (line[:500] + ('\n' + _get_next_line(i) if _get_next_line(i) else ''))[:1000]
            _tip = get_correction_tip('lifecycle', _msg, _raw)
            _details = {}
            if _tip:
                _details['correction_tip'] = _tip
            alerts.append({
                'severity': 'critical',
                'category': 'lifecycle',
                'message': _msg,
                'raw_line': _raw,
                'source_file': source_file,
                'line_number': start_line + i + 1,
                'thread_id': None,
                'occurred_at': current_timestamp,
                'details': _details or None,
            })
            continue

        # Aplica regras de alerta na ordem de prioridade
        matched = False
        for pattern, severity, category, desc_fn in ALERT_RULES:
            m = pattern.search(line)
            if m:
                # Extrai usuario/computador se disponível
                username = None
                computer = None
                tf = RE_THREAD_FINISHED.search(line)
                if tf:
                    username = tf.group(1)
                    computer = tf.group(2)
                eet = RE_ERROR_ENDING_THREAD.search(line)
                if eet:
                    username = eet.group(1)
                    computer = eet.group(2)

                _msg = desc_fn(m)[:200]
                _raw = (line[:500] + ('\n' + _get_next_line(i) if _get_next_line(i) else ''))[:1000]
                _tip = get_correction_tip(category, _msg, _raw)
                _details = {}
                if _tip:
                    _details['correction_tip'] = _tip
                alerts.append({
                    'severity': severity,
                    'category': category,
                    'message': _msg,
                    'raw_line': _raw,
                    'source_file': source_file,
                    'line_number': start_line + i + 1,
                    'thread_id': _extract_thread_id(line),
                    'username': username,
                    'computer_name': computer,
                    'occurred_at': current_timestamp,
                    'details': _details or None,
                })
                matched = True
                break

        if matched:
            continue

        # Verifica métricas
        for pattern, metric_type, extract_fn in METRIC_RULES:
            m = pattern.search(line)
            if m:
                metrics.append({
                    'type': metric_type,
                    'values': extract_fn(m),
                    'occurred_at': current_timestamp,
                    'source_file': source_file,
                    'line_number': start_line + i + 1,
                })
                break

    return alerts, metrics


# =====================================================================
# LEITURA REMOTA DE LOGS VIA SSH / LOCAL
# =====================================================================

def _resolve_environment_suffix(environment_id):
    """Resolve o sufixo da variável (PRD, HOM, DEV, TST) a partir do environment_id."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name FROM environments WHERE id = %s", (environment_id,))
        env = cursor.fetchone()
    finally:
        release_db_connection(conn)

    if not env:
        return None

    env_name = env['name'].lower()
    suffix_map = {
        'produção': 'PRD', 'producao': 'PRD', 'production': 'PRD',
        'homologação': 'HOM', 'homologacao': 'HOM', 'homolog': 'HOM',
        'desenvolvimento': 'DEV', 'development': 'DEV', 'dev': 'DEV',
        'testes': 'TST', 'tests': 'TST', 'test': 'TST', 'qa': 'TST',
    }
    return suffix_map.get(env_name, 'PRD')


def _get_server_variables(suffix):
    """Busca todas as server_variables relevantes para o sufixo do ambiente."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT name, value FROM server_variables WHERE name LIKE %s",
            (f'%_{suffix}',)
        )
        return {row['name']: row['value'] for row in cursor.fetchall()}
    finally:
        release_db_connection(conn)


def _resolve_log_path(config, variables, suffix):
    """
    Resolve o caminho completo do log usando server_variables.

    O log_path pode ser:
    - Nome do arquivo apenas (ex: 'console.log') → usa LOG_DIR_{SUFFIX} como base
    - Caminho completo (ex: 'C:\\logs\\console.log') → usa diretamente
    - Com variáveis (ex: '{{LOG_DIR}}/console.log') → resolve variáveis
    """
    log_path = config['log_path']
    os_type = config.get('os_type', 'windows')

    # Substitui variáveis {{NOME}} pelo valor com sufixo
    import re as _re
    def replace_var(match):
        var_name = match.group(1)
        # Tenta com sufixo primeiro, depois sem
        return variables.get(f'{var_name}_{suffix}', variables.get(var_name, match.group(0)))

    log_path = _re.sub(r'\{\{(\w+)\}\}', replace_var, log_path)

    # Se é apenas nome de arquivo (sem separador de caminho), prepende LOG_DIR
    is_just_filename = '/' not in log_path and '\\' not in log_path
    if is_just_filename:
        log_dir = variables.get(f'LOG_DIR_{suffix}', '')
        if log_dir:
            separator = '\\' if os_type == 'windows' else '/'
            log_path = f"{log_dir.rstrip('/').rstrip(chr(92))}{separator}{log_path}"

    return log_path


def read_log_remote(config, from_line=0, max_lines=5000):
    """
    Lê linhas de um arquivo de log remoto via SSH ou local.

    O caminho do log é resolvido usando server_variables do ambiente:
    - LOG_DIR_{SUFFIX}: diretório base dos logs
    - SSH_HOST_WINDOWS_{SUFFIX}: host SSH
    - SSH_USER_WINDOWS_{SUFFIX}: usuário SSH
    - SSH_PORT_WINDOWS_{SUFFIX}: porta SSH

    Args:
        config: dict com os dados de log_monitor_configs
        from_line: posição (linha) a partir da qual ler
        max_lines: número máximo de linhas para ler

    Returns:
        tuple: (lines, total_lines_read) ou (None, 0) em caso de erro
    """
    os_type = config.get('os_type', 'windows')

    # Resolve sufixo do ambiente
    suffix = _resolve_environment_suffix(config['environment_id'])
    if not suffix:
        return None, 0

    # Busca variáveis do servidor
    variables = _get_server_variables(suffix)

    # Resolve caminho completo do log
    log_path = _resolve_log_path(config, variables, suffix)

    # Tenta leitura local primeiro (arquivo acessível no mesmo servidor)
    local_lines = _read_log_local(log_path, from_line, max_lines)
    if local_lines is not None:
        return local_lines, len(local_lines)

    # Arquivo não existe localmente — tenta SSH remoto
    if os_type == 'windows':
        ssh_host = variables.get(f'SSH_HOST_WINDOWS_{suffix}', '')
        ssh_user = variables.get(f'SSH_USER_WINDOWS_{suffix}', '')
        ssh_port = variables.get(f'SSH_PORT_WINDOWS_{suffix}', '22')

        if not ssh_host or not ssh_user:
            return None, 0

        # PowerShell: lê arquivo com skip e take
        ps_command = (
            f"Get-Content '{log_path}' "
            f"| Select-Object -Skip {from_line} -First {max_lines}"
        )
        cmd = [
            'ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=10',
            '-p', ssh_port,
            f'{ssh_user}@{ssh_host}',
            'powershell', '-Command', ps_command
        ]
    else:
        ssh_host = variables.get(f'SSH_HOST_LINUX_{suffix}', variables.get(f'SSH_HOST_WINDOWS_{suffix}', ''))
        ssh_user = variables.get(f'SSH_USER_LINUX_{suffix}', variables.get(f'SSH_USER_WINDOWS_{suffix}', ''))
        ssh_port = variables.get(f'SSH_PORT_LINUX_{suffix}', variables.get(f'SSH_PORT_WINDOWS_{suffix}', '22'))

        if not ssh_host or not ssh_user:
            return None, 0

        safe_path = shlex.quote(log_path)
        remote_cmd = f"tail -n +{from_line + 1} {safe_path} | head -n {max_lines}"
        cmd = [
            'ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=10',
            '-p', ssh_port,
            f'{ssh_user}@{ssh_host}',
            remote_cmd
        ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            encoding='utf-8',
            errors='replace'
        )
        if result.returncode != 0:
            return None, 0

        lines = result.stdout.splitlines()
        return lines, len(lines)

    except (subprocess.TimeoutExpired, Exception):
        return None, 0


def _read_log_local(log_path, from_line=0, max_lines=5000):
    """
    Tenta ler o arquivo de log localmente (mesmo servidor).
    Retorna lista de linhas se o arquivo existir, None caso contrário.
    """
    if not os.path.isfile(log_path):
        return None

    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            # Pula até from_line
            for _ in range(from_line):
                if not f.readline():
                    break
            # Lê max_lines
            lines = []
            for _ in range(max_lines):
                line = f.readline()
                if not line:
                    break
                lines.append(line.rstrip('\n').rstrip('\r'))
        return lines
    except (OSError, PermissionError):
        return None


# =====================================================================
# SCAN DE LOG: PARSEIA E SALVA ALERTAS NO BANCO
# =====================================================================

def scan_log(config_id, flask_app=None):
    """
    Executa um scan completo de um log configurado.
    Lê a partir da última posição, parseia e salva alertas novos.

    Args:
        config_id: ID do log_monitor_configs
        flask_app: instância Flask (para contexto em threads)

    Returns:
        dict com resultado do scan
    """
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM log_monitor_configs WHERE id = %s", (config_id,))
        config = cursor.fetchone()

        if not config:
            return {'success': False, 'error': 'Configuração não encontrada'}

        config = dict(config)
        from_line = config.get('last_read_position', 0) or 0

        # Lê novas linhas
        lines, count = read_log_remote(config, from_line=from_line)

        if lines is None:
            return {'success': False, 'error': 'Falha ao ler log remoto'}

        if count == 0:
            # Atualiza last_read_at mesmo sem linhas novas
            cursor.execute(
                "UPDATE log_monitor_configs SET last_read_at = %s WHERE id = %s",
                (datetime.now(), config_id)
            )
            conn.commit()
            return {'success': True, 'alerts_count': 0, 'lines_read': 0}

        # Parseia as linhas
        source_file = config.get('log_path', 'unknown').split('\\')[-1].split('/')[-1]
        alerts, metrics = parse_log_lines(lines, source_file=source_file, start_line=from_line)

        # Filtra apenas critical e warning para salvar (info é muito volume)
        alerts_to_save = [a for a in alerts if a['severity'] in ('critical', 'warning')]

        # Salva alertas no banco
        saved_count = 0
        for alert in alerts_to_save:
            try:
                import json
                cursor.execute("""
                    INSERT INTO log_alerts
                        (config_id, environment_id, severity, category, message,
                         raw_line, source_file, line_number, thread_id,
                         username, computer_name, occurred_at, details)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    config_id,
                    config['environment_id'],
                    alert['severity'],
                    alert['category'],
                    alert['message'],
                    alert.get('raw_line'),
                    alert.get('source_file'),
                    alert.get('line_number'),
                    alert.get('thread_id'),
                    alert.get('username'),
                    alert.get('computer_name'),
                    alert.get('occurred_at'),
                    json.dumps(alert.get('details')) if alert.get('details') else None,
                ))
                saved_count += 1
            except Exception:
                pass  # Ignora duplicatas ou erros individuais

        # Atualiza posição de leitura
        new_position = from_line + count
        cursor.execute(
            "UPDATE log_monitor_configs SET last_read_position = %s, last_read_at = %s WHERE id = %s",
            (new_position, datetime.now(), config_id)
        )

        conn.commit()

        # Rastrear recorrência e avaliar notificações inteligentes
        try:
            from app.services.knowledge_base import track_recurrence
            from app.services.smart_notifications import evaluate_notification_rules
            from app.services.notifier import send_email_async

            for alert in alerts_to_save:
                track_recurrence(
                    config['environment_id'],
                    alert['category'],
                    alert['message'],
                )

                # Avaliar regras de notificação inteligente
                triggered_rules = evaluate_notification_rules(
                    config['environment_id'],
                    alert['severity'],
                    alert['category'],
                )
                if triggered_rules:
                    for rule in triggered_rules:
                        if rule.get('notify_email') and rule.get('recipients'):
                            emails = [e.strip() for e in rule['recipients'].split(',') if e.strip()]
                            if emails:
                                from app.services.notifier import email_base_template
                                body = email_base_template(
                                    f"Alerta: {alert['category'].upper()}",
                                    "#dc3545",
                                    f"<p><strong>Severidade:</strong> {alert['severity']}</p>"
                                    f"<p><strong>Categoria:</strong> {alert['category']}</p>"
                                    f"<p><strong>Mensagem:</strong> {alert['message']}</p>"
                                    f"<p><strong>Regra:</strong> {rule['rule_name']}</p>",
                                )
                                send_email_async(
                                    emails,
                                    f"[AtuDIC] Alerta {alert['severity']}: {alert['category']}",
                                    body,
                                )
        except Exception:
            pass  # Não falhar o scan por erro nas notificações inteligentes

        # Broadcast SSE para alertas críticos
        critical_count = len([a for a in alerts_to_save if a['severity'] == 'critical'])
        if critical_count > 0:
            event_manager.broadcast({
                'type': 'log_alert',
                'data': {
                    'config_id': config_id,
                    'environment_id': config['environment_id'],
                    'critical_count': critical_count,
                    'total_count': saved_count,
                }
            })

        return {
            'success': True,
            'lines_read': count,
            'alerts_count': saved_count,
            'critical_count': critical_count,
            'metrics_count': len(metrics),
            'metrics': metrics,
        }

    except Exception as e:
        conn.rollback()
        return {'success': False, 'error': str(e)}
    finally:
        release_db_connection(conn)


# =====================================================================
# MONITOR DAEMON: RODA EM BACKGROUND VARRENDO LOGS PERIODICAMENTE
# =====================================================================

class LogMonitor:
    """Monitor daemon que varre logs do Protheus periodicamente."""

    def __init__(self, flask_app):
        self.flask_app = flask_app
        self._thread = None
        self._stop_event = threading.Event()
        self._running = False

    def start(self):
        if self._running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._running = True

    def stop(self):
        self._stop_event.set()
        self._running = False

    def is_running(self):
        return self._running

    def _run_loop(self):
        """Loop principal do monitor."""
        while not self._stop_event.is_set():
            try:
                self._check_all_configs()
            except Exception:
                traceback.print_exc()

            # Espera 30 segundos entre checks (interruptível)
            self._stop_event.wait(30)

    def _check_all_configs(self):
        """Verifica todos os configs ativos e executa scan se necessário."""
        conn = get_db()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM log_monitor_configs
                WHERE is_active = TRUE
                ORDER BY id
            """)
            configs = cursor.fetchall()
        finally:
            release_db_connection(conn)

        for config in configs:
            config = dict(config)
            interval = config.get('check_interval_seconds', 60)
            last_read = config.get('last_read_at')

            # Verifica se já passou o intervalo
            if last_read:
                elapsed = (datetime.now() - last_read).total_seconds()
                if elapsed < interval:
                    continue

            # Executa scan
            try:
                result = scan_log(config['id'], flask_app=self.flask_app)
                if result.get('critical_count', 0) > 0:
                    self._notify_critical(config, result)
            except Exception:
                traceback.print_exc()

    def _notify_critical(self, config, scan_result):
        """Envia notificação para alertas críticos.

        Envia SOMENTE se o monitor tem notify_emails configurado.
        Se não tem, não envia para ninguém.
        """
        critical_count = scan_result.get('critical_count', 0)
        if critical_count == 0:
            return

        # Só envia se o monitor tem destinatários configurados
        notify_emails_str = config.get('notify_emails', '') or ''
        emails = [e.strip() for e in notify_emails_str.split(',') if e.strip()]
        if not emails:
            return

        # Busca nome do ambiente
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT name FROM environments WHERE id = %s", (config['environment_id'],))
            env = cursor.fetchone()
            env_name = env['name'] if env else f"Ambiente {config['environment_id']}"

            # Verifica se SMTP está configurado
            cursor.execute("SELECT * FROM notification_settings WHERE id = 1")
            notif = cursor.fetchone()
        finally:
            release_db_connection(conn)

        if notif and notif.get('smtp_server'):
            from app.services.notifier import email_base_template

            subject = f"[AtuDIC] {critical_count} alerta(s) crítico(s) - {env_name}"

            body_content = f"""
                <h3 style="color: #c62828; margin: 0 0 16px 0; border-bottom: 2px solid #c62828; padding-bottom: 10px;">
                    Alertas Críticos Detectados
                </h3>
                <table cellpadding="8" cellspacing="0" border="0" style="width: 100%; margin-bottom: 16px;">
                    <tr style="border-bottom: 1px solid #eee;">
                        <td style="color: #666; width: 150px;">Ambiente</td>
                        <td style="color: #333; font-weight: 600;">{env_name}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #eee;">
                        <td style="color: #666;">Monitor</td>
                        <td style="color: #333;">{config.get('name', config['log_path'])}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #eee;">
                        <td style="color: #666;">Alertas críticos</td>
                        <td>
                            <span style="background-color: #c62828; color: #fff; padding: 3px 10px; border-radius: 4px; font-weight: 700; font-size: 14px;">
                                {critical_count}
                            </span>
                        </td>
                    </tr>
                    <tr style="border-bottom: 1px solid #eee;">
                        <td style="color: #666;">Total de alertas</td>
                        <td style="color: #333;">{scan_result.get('alerts_count', 0)}</td>
                    </tr>
                    <tr>
                        <td style="color: #666;">Linhas analisadas</td>
                        <td style="color: #333;">{scan_result.get('lines_read', 0)}</td>
                    </tr>
                </table>
                <p style="color: #1565c0; margin: 0;">Acesse o painel de Monitoramento do AtuDIC para detalhes e ações.</p>
            """

            body = email_base_template('Monitoramento', '#b71c1c', body_content)
            send_email_async(emails, subject, body)
