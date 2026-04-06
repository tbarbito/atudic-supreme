import threading
import time
import traceback
import json
import calendar
from datetime import datetime, timedelta

from app.database import get_db, release_db_connection
from app.utils.helpers import now_br
from app.services.runner import execute_pipeline_thread


def calculate_next_run(schedule):
    """Calcula a data da próxima execução (Função pura/standalone)"""
    try:
        schedule_type = schedule['schedule_type']
        config = schedule['schedule_config']
        
        if isinstance(config, str):
            config = json.loads(config)
            
        now = datetime.now()
        
        # Helper extraction para retrocompatibilidade
        def get_time():
            if 'time' in config:
                return datetime.strptime(config['time'], "%H:%M").time()
            hour = int(config.get('hour', 0))
            minute = int(config.get('minute', 0))
            return datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").time()
            
        if schedule_type == 'once':
            return None
            
        elif schedule_type == 'daily':
            target_time = get_time()
            next_run = datetime.combine(now.date(), target_time)
            if next_run <= now:
                next_run += timedelta(days=1)
            return next_run
            
        elif schedule_type == 'weekly':
            target_time = get_time()
            # Retrocompatibilidade com db legacy: weekdays vs days
            target_days = config.get('days', config.get('weekdays', []))
            target_days = [int(d) for d in target_days]
            
            # Começa tentando hoje
            candidate = datetime.combine(now.date(), target_time)
            
            # Procura o próximo dia válido
            for _ in range(8): # Loop seguro
                if candidate.weekday() in target_days and candidate > now:
                    return candidate
                candidate += timedelta(days=1)
            return None
        
        elif schedule_type == 'monthly':
            target_day = int(config.get('day', 1))
            target_time = get_time()
            
            # Tenta este mês
            try:
                candidate = datetime.combine(now.date().replace(day=target_day), target_time)
            except ValueError:
                candidate = now # Força a ir pro próximo loop
            
            if candidate <= now:
                # Mês seguinte
                next_month_date = now.date().replace(day=1) + timedelta(days=32)
                next_month_date = next_month_date.replace(day=1) # 1o dia do prox mes
                
                try:
                    candidate = datetime.combine(next_month_date.replace(day=target_day), target_time)
                except ValueError:
                     return None
            return candidate
        
        elif schedule_type == 'crotab':
            # TODO: Implementar parser de cron se necessário
            return None
            
    except Exception as e:
        print(f"erro ao calcular next run: {e}")
        traceback.print_exc()
        return None


