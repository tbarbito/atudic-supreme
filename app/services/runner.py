import os
import subprocess
import platform
import json
import hashlib
import shlex
import shutil
import glob
import threading
from datetime import datetime
from flask import current_app

from app.database import get_db, release_db_connection
from app.utils.helpers import get_base_dir_for_pipeline
from app.services.events import event_manager
from app.services.webhook_dispatcher import dispatch_webhook_event


# =====================================================================
# LOCK DE AMBIENTE — acesso exclusivo ao RPO por ambiente
# O Protheus exige acesso exclusivo ao repositorio de objetos (RPO).
# Duas compilacoes simultaneas no mesmo ambiente causam COMPILEERROR-300.
# =====================================================================
_env_locks = {}          # {environment_id: threading.Lock()}
_env_locks_guard = threading.Lock()  # protege o dict acima
_env_running = {}        # {environment_id: {"type": "build"|"release", "id": run_id, "pipeline": name, "started_at": dt}}


def _get_env_lock(environment_id):
    """Retorna (ou cria) o Lock para um ambiente."""
    with _env_locks_guard:
        if environment_id not in _env_locks:
            _env_locks[environment_id] = threading.Lock()
        return _env_locks[environment_id]


def acquire_env_lock(environment_id, run_type, run_id, pipeline_name=""):
    """Tenta adquirir lock do ambiente. Retorna True se conseguiu, False se ja ocupado."""
    lock = _get_env_lock(environment_id)
    acquired = lock.acquire(blocking=False)
    if acquired:
        _env_running[environment_id] = {
            "type": run_type,
            "id": run_id,
            "pipeline": pipeline_name,
            "started_at": datetime.now(),
        }
    return acquired


def release_env_lock(environment_id):
    """Libera o lock do ambiente."""
    lock = _get_env_lock(environment_id)
    _env_running.pop(environment_id, None)
    try:
        lock.release()
    except RuntimeError:
        pass  # lock ja estava liberado


def get_env_running_info(environment_id):
    """Retorna info da execucao ativa no ambiente, ou None."""
    return _env_running.get(environment_id)


def _sanitize_var_for_shell(value, shell_type='bash'):
    """Sanitiza valor de variável para uso seguro em comandos shell.

    Para bash: usa shlex.quote() para escapar metacaracteres.
    Para powershell: escapa aspas simples (única forma de injeção em strings PS).
    """
    if not isinstance(value, str):
        value = str(value)
    if shell_type == 'bash':
        return shlex.quote(value)
    elif shell_type == 'powershell':
        # Em PowerShell, aspas simples dentro de strings são escapadas dobrando-as
        return value.replace("'", "''")
    return value


def _calculate_md5(file_path):
    """Calcula o hash MD5 de um arquivo."""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()





import threading
import re
import time
import tempfile
from collections import deque
from threading import Lock

# =====================================================================
# QUEUE EM MEMÓRIA PARA STREAMING DE LOGS EM TEMPO REAL
# =====================================================================

# Estrutura: {run_id: {'logs': deque([...]), 'status': 'running'|'success'|'failed'}}
live_log_streams = {}
live_log_streams_lock = Lock()

def get_live_stream(run_id):
    """Obtém ou cria stream de logs para um run_id"""
    with live_log_streams_lock:
        if run_id not in live_log_streams:
            live_log_streams[run_id] = {
                'logs': deque(maxlen=5000),  # Máximo 5000 linhas em memória
                'status': 'running'
            }
        return live_log_streams[run_id]

def save_logs_background(flask_app, log_buffer, log_id, output, status):
    """Salva logs no banco em thread background (não bloqueia execução)"""
    def _save():
        with flask_app.app_context():
            try:
                conn = get_db()
                cursor = conn.cursor()
                
                # Inserir logs de output
                if log_buffer:
                    cursor.executemany("""
                        INSERT INTO pipeline_run_output_logs (run_id, output, log_type, created_at)
                        VALUES (%s, %s, %s, %s)
                    """, log_buffer)
                
                # Atualizar log do comando
                cursor.execute("""
                    UPDATE pipeline_run_logs 
                    SET output = %s, status = %s, finished_at = %s
                    WHERE id = %s
                """, (output, status, datetime.now(), log_id))
                
                conn.commit()
                release_db_connection(conn)
                flask_app.logger.info(f"✅ Logs salvos em background para log_id={log_id}")
            except Exception as e:
                flask_app.logger.error(f"❌ Erro ao salvar logs em background: {e}")
    
    thread = threading.Thread(target=_save, daemon=True)
    thread.start()

def push_live_log(run_id, message, level="output"):
    """Adiciona log ao stream em memória"""
    stream = get_live_stream(run_id)
    stream['logs'].append({'output': message, 'log_type': level})

def set_live_stream_status(run_id, status):
    """Define status final do stream"""
    stream = get_live_stream(run_id)
    stream['status'] = status

def cleanup_live_stream(run_id):
    """Remove stream da memória após conclusão"""
    with live_log_streams_lock:
        if run_id in live_log_streams:
            del live_log_streams[run_id]


