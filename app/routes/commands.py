from flask import Blueprint, request, jsonify
from psycopg2 import IntegrityError, Error as PsycopgError
from datetime import datetime

from app.database import get_db, release_db_connection
from app.utils.security import (
    require_auth,
    require_admin,
    check_protected_item
)

commands_bp = Blueprint('commands', __name__)

@commands_bp.route("/api/commands", methods=["GET"])
@require_auth
def get_commands():
    """Lista comandos com filtros seguros"""
    
    # Pega parâmetros de query string
    category = request.args.get('category')  # Tipo de script (bash, powershell, etc)
    command_category = request.args.get('command_category')  # 🆕 Build ou Deploy
    search = request.args.get('search')
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Header base do SQL com ambiente
    env_id = request.headers.get('X-Environment-Id')
    if not env_id:
        release_db_connection(conn)
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    # Query base segura
    base_query = "SELECT * FROM commands WHERE environment_id = %s"
    params = [int(env_id)]
    
    # Adiciona filtros de forma segura
    if category:
        # Valida categoria contra lista permitida
        allowed_categories = ['build', 'deploy', 'test', 'maintenance']
        if category in allowed_categories:
            base_query += " AND category = %s"
            params.append(category)
    
    # 🆕 Filtro por command_category (build/deploy)
    if command_category:
        allowed_command_categories = ['build', 'deploy']
        if command_category in allowed_command_categories:
            base_query += " AND command_category = %s"
            params.append(command_category)
    
    if search:
        # Sanitiza termo de busca
        search_term = f"%{search}%"
        base_query += " AND (name LIKE %s OR description LIKE %s)"
        params.append(search_term)
        params.append(search_term)
    
    base_query += " ORDER BY name"
    
    try:
        cursor.execute(base_query, tuple(params))
        commands = [dict(row) for row in cursor.fetchall()]
        return jsonify(commands)
    except PsycopgError as e:
        return jsonify({"error": f"Erro no banco de dados: {str(e)}"}), 500
    finally:
        release_db_connection(conn)

@commands_bp.route("/api/commands", methods=["POST"])
@require_admin
def create_command():
    """Cria novo comando com validação completa"""
    data = request.json
    
    # Validação de campos obrigatórios - 🆕 command_category adicionado
    required_fields = ["name", "type", "script", "command_category"]
    for field in required_fields:
        if not data.get(field):
            return jsonify({"error": f"Campo {field} é obrigatório"}), 400
    
    env_id = request.headers.get('X-Environment-Id')
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    # Valida tipo de script
    script_type = data.get("type", "bash")
    allowed_types = ['bash', 'powershell', 'python', 'nodejs', 'docker']
    if script_type not in allowed_types:
        return jsonify({"error": f"Tipo inválido. Use: {', '.join(allowed_types)}"}), 400
    
    # 🆕 Valida command_category
    command_category = data.get("command_category")
    allowed_categories = ['build', 'deploy']
    if command_category not in allowed_categories:
        return jsonify({"error": f"Categoria inválida. Use: {', '.join(allowed_categories)}"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Query segura com placeholders - 🆕 command_category incluído
        cursor.execute(
            """
            INSERT INTO commands (environment_id, name, command_category, type, description, script, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                int(env_id),
                data["name"],
                command_category,
                script_type,
                data.get("description", ""),
                data["script"],
                datetime.now()
            )
        )
        
        command_id = cursor.fetchone()['id']
        conn.commit()
        
        return jsonify({
            "success": True,
            "id": command_id,
            "message": "Comando criado com sucesso"
        }), 201
        
    except IntegrityError:
        return jsonify({"error": "Comando com este nome já existe neste ambiente"}), 409
    except PsycopgError as e:
        return jsonify({"error": f"Erro no banco de dados: {str(e)}"}), 500
    finally:
        release_db_connection(conn)

@commands_bp.route("/api/commands/<int:command_id>", methods=["PUT"])
@require_admin
def update_command(command_id):
    """Atualiza comando existente"""
    data = request.json
    env_id = request.headers.get('X-Environment-Id')
    
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400

    # Verificar se item é protegido
    if check_protected_item('commands', command_id):
        return jsonify({"error": "Este comando é protegido e não pode ser alterado"}), 403

    # 🆕 Validar command_category
    if 'command_category' in data:
        allowed_categories = ['build', 'deploy']
        if data['command_category'] not in allowed_categories:
            return jsonify({"error": f"Categoria inválida. Use: {', '.join(allowed_categories)}"}), 400

    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Verificar se já existe outro comando com esse nome no mesmo ambiente (exceto o atual)
        cursor.execute(
            "SELECT id FROM commands WHERE name = %s AND environment_id = %s AND id != %s",
            (data["name"], int(env_id), command_id)
        )
        existing = cursor.fetchone()
        
        if existing:
            release_db_connection(conn)
            return jsonify({"error": "Um comando com este nome já existe neste ambiente"}), 409

        # Atualizar o comando - 🆕 command_category incluído
        cursor.execute(
            """
            UPDATE commands 
            SET name = %s, command_category = %s, type = %s, description = %s, script = %s
            WHERE id = %s AND environment_id = %s
            """,
            (
                data["name"],
                data.get("command_category", "build"),
                data["type"],
                data.get("description", ""),
                data["script"],
                command_id,
                int(env_id),
            ),
        )

        conn.commit()
        return jsonify({"success": True, "message": "Comando atualizado com sucesso"})
    
    except IntegrityError:
        return jsonify({"error": "Erro de integridade ao atualizar comando"}), 409
    
    finally:
        release_db_connection(conn)

@commands_bp.route("/api/commands/<int:command_id>", methods=["DELETE"])
@require_admin
def delete_command(command_id):
    """Deleta comando com validação de ambiente"""
    
    env_id = request.headers.get('X-Environment-Id')
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    # Verificar se item é protegido
    if check_protected_item('commands', command_id):
        return jsonify({"error": "Este comando é protegido e não pode ser excluído"}), 403
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Verifica se comando existe e pertence ao ambiente
        cursor.execute(
            "SELECT id FROM commands WHERE id = %s AND environment_id = %s",
            (command_id, int(env_id))
        )
        
        if not cursor.fetchone():
            release_db_connection(conn)
            return jsonify({"error": "Comando não encontrado neste ambiente"}), 404
        
        # Deleta com prepared statement
        cursor.execute(
            "DELETE FROM commands WHERE id = %s AND environment_id = %s",
            (command_id, int(env_id))
        )
        
        conn.commit()
        return jsonify({"success": True, "message": "Comando excluído com sucesso"})
        
    except PsycopgError as e:
        return jsonify({"error": f"Erro no banco de dados: {str(e)}"}), 500
    finally:
        release_db_connection(conn)