class PipelineScheduler:
    """Worker que monitora e executa pipelines e ações de serviço agendadas"""
    
    def __init__(self, flask_app):
        self.flask_app = flask_app
        self.running = False
        self.thread = None
        
    def start(self):
        """Inicia o worker em background"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.thread.start()
        print("✅ Scheduler worker iniciado!")
        
    def stop(self):
        """Para o worker"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        print("🛑 Scheduler worker parado!")
    
    def _scheduler_loop(self):
        """Loop principal do scheduler"""
        self._maintenance_counter = 0
        with self.flask_app.app_context():
            while self.running:
                try:
                    self._check_and_execute_schedules()
                    self._check_and_execute_service_actions()

                    # Tarefas de manutenção periódica
                    self._maintenance_counter += 1

                    # A cada ~15 min (30 iterações de 30s): refresh alert_trends
                    if self._maintenance_counter % 30 == 0:
                        self._refresh_alert_trends()

                    # A cada ~24h (2880 iterações de 30s): cleanup de dados antigos
                    if self._maintenance_counter % 2880 == 0:
                        self._cleanup_old_data()
                        self._maintenance_counter = 0
                except Exception as e:
                    print(f"❌ Erro no scheduler loop: {e}")
                    traceback.print_exc()

                # Aguarda 30 segundos antes da próxima verificação
                time.sleep(30)
    
    def _check_and_execute_schedules(self):
        """Verifica schedules ativos e executa se necessário"""
        conn = get_db()
        cursor = conn.cursor()
        
        now = datetime.now()
        
        # Busca schedules ativos que devem ser executados
        cursor.execute("""
            SELECT s.*, p.name as pipeline_name, u.username
            FROM pipeline_schedules s
            JOIN pipelines p ON s.pipeline_id = p.id
            JOIN users u ON s.created_by = u.id
            WHERE s.is_active = TRUE
            AND (s.next_run_at IS NULL OR s.next_run_at <= %s)
        """, (now,))
        schedules = cursor.fetchall()
        
        if len(schedules) > 0:
            print(f"⏰ Monitor do Scheduler encontrou {len(schedules)} pipeline(s) para executar agora ({now.strftime('%H:%M:%S')})")
        
        for schedule in schedules:
            try:
                schedule_dict = dict(schedule)
                self._execute_scheduled_pipeline(cursor, schedule_dict, now)
            except Exception as e:
                print(f"❌ Erro ao executar schedule {schedule['id']}: {e}")
                traceback.print_exc()
        
        conn.commit()
        release_db_connection(conn)
    
    def _execute_scheduled_pipeline(self, cursor, schedule, now):
        """Executa uma pipeline agendada"""
        from app.services.runner import execute_pipeline_run
        
        schedule_id = schedule['id']
        pipeline_id = schedule['pipeline_id']
        created_by = schedule['created_by']
        username = schedule['username']

        print(f"⏰ Executando schedule #{schedule_id}: {schedule['name']} (Pipeline: {schedule['pipeline_name']})")

        # Buscar comandos BUILD da pipeline
        cursor.execute("""
            SELECT c.* FROM commands c
            JOIN pipeline_commands pc ON c.id = pc.command_id
            WHERE pc.pipeline_id = %s
            ORDER BY pc.sequence_order
        """, (pipeline_id,))
        build_commands = [dict(row) for row in cursor.fetchall()]

        if not build_commands:
            print(f"❌ Schedule #{schedule_id}: Pipeline sem comandos configurados")
            return

        # Buscar comando DEPLOY da pipeline (se existir)
        cursor.execute(
            "SELECT deploy_command_id FROM pipelines WHERE id = %s",
            (pipeline_id,)
        )
        pipeline_info = cursor.fetchone()
        deploy_command_id = pipeline_info['deploy_command_id'] if pipeline_info else None

        deploy_command = None
        if deploy_command_id:
            cursor.execute(
                "SELECT * FROM commands WHERE id = %s AND command_category = 'deploy'",
                (deploy_command_id,)
            )
            deploy_command = cursor.fetchone()
            if deploy_command:
                deploy_command = dict(deploy_command)

        # Combinar comandos: BUILD + DEPLOY (se existir)
        all_commands = build_commands.copy()
        if deploy_command:
            all_commands.append(deploy_command)
            print(f"📦 Schedule incluirá {len(build_commands)} comandos BUILD + 1 comando DEPLOY")
        else:
            print(f"📦 Schedule incluirá {len(build_commands)} comandos BUILD (sem deploy)")

        # Buscar environment_id da pipeline
        cursor.execute(
            "SELECT environment_id FROM pipelines WHERE id = %s",
            (pipeline_id,)
        )
        env_row = cursor.fetchone()
        environment_id = env_row['environment_id'] if env_row else None

        # Obter próximo run_number
        cursor.execute(
            "SELECT MAX(run_number) as last FROM pipeline_runs WHERE pipeline_id = %s",
            (pipeline_id,)
        )
        last_run = cursor.fetchone()
        run_number = (dict(last_run)["last"] or 0) + 1

        # Criar novo pipeline_run
        cursor.execute("""
            INSERT INTO pipeline_runs 
            (pipeline_id, run_number, status, started_at, started_by, environment_id, trigger_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
        """, (pipeline_id, run_number, 'running', now, 
              created_by, environment_id, 'scheduled'))

        run_id = cursor.fetchone()['id']
        cursor.connection.commit()

        # Verificar lock de ambiente — acesso exclusivo ao RPO
        if environment_id:
            from app.services.runner import acquire_env_lock, get_env_running_info
            running = get_env_running_info(environment_id)
            if running:
                # Ambiente ocupado — cancelar run e marcar como failed
                cursor.execute("""
                    UPDATE pipeline_runs
                    SET status = 'failed', finished_at = %s,
                        error_message = %s
                    WHERE id = %s
                """, (
                    now,
                    f"Ambiente ocupado: {running['type']} do pipeline '{running['pipeline']}' "
                    f"(iniciado em {running['started_at'].strftime('%H:%M:%S')})",
                    run_id
                ))
                cursor.connection.commit()
                print(f"⚠️ Schedule #{schedule_id}: Ambiente ocupado, execução adiada (run_id={run_id})")
                return

            if not acquire_env_lock(environment_id, "build", run_id, schedule.get('pipeline_name', '')):
                print(f"⚠️ Schedule #{schedule_id}: Não foi possível adquirir lock do ambiente")
                return

        # Inicia execução da pipeline em background com TODOS os comandos
        t = threading.Thread(
            target=execute_pipeline_run,
            args=(self.flask_app, run_id, pipeline_id, all_commands, schedule.get('notify_emails'), schedule.get('notify_whatsapp')),
            kwargs={"environment_id": environment_id},
            daemon=True
        )
        t.start()

        print(f"✅ Schedule #{schedule_id}: Pipeline run #{run_number} iniciado (run_id: {run_id})")
        
        # Calcular e atualizar próxima execução usando a função standalone
        next_run = calculate_next_run(schedule)
        
        if next_run:
            cursor.execute(
                "UPDATE pipeline_schedules SET next_run_at = %s, last_run_at = %s WHERE id = %s",
                (next_run, now, schedule_id)
            )
        else:
            # Se não tem próxima execução (ex: once), desativa
            cursor.execute(
                "UPDATE pipeline_schedules SET is_active = FALSE, next_run_at = NULL, last_run_at = %s WHERE id = %s",
                (now, schedule_id)
            )

    def _refresh_alert_trends(self):
        """Atualiza a view materializada alert_trends (economia de tokens)."""
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY alert_trends")
            conn.commit()
        except Exception:
            # View pode nao existir (migration pendente) — silenciar
            conn.rollback()
        finally:
            release_db_connection(conn)

    def _cleanup_old_data(self):
        """Remove dados antigos para manter o banco enxuto.

        Executado a cada ~24h pelo scheduler loop.
        - chat_messages: arquiva mensagens > 90 dias
        - agent_audit_log: remove registros > 180 dias
        - search_log (SQLite): tratado separadamente pelo agent_memory
        """
        conn = get_db()
        cursor = conn.cursor()
        try:
            # Chat messages — manter últimos 90 dias
            cursor.execute("""
                DELETE FROM chat_messages
                WHERE created_at < NOW() - INTERVAL '90 days'
            """)
            chat_deleted = cursor.rowcount

            # Audit log — manter últimos 180 dias
            cursor.execute("""
                DELETE FROM agent_audit_log
                WHERE created_at < NOW() - INTERVAL '180 days'
            """)
            audit_deleted = cursor.rowcount

            # Alertas reconhecidos antigos — manter últimos 30 dias
            cursor.execute("""
                DELETE FROM log_alerts
                WHERE acknowledged = TRUE
                AND occurred_at < NOW() - INTERVAL '30 days'
            """)
            alerts_deleted = cursor.rowcount

            # Permission overrides expirados — limpar para manter banco enxuto
            overrides_deleted = 0
            try:
                cursor.execute("""
                    DELETE FROM user_permission_overrides
                    WHERE expires_at IS NOT NULL AND expires_at < NOW()
                """)
                overrides_deleted = cursor.rowcount
            except Exception:
                pass  # Tabela pode nao existir se migration 022 nao rodou

            conn.commit()

            total = chat_deleted + audit_deleted + alerts_deleted + overrides_deleted
            if total > 0:
                print(f"🧹 Cleanup: {chat_deleted} chat msgs, {audit_deleted} audit logs, {alerts_deleted} alertas, {overrides_deleted} overrides expirados removidos")
        except Exception as e:
            conn.rollback()
            print(f"⚠️ Cleanup falhou (tabelas podem nao existir): {e}")
        finally:
            release_db_connection(conn)

    def _check_and_execute_service_actions(self):
        """Verifica service actions agendadas e executa se necessário"""
        conn = get_db()
        cursor = conn.cursor()

        now = datetime.now()
        
        # Busca service actions ativas com agendamento
        cursor.execute("""
            SELECT sa.*, u.username
            FROM service_actions sa
            JOIN users u ON sa.created_by = u.id
            WHERE sa.is_active = TRUE
            AND sa.schedule_type IS NOT NULL
            AND (sa.next_run_at IS NULL OR sa.next_run_at <= %s)
        """, (now,))
        actions = cursor.fetchall()
        
        if len(actions) > 0:
            print(f"⏰ Monitor do Scheduler encontrou {len(actions)} service action(s) para executar agora ({now.strftime('%H:%M:%S')})")
        
        for action in actions:
            try:
                action_dict = dict(action)
                self._execute_scheduled_service_action(cursor, action_dict, now)
            except Exception as e:
                print(f"❌ Erro ao executar service action {action['id']}: {e}")
                traceback.print_exc()
        
        conn.commit()
        release_db_connection(conn)

    def _execute_scheduled_service_action(self, cursor, action, now):
        """Executa uma ação de serviço agendada"""
        from app.services.runner import execute_service_action_logic
        import threading
        
        action_id = action['id']
        action_name = action['name']
        print(f"⚙️ Iniciando execução da service action #{action_id}: {action_name}")
        
        # Executar em thread separada para não bloquear o loop do scheduler
        env_id = action['environment_id']
        user_id = action['created_by']
        
        t = threading.Thread(
            target=execute_service_action_logic,
            args=(self.flask_app, action_id, env_id, user_id, action.get('notify_emails'), action.get('notify_whatsapp')),
            daemon=True
        )
        t.start()
        
        # Calcular próxima execução
        next_run = calculate_next_run(action)
        
        if next_run:
            cursor.execute(
                "UPDATE service_actions SET next_run_at = %s, last_run_at = %s WHERE id = %s",
                (next_run, now, action_id)
            )
        else:
             cursor.execute(
                "UPDATE service_actions SET is_active = FALSE, next_run_at = NULL, last_run_at = %s WHERE id = %s",
                (now, action_id)
            )
