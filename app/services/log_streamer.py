"""
Log streaming service.

This module handles real-time log streaming for pipeline execution and
background log persistence.
"""
import threading
import time
from collections import deque
from threading import Lock
from datetime import datetime
from app.database import get_db, release_db_connection

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
        # Precisa do app_context se usar current_app, mas aqui usamos get_db direto.
        # Porém, Flask pode exigir context para outras coisas. Pelo original, usava flask_app.app_context().
        # Se get_db não depende de flask.g (no nosso refactor não depende), pode não precisar.
        # Mas vamos manter o context por segurança se houver logs de erro usando app.logger.
        
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