# =====================================================================
# QUEUE EM MEMÓRIA PARA STREAMING DE LOGS EM TEMPO REAL
# =====================================================================

def _load_and_mask_variables(cursor):
    """Carrega variáveis de ambiente, identificando as sensíveis para máscara."""
    env_vars = os.environ.copy()
    cursor.execute("SELECT name, value, is_password FROM server_variables")
    all_vars = cursor.fetchall()
    protected_vars = set()
    
    for var in all_vars:
        env_vars[var["name"]] = var["value"]
        if var.get('is_password'):
            protected_vars.add(var["name"])
            
    return env_vars, protected_vars, len(all_vars), len(protected_vars)


# =====================================================================
# EXECUÇÃO DE PIPELINE (CI/CD Build) - Portado do app.py original
# =====================================================================

def execute_pipeline_run(flask_app, run_id, pipeline_id, commands, notify_emails=None, notify_whatsapp=None, environment_id=None):
    """
    Executa os comandos do pipeline em sequência.
    Thread separada para não bloquear o servidor.
    Usa pipeline_run_logs + live_log_streams para streaming em tempo real.
    """
    from app.services.notifier import send_pipeline_notification
    with flask_app.app_context():
        conn = get_db()
        cursor = conn.cursor()

        try:
            # Buscar BASE_DIR específico do ambiente da pipeline
            BASE_DIR = get_base_dir_for_pipeline(cursor, pipeline_id)
            
            # Define working_dir como BASE_DIR sem depender de repositórios
            working_dir = BASE_DIR
            
            # Buscar TODAS as variáveis de ambiente do banco
            env_vars, protected_vars, num_vars, num_protected = _load_and_mask_variables(cursor)
            
            flask_app.logger.info(f"🔧 Variáveis carregadas: {num_vars} variáveis ({num_protected} protegidas)")

            # Executar cada comando
            for idx, command in enumerate(commands, 1):
                # Criar log entry para comando
                cursor.execute("""
                    INSERT INTO pipeline_run_logs (
                        run_id, command_id, command_order, 
                        status, started_at
                    ) VALUES (%s, %s, %s, 'running', %s) RETURNING id
                """, (run_id, command["id"], idx, datetime.now()))
                
                log_id = cursor.fetchone()['id']
                conn.commit()

                flask_app.logger.info(f"🔍 Executando comando {idx}: {command.get('name', 'Sem nome')} (tipo: {command.get('type', 'INDEFINIDO')})")

                # Executar comando
                try:
                    # Substituir variáveis no comando
                    cmd_text = command["script"]
                    if "${BASE_DIR}" in cmd_text:
                        cmd_text = cmd_text.replace("${BASE_DIR}", BASE_DIR)

                    # Obter sufixo do ambiente da pipeline para substituição de variáveis
                    cursor.execute("SELECT environment_id FROM pipelines WHERE id = %s", (pipeline_id,))
                    pipe_env = cursor.fetchone()
                    env_suffix = ""
                    if pipe_env:
                        cursor.execute("SELECT name FROM environments WHERE id = %s", (pipe_env['environment_id'],))
                        env_row = cursor.fetchone()
                        if env_row:
                            suffix_map = {'Produção': 'PRD', 'Homologação': 'HOM', 'Desenvolvimento': 'DEV', 'Testes': 'TST'}
                            env_suffix = suffix_map.get(env_row['name'], '')

                    # Para PowerShell: substitui TODAS as variáveis ${NOME} pelos valores
                    if command.get("type") == "powershell":
                        # Encontra todas as variáveis ${VAR} no script
                        variables_found = re.findall(r'\$\{([A-Z_0-9]+)\}', cmd_text)

                        # Substitui cada variável pelo valor do env_vars
                        for var_name in variables_found:
                            old_pattern = f"${{{var_name}}}"
                            
                            # Tenta primeiro com sufixo do ambiente (ex: BUILD_DIR_HOM)
                            var_with_suffix = f"{var_name}_{env_suffix}" if env_suffix else var_name
                            
                            is_protected = var_name in protected_vars or var_with_suffix in protected_vars
                            if var_with_suffix in env_vars:
                                new_value = env_vars[var_with_suffix]
                                cmd_text = cmd_text.replace(old_pattern, new_value)
                                display_value = '********' if is_protected else new_value
                                flask_app.logger.info(f"  Substituiu ${{{var_name}}} por {display_value} (usando {var_with_suffix})")
                            elif var_name in env_vars:
                                # Fallback: tenta sem sufixo
                                new_value = env_vars[var_name]
                                cmd_text = cmd_text.replace(old_pattern, new_value)
                                display_value = '********' if is_protected else new_value
                                flask_app.logger.info(f"  Substituiu ${{{var_name}}} por {display_value} (sem sufixo)")
                            else:
                                flask_app.logger.warning(f"⚠️ Variável ${{{var_name}}} nem {var_with_suffix} encontrada!")

                    # Determina o comando correto baseado no tipo
                    temp_script_path = None
                    if command.get("type") == "powershell":
                        # PowerShell: usar arquivo temporário .ps1
                        ps_header = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n$ProgressPreference = 'SilentlyContinue'\n"
                        full_script = ps_header + cmd_text
                        
                        temp_script = tempfile.NamedTemporaryFile(
                            mode='w',
                            suffix='.ps1',
                            delete=False,
                            encoding='utf-8-sig'  # UTF-8 com BOM
                        )
                        temp_script.write(full_script)
                        temp_script.close()
                        temp_script_path = temp_script.name
                        
                        if platform.system() == "Windows":
                            exec_command = [
                                "powershell.exe",
                                "-NoProfile",
                                "-NoLogo",
                                "-ExecutionPolicy", "Bypass",
                                "-File", temp_script_path
                            ]
                        else:
                            exec_command = [
                                "pwsh",
                                "-NoProfile",
                                "-NoLogo",
                                "-File", temp_script_path
                            ]
                        use_shell = False

                    elif command.get("type") == "bash":
                        exec_command = cmd_text
                        use_shell = True

                    else:
                        exec_command = cmd_text
                        use_shell = True

                    # Buffer para salvar no banco NO FINAL (histórico)
                    log_buffer = []
                    
                    def log_build(message, level="info"):
                        # 1. Envia para stream em memória (tempo real - SSE)
                        push_live_log(run_id, message, level)
                        # 2. Acumula para salvar no banco depois (histórico)
                        log_buffer.append((run_id, message, level, datetime.now()))
                    
                    start_exec_time = time.time()
                    
                    log_build(f"🚀 Iniciando comando: {command.get('name', 'Comando')}", "info")
                    log_build(f"📋 Tipo: {command.get('type', 'bash')}", "info")
                    log_build("─" * 50, "info")
                    
                    # Usar Popen para capturar output em tempo real
                    process = subprocess.Popen(
                        exec_command,
                        shell=use_shell,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding='utf-8',
                        errors='replace',
                        cwd=working_dir if command.get("type") != "powershell" else None,
                        env=env_vars
                    )
                    
                    output_lines = []
                    
                    # Ler output linha por linha
                    try:
                        for line in process.stdout:
                            line = line.rstrip('\n\r')
                            if line:
                                output_lines.append(line)
                                log_build(line, "output")
                        
                        process.wait(timeout=3600)
                        
                        # Cleanup do script temporário PowerShell
                        if temp_script_path:
                            try:
                                os.unlink(temp_script_path)
                            except Exception:
                                pass

                    except subprocess.TimeoutExpired:
                        process.kill()
                        log_build("❌ Comando excedeu o tempo limite de 1 hora", "error")
                        raise

                    exec_duration = time.time() - start_exec_time

                    output = '\n'.join(output_lines)
                    status = "success" if process.returncode == 0 else "failed"
                    
                    # Log de conclusão
                    if status == "success":
                        log_build(f"✅ Comando concluído com sucesso! (Duração: {exec_duration:.2f}s)", "success")
                    else:
                        log_build(f"❌ Comando falhou com código {process.returncode}", "error")
                    
                    # Salvar logs em background (não bloqueia)
                    save_logs_background(flask_app, log_buffer.copy(), log_id, output, status)
                    
                    # Se comando falhou, parar pipeline
                    if status == "failed":
                        raise Exception(f"Comando '{command.get('name', 'desconhecido')}' falhou com código {process.returncode}")
                        
                except subprocess.TimeoutExpired:
                    error_msg = f"Comando excedeu o tempo limite de 1 hora"
                    cursor.execute("""
                        UPDATE pipeline_run_logs 
                        SET output = %s, status = 'failed', finished_at = %s
                        WHERE id = %s
                    """, (error_msg, datetime.now(), log_id))
                    conn.commit()
                    raise Exception(error_msg)
                    
                except Exception as e:
                    # Garantir que status está como 'failed'
                    cursor.execute("""
                        UPDATE pipeline_run_logs 
                        SET status = 'failed', finished_at = %s
                        WHERE id = %s
                    """, (datetime.now(), log_id))
                    conn.commit()
                    raise
            
            # Pipeline executado com sucesso
            cursor.execute("""
                UPDATE pipeline_runs 
                SET status = 'success', finished_at = %s
                WHERE id = %s
            """, (datetime.now(), run_id))
            conn.commit()
            
            # Atualizar status do stream
            set_live_stream_status(run_id, 'success')
            
            # Se foi execução via schedule e incluiu comandos de deploy, criar release automaticamente
            cursor.execute("""
                SELECT trigger_type, environment_id, pipeline_id, started_by 
                FROM pipeline_runs 
                WHERE id = %s
            """, (run_id,))
            run_info = cursor.fetchone()

            if run_info and run_info['trigger_type'] == 'scheduled':
                has_deploy = any(cmd.get('command_category') == 'deploy' for cmd in commands)
                if has_deploy:
                    cursor.execute(
                        "SELECT deploy_command_id FROM pipelines WHERE id = %s",
                        (run_info['pipeline_id'],)
                    )
                    pipeline_info = cursor.fetchone()
                    deploy_command_id = pipeline_info['deploy_command_id'] if pipeline_info else None

                    if deploy_command_id:
                        cursor.execute(
                            "SELECT MAX(release_number) as last FROM releases WHERE pipeline_id = %s",
                            (run_info['pipeline_id'],)
                        )
                        last_release = cursor.fetchone()
                        release_number = (last_release['last'] if last_release['last'] else 0) + 1

                        cursor.execute("""
                            INSERT INTO releases (
                                pipeline_id, run_id, release_number, environment_id, 
                                deployed_by, deploy_command_id, status, started_at, finished_at
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            run_info['pipeline_id'],
                            run_id,
                            release_number,
                            run_info['environment_id'],
                            run_info['started_by'],
                            deploy_command_id,
                            'success',
                            datetime.now(),
                            datetime.now()
                        ))
                        conn.commit()
                        flask_app.logger.info(f"✅ Release #{release_number} criado automaticamente pelo schedule para run {run_id}")

            # Broadcast do evento
            cursor.execute("SELECT name FROM pipelines WHERE id = %s", (pipeline_id,))
            pipeline = cursor.fetchone()
            if pipeline:
                event_manager.broadcast({
                    "type": "PIPELINE_FINISH",
                    "pipeline_name": pipeline["name"],
                    "status": "success",
                    "timestamp": datetime.now()
                })
                dispatch_webhook_event("PIPELINE_FINISH", {
                    "pipeline_name": pipeline["name"],
                    "status": "success",
                    "run_id": run_id,
                })

                # Enviar Notificações
                try:
                    cursor.execute("SELECT started_at, finished_at FROM pipeline_runs WHERE id = %s", (run_id,))
                    run_details = dict(cursor.fetchone() or {})
                    
                    time.sleep(1) # Aguarda salvar background flush de logs
                    cursor.execute("SELECT output FROM pipeline_run_output_logs WHERE run_id = %s ORDER BY id", (run_id,))
                    log_rows = cursor.fetchall()
                    log_text = "\n".join([str(row['output']) for row in log_rows if row.get('output')])
                    
                    send_pipeline_notification(pipeline["name"], "success", run_details, notify_emails, notify_whatsapp, log_text=log_text)
                except Exception as notif_err:
                    flask_app.logger.warning(f"Falha ao enviar notificação: {notif_err}")
            
        except Exception as e:
            # Pipeline falhou
            cursor.execute("""
                UPDATE pipeline_runs 
                SET status = 'failed', finished_at = %s, error_message = %s
                WHERE id = %s
            """, (datetime.now(), str(e), run_id))
            conn.commit()
            flask_app.logger.error(f"Pipeline run {run_id} falhou: {e}")
            
            # Atualizar status do stream quando falhar
            set_live_stream_status(run_id, 'failed')

            # Broadcast do evento de falha
            cursor.execute("SELECT name FROM pipelines WHERE id = %s", (pipeline_id,))
            pipeline = cursor.fetchone()
            if pipeline:
                event_manager.broadcast({
                    "type": "PIPELINE_FINISH",
                    "pipeline_name": pipeline["name"],
                    "status": "failed",
                    "timestamp": datetime.now()
                })
                dispatch_webhook_event("PIPELINE_FINISH", {
                    "pipeline_name": pipeline["name"],
                    "status": "failed",
                    "run_id": run_id,
                })

                # Enviar Notificações
                try:
                    cursor.execute("SELECT started_at, finished_at FROM pipeline_runs WHERE id = %s", (run_id,))
                    run_details = dict(cursor.fetchone() or {})
                    
                    time.sleep(1) # Aguarda salvar background flush de logs
                    cursor.execute("SELECT output FROM pipeline_run_output_logs WHERE run_id = %s ORDER BY id", (run_id,))
                    log_rows = cursor.fetchall()
                    log_text = "\n".join([str(row['output']) for row in log_rows if row.get('output')])
                    
                    send_pipeline_notification(pipeline["name"], "failed", run_details, notify_emails, notify_whatsapp, log_text=log_text)
                except Exception as notif_err:
                    flask_app.logger.warning(f"Falha ao enviar notificação: {notif_err}")
            
        finally:
            if environment_id:
                release_env_lock(environment_id)
                flask_app.logger.info(f"🔓 Lock do ambiente {environment_id} liberado (build run_id={run_id})")
            release_db_connection(conn)


# =====================================================================
# EXECUÇÃO DE RELEASE (CD/Deploy) - Portado do app.py original
# =====================================================================

def execute_release(flask_app, release_id, run_id, command, environment_id=None):
    """
    Executa o deploy de um release em background.
    Associado a um RUN específico.
    """
    with flask_app.app_context():
        conn = get_db()
        cursor = conn.cursor()
        
        env_vars, protected_vars, _, _ = _load_and_mask_variables(cursor)
        
        def log_release(message, level="info"):
            """Registra log do release no banco"""
            cursor.execute("""
                INSERT INTO release_logs (release_id, output, log_type, created_at)
                VALUES (%s, %s, %s, %s)
            """, (release_id, message, level, datetime.now()))
            conn.commit()
            flask_app.logger.info(f"[Release {release_id}] {message}")
        
        try:
            # Buscar informações do run
            cursor.execute("SELECT * FROM pipeline_runs WHERE id = %s", (run_id,))
            run = cursor.fetchone()
            
            if not run:
                raise Exception(f"Run {run_id} não encontrado")
            
            run_dict = dict(run)
            
            log_release(f"🚀 Iniciando deploy do build #{run_dict['run_number']}", "info")
            log_release(f"📋 Comando: {command['name']}", "info")
            log_release(f"⚙️  Executando deploy...", "info")
            
            # Variáveis de ambiente já foram carregadas no início da função
            
            cmd_text = command['script']
            cmd_type = command.get('type', 'bash')
            
            # Para PowerShell: substitui TODAS as variáveis ${NOME} pelos valores
            if cmd_type == "powershell":
                variables_found = re.findall(r'\$\{([A-Z_0-9]+)\}', cmd_text)
                for var_name in variables_found:
                    if var_name in env_vars:
                        old_pattern = f"${{{var_name}}}"
                        new_value = _sanitize_var_for_shell(env_vars[var_name], 'powershell')
                        cmd_text = cmd_text.replace(old_pattern, new_value)

                if platform.system() == "Windows":
                    exec_command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd_text]
                else:
                    exec_command = ["pwsh", "-NoProfile", "-Command", cmd_text]
                use_shell = False

            elif cmd_type == "bash":
                exec_command = cmd_text
                use_shell = True

            else:
                exec_command = cmd_text
                use_shell = True

            # Executar comando de deploy
            result = subprocess.run(
                exec_command,
                shell=use_shell,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=600,  # 10 minutos
                env=env_vars
            )
            
            # Registrar saída
            if result.stdout:
                log_release(f"📤 Output:\n{result.stdout}", "info")
            
            if result.stderr:
                log_release(f"⚠️  Stderr:\n{result.stderr}", "warning")
            
            # Determinar status
            status = "success"
            error_msg = None
            
            if result.returncode == 0:
                log_release(f"✅ Deploy concluído com sucesso!", "success")
            else:
                log_release(f"❌ Deploy falhou com código {result.returncode}", "error")
                status = "failed"
                error_msg = result.stderr or "Erro desconhecido"
            
            # Atualizar status do release
            cursor.execute("""
                UPDATE releases 
                SET status = %s, finished_at = %s, error_message = %s
                WHERE id = %s
            """, (status, datetime.now(), error_msg, release_id))
            conn.commit()
            
            # Adicionar saída completa do deploy nos logs do run
            try:
                cursor.execute("""
                    SELECT MAX(command_order) as max_order 
                    FROM pipeline_run_logs 
                    WHERE run_id = %s
                """, (run_id,))
                last_order = cursor.fetchone()
                next_order = (last_order['max_order'] or 0) + 1 if last_order else 1

                deploy_output = ""
                if result.stdout:
                    deploy_output += result.stdout
                if result.stderr and status == 'success':
                    deploy_output += f"\n\n{'='*60}\n⚠️ AVISOS:\n{'='*60}\n{result.stderr}"
                if not deploy_output.strip():
                    deploy_output = f"🚀 Deploy executado!\nRelease #{release_id}\nComando: {command['name']}"

                cursor.execute("""
                    INSERT INTO pipeline_run_logs (
                        run_id, command_id, command_order, status, output, 
                        started_at, finished_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    run_id,
                    command['id'],
                    next_order,
                    'success' if status == 'success' else 'failed',
                    deploy_output,
                    datetime.now(),
                    datetime.now()
                ))
                conn.commit()
            except Exception as log_error:
                flask_app.logger.warning(f"⚠️ Não foi possível adicionar log do release aos logs do run: {log_error}")

        except subprocess.TimeoutExpired:
            log_release("⏱️ Deploy excedeu o tempo limite", "error")
            cursor.execute("""
                UPDATE releases 
                SET status = 'failed', finished_at = %s, error_message = %s
                WHERE id = %s
            """, (datetime.now(), "Timeout", release_id))
            conn.commit()
            
        except Exception as e:
            log_release(f"💥 Erro durante deploy: {str(e)}", "error")
            cursor.execute("""
                UPDATE releases 
                SET status = 'failed', finished_at = %s, error_message = %s
                WHERE id = %s
            """, (datetime.now(), str(e), release_id))
            conn.commit()
            flask_app.logger.error(f"Release {release_id} falhou: {e}")

        finally:
            if environment_id:
                release_env_lock(environment_id)
                flask_app.logger.info(f"🔓 Lock do ambiente {environment_id} liberado (release_id={release_id})")
            release_db_connection(conn)


# =====================================================================
# EXECUÇÃO DE PIPELINE LEGADA (execute_pipeline_thread)
def execute_service_action_logic(app, action_id, env_id, user_id, notify_emails=None, notify_whatsapp=None):
    """Executa a lógica core de uma ação de serviço, para ser usada por rotas e pelo scheduler."""
    import os
    import json
    import platform
    import subprocess
    import traceback
    
    from app.database import get_db, release_db_connection
    from app.utils.helpers import now_br

    with app.app_context():
        conn = get_db()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "SELECT * FROM service_actions WHERE id = %s AND environment_id = %s",
                (action_id, env_id)
            )
            action = cursor.fetchone()
            
            if not action:
                return {"success": False, "error": "Ação não encontrada", "status_code": 404}
            
            # Use database notification fields as fallback 
            notify_emails = notify_emails or action.get('notify_emails')
            notify_whatsapp = notify_whatsapp or action.get('notify_whatsapp')
            
            # Buscar nome do ambiente para mapear sufixo
            cursor.execute(
                "SELECT name FROM environments WHERE id = %s",
                (action['environment_id'],)
            )
            env = cursor.fetchone()
            
            suffix_map = {
                'Produção': 'PRD',
                'Homologação': 'HOM',
                'Desenvolvimento': 'DEV',
                'Testes': 'TST'
            }
            suffix = suffix_map.get(env['name'], 'PRD') if env else 'PRD'
            
            # Parse service IDs
            service_ids = action['service_ids'].split(',')
            
            # Get service names and server_name
            cursor.execute(
                f"SELECT id, name, server_name FROM server_services WHERE id IN ({','.join(['%s'] * len(service_ids))})",
                service_ids
            )
            services_unordered = cursor.fetchall()
            
            # IMPORTANTE: Ordenar serviços na ordem original dos IDs
            services_dict = {str(s['id']): dict(s) for s in services_unordered}
            services = [services_dict[sid] for sid in service_ids if sid in services_dict]
            
            # Carregar variáveis de ambiente do banco
            env_vars, protected_vars, _, _ = _load_and_mask_variables(cursor)
            
            results = []
            for service in services:
                service_name = service['name']
                server_name = service.get('server_name', 'localhost')
                
                # Substituir variáveis ${VAR} no server_name
                import re
                variables_found = re.findall(r'\$\{([A-Z_0-9]+)\}', server_name)
                for var_name in variables_found:
                    if var_name in env_vars:
                        server_name = server_name.replace(f"${{{var_name}}}", env_vars[var_name])
                
                # Sanitizar nome do serviço para prevenir injeção de comando
                import re as _re
                if not _re.match(r'^[a-zA-Z0-9._@:/-]+$', service_name):
                    results.append({
                        "service": service_name, "success": False,
                        "output": f"Nome de serviço inválido: {service_name}"
                    })
                    continue

                # Build command based on OS and action type
                if action['os_type'] == 'linux':
                    if action['action_type'] == 'start':
                        command = ["systemctl", "start", service_name]
                    elif action['action_type'] == 'stop':
                        command = ["systemctl", "stop", service_name]
                    elif action['action_type'] == 'restart':
                        command = ["systemctl", "restart", service_name]

                    try:
                        result = subprocess.run(
                            command, shell=False, capture_output=True, text=True,
                            encoding='utf-8', errors='replace',
                            timeout=60, env=env_vars
                        )
                        results.append({
                            "service": service_name,
                            "success": result.returncode == 0,
                            "output": result.stdout + result.stderr
                        })
                    except Exception as e:
                        results.append({
                            "service": service_name, "success": False, "output": str(e)
                        })
                        
                else:  # windows
                    force_flag = "-Force" if action.get('force_stop', False) else ""

                    # Escapa aspas simples no nome do serviço para PowerShell
                    safe_service_name = _sanitize_var_for_shell(service_name, 'powershell')
                    svc_filter = f"Get-Service | Where-Object {{$_.Name -eq '{safe_service_name}'}}"
                    if action['action_type'] == 'start':
                        ps_script = f"{svc_filter} | Start-Service"
                    elif action['action_type'] == 'stop':
                        ps_script = f"{svc_filter} | Stop-Service {force_flag}"
                    elif action['action_type'] == 'restart':
                        ps_script = f"{svc_filter} | Restart-Service {force_flag}"
                    
                    is_linux_server = platform.system() == 'Linux'
                    
                    try:
                        app.logger.info(f"Checking server type: {is_linux_server}, Server name: {server_name}")
                        
                        if is_linux_server:
                            ssh_host = env_vars.get(f'SSH_HOST_WINDOWS_{suffix}', server_name)
                            ssh_user = env_vars.get(f'SSH_USER_WINDOWS_{suffix}', 'administrador')
                            ssh_port = env_vars.get(f'SSH_PORT_WINDOWS_{suffix}', '22')

                            # Sanitiza parâmetros SSH para prevenir injeção de comando
                            ssh_host = shlex.quote(ssh_host)
                            ssh_user = shlex.quote(ssh_user)
                            ssh_port = shlex.quote(ssh_port)
                            ps_script_escaped = ps_script.replace('"', '\\"')

                            ssh_command = f"ssh -i ~/.ssh/id_rsa_aturpo -p {ssh_port} -o StrictHostKeyChecking=no -o ConnectTimeout=10 {ssh_user}@{ssh_host} \"powershell -Command {ps_script_escaped}\""

                            app.logger.info(f"🔧 SSH Command: {ssh_command}")

                            result = subprocess.run(
                                ssh_command, shell=True, capture_output=True, text=True,
                                timeout=60, env=env_vars, encoding='cp850', errors='replace'
                            )
                            
                            ssh_success = result.returncode == 0 or (result.returncode == 1 and not result.stderr)
                            
                            results.append({
                                "service": service_name, "server": ssh_host, "method": "SSH",
                                "success": ssh_success,
                                "output": result.stdout + result.stderr if (result.stdout or result.stderr) else "Comando executado com sucesso"
                            })
                        else:
                            is_local = server_name.lower() in ['localhost', '127.0.0.1', '.', ''] or server_name.lower() == os.environ.get('COMPUTERNAME', '').lower()
                            
                            if not is_local:
                                remote_filter = f"Get-Service | Where-Object {{$_.Name -eq '{service_name}'}}"
                                if action['action_type'] == 'start':
                                    ps_script = f"Invoke-Command -ComputerName '{server_name}' -ScriptBlock {{ {remote_filter} | Start-Service }}"
                                elif action['action_type'] == 'stop':
                                    ps_script = f"Invoke-Command -ComputerName '{server_name}' -ScriptBlock {{ {remote_filter} | Stop-Service {force_flag} }}"
                                elif action['action_type'] == 'restart':
                                    ps_script = f"Invoke-Command -ComputerName '{server_name}' -ScriptBlock {{ {remote_filter} | Restart-Service {force_flag} }}"
                            
                            exec_command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script]
                            
                            result = subprocess.run(
                                exec_command, shell=False, capture_output=True, text=True,
                                encoding='cp850', errors='replace', timeout=60, env=env_vars
                            )
                            results.append({
                                "service": service_name, "server": server_name, "method": "PowerShell",
                                "is_local": is_local, "success": result.returncode == 0,
                                "output": result.stdout + result.stderr
                            })
                    except Exception as e:
                        results.append({
                            "service": service_name, "server": server_name,
                            "success": False, "output": str(e)
                        })
            
            # Gravar log de execução no banco
            try:
                all_success = all(r.get('success') for r in results)
                any_success = any(r.get('success') for r in results)
                overall_status = 'success' if all_success else ('partial' if any_success else 'failed')
                
                cursor.execute(
                    """INSERT INTO service_action_logs 
                       (action_id, environment_id, status, results, executed_by, executed_at)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (action_id, env_id, overall_status, json.dumps(results), user_id, now_br())
                )
                conn.commit()
            except Exception as log_err:
                app.logger.warning(f"Erro ao gravar log de execução da service action: {log_err}")

            # Enviar Notificação
            try:
                from app.services.notifier import send_service_action_notification
                details_json = json.dumps(results, indent=2, ensure_ascii=False)
                send_service_action_notification(action['name'], "success", details_json, notify_emails, notify_whatsapp)
            except Exception as notif_err:
                app.logger.warning(f"Falha ao enviar notificação SA: {notif_err}")

            return {
                "success": True,
                "results": results,
                "message": f"Ação '{action['name']}' executada",
                "status_code": 200
            }
            
        except Exception as e:
            traceback.print_exc()
            error_details = str(e) + "\n" + traceback.format_exc()
            try:
                from app.services.notifier import send_service_action_notification
                a_name = action.get('name', f"Ação #{action_id}") if 'action' in locals() and action else f"Ação #{action_id}"
                send_service_action_notification(a_name, "failed", error_details, notify_emails, notify_whatsapp)
            except Exception as notif_err:
                pass
            return {"success": False, "error": error_details, "status_code": 500}
        finally:
            release_db_connection(conn)


# Mantida para compatibilidade com schedules que usam a versão antiga

# =====================================================================

def execute_pipeline_thread(flask_app, pipeline_id, user_name, trigger_type='manual', schedule_id=None, run_id=None):
    """Função legada que roda em background para executar os comandos da pipeline."""
    with flask_app.app_context():
        start_time = datetime.now()
        trigger_info = f"{trigger_type}"
        if schedule_id:
            trigger_info += f" (schedule #{schedule_id})"

        conn = get_db()
        cursor = conn.cursor()

        try:
            BASE_DIR = get_base_dir_for_pipeline(cursor, pipeline_id)

            cursor.execute(
                "SELECT c.* FROM commands c JOIN pipeline_commands pc ON c.id = pc.command_id WHERE pc.pipeline_id = %s ORDER BY pc.sequence_order",
                (pipeline_id,),
            )
            commands_to_run = [dict(row) for row in cursor.fetchall()]

            cursor.execute(
                "UPDATE pipelines SET status = 'running' WHERE id = %s", (pipeline_id,)
            )
            conn.commit()

            pipeline_success = True

            # Buscar TODAS as variáveis do servidor para substituição nos scripts
            env_vars, protected_vars, _, _ = _load_and_mask_variables(cursor)
            server_vars = {k: v or '' for k, v in env_vars.items()}

            # Repositório é OPCIONAL - tenta usar como diretório de trabalho se existir
            cursor.execute(
                "SELECT name, default_branch FROM repositories ORDER BY id LIMIT 1"
            )
            repo = cursor.fetchone()

            working_dir = None
            if repo:
                branch_name = repo["default_branch"]
                repo_dir = os.path.join(BASE_DIR, repo["name"], branch_name)
                if os.path.exists(repo_dir):
                    working_dir = repo_dir
            
            if pipeline_success:
                for command in commands_to_run:
                    cursor.execute(
                        "INSERT INTO execution_logs (pipeline_id, command_id, status, started_at, executed_by) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                        (pipeline_id, command["id"], "running", datetime.now(), user_name),
                    )
                    log_id = cursor.fetchone()['id']
                    conn.commit()

                    # Substitui ${BASE_DIR} e TODAS as variáveis do ambiente no script
                    script_to_run = command["script"].replace("${BASE_DIR}", BASE_DIR)
                    for var_name, var_value in server_vars.items():
                        script_to_run = script_to_run.replace(f"${{{var_name}}}", var_value)

                    if command["type"] == "powershell" and working_dir:
                        script_to_run = f"""
                    Push-Location '{working_dir}'
                    try {{
                        {script_to_run}
                    }} catch {{
                        Write-Error "Erro na execução: $_"
                        throw
                    }} finally {{
                        Pop-Location
                    }}
                    """

                    shell_command = []
                    use_cwd = False
                    encoding = 'utf-8'

                    if command["type"] == "bash":
                        shell_command = ["/bin/bash", "-c", script_to_run]
                        use_cwd = True
                    elif command["type"] == "powershell":
                        if platform.system() == "Windows":
                            shell_command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script_to_run]
                            encoding = 'cp850'
                        else:
                            shell_command = ["pwsh", "-NoProfile", "-Command", script_to_run]
                        use_cwd = False
                    elif command["type"] in ("batch", "cmd"):
                        if platform.system() == "Windows":
                            shell_command = ["cmd.exe", "/c", script_to_run]
                            encoding = 'cp850'
                            use_cwd = False
                        else:
                            cursor.execute(
                                "UPDATE execution_logs SET status = 'failed', error = %s WHERE id = %s",
                                ("Scripts batch/cmd só são suportados no Windows.", log_id),
                            )
                            conn.commit()
                            pipeline_success = False
                            break
                    else:
                        cursor.execute(
                            "UPDATE execution_logs SET status = 'failed', error = %s WHERE id = %s",
                            (f"Tipo de script '{command['type']}' não é suportado.", log_id),
                        )
                        conn.commit()
                        pipeline_success = False
                        break
                    
                    try:
                        process = subprocess.Popen(
                            shell_command,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            cwd=working_dir if use_cwd else None,
                            bufsize=1,
                            universal_newlines=True,
                            encoding=encoding,
                            errors='replace'
                        )
                        output = ""
                        for line in process.stdout:
                            output += line
                            cursor.execute(
                                "UPDATE execution_logs SET output = %s WHERE id = %s",
                                (output, log_id),
                            )
                            conn.commit()

                        process.wait()

                        if process.returncode != 0:
                            raise subprocess.CalledProcessError(
                                process.returncode, shell_command, output=output
                            )

                        cursor.execute(
                            "UPDATE execution_logs SET status = 'success', finished_at = %s WHERE id = %s",
                            (datetime.now(), log_id),
                        )
                        conn.commit()

                    except subprocess.CalledProcessError as e:
                        error_output = f"{output}\n\nERRO (Código de Saída: {e.returncode})"
                        cursor.execute(
                            "UPDATE execution_logs SET status = 'failed', error = %s, finished_at = %s WHERE id = %s",
                            (error_output, datetime.now(), log_id),
                        )
                        conn.commit()
                        pipeline_success = False
                        break

            end_time = datetime.now()
            duration = str(end_time - start_time).split(".")[0]
            final_status = "success" if pipeline_success else "failed"

            cursor.execute("SELECT name FROM pipelines WHERE id = %s", (pipeline_id,))
            pipeline = cursor.fetchone()
            if pipeline:
                event_manager.broadcast({
                    "type": "PIPELINE_FINISH",
                    "user": user_name,
                    "pipeline_name": pipeline["name"],
                    "status": final_status,
                    "duration": duration,
                    "timestamp": datetime.now()
                })
                dispatch_webhook_event("PIPELINE_FINISH", {
                    "pipeline_name": pipeline["name"],
                    "status": final_status,
                    "user": user_name,
                    "duration": duration,
                })

            cursor.execute(
                "UPDATE pipelines SET status = %s, duration = %s WHERE id = %s",
                (final_status, duration, pipeline_id),
            )

            # Atualizar pipeline_runs se run_id fornecido
            if run_id:
                error_msg = None
                if not pipeline_success:
                    cursor.execute(
                        "SELECT error FROM execution_logs WHERE pipeline_id = %s AND status = 'failed' ORDER BY id DESC LIMIT 1",
                        (pipeline_id,)
                    )
                    err_row = cursor.fetchone()
                    if err_row:
                        error_msg = str(err_row['error'])[:500] if err_row['error'] else None

                cursor.execute(
                    "UPDATE pipeline_runs SET status = %s, finished_at = %s, error_message = %s WHERE id = %s",
                    (final_status, end_time, error_msg, run_id)
                )

            conn.commit()

        finally:
            if conn:
                release_db_connection(conn)

