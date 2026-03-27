from datetime import datetime, timedelta, timezone
import os

CLONE_DIR = "cloned_repos"

def now_br():
    """Retorna a hora atual no fuso horario de Brasilia (UTC-3)"""
    return datetime.now(timezone.utc) - timedelta(hours=3)

def get_base_dir_for_pipeline(cursor, pipeline_id):
    """
    Retorna o BASE_DIR correto baseado no ambiente da pipeline.
    
    Args:
        cursor: Cursor do banco de dados
        pipeline_id: ID da pipeline
        
    Returns:
        str: Caminho do BASE_DIR correspondente ao ambiente
    """
    
    # Busca environment_id da pipeline
    cursor.execute(
        "SELECT environment_id FROM pipelines WHERE id = %s", (pipeline_id,)
    )
    pipeline = cursor.fetchone()
    
    if not pipeline:
        return CLONE_DIR  # Fallback
    
    # Busca nome do ambiente
    cursor.execute(
        "SELECT name FROM environments WHERE id = %s", (pipeline['environment_id'],)
    )
    env = cursor.fetchone()
    
    if not env:
        return CLONE_DIR  # Fallback
    
    # Mapeia ambiente para sufixo
    suffix_map = {
        'Produção': 'PRD',
        'Homologação': 'HOM',
        'Desenvolvimento': 'DEV',
        'Testes': 'TST'
    }
    suffix = suffix_map.get(env['name'], 'PRD')
    
    # Busca variável BASE_DIR_{SUFFIX}
    cursor.execute(
        "SELECT value FROM server_variables WHERE name = %s", (f"BASE_DIR_{suffix}",)
    )
    base_dir_var = cursor.fetchone()
    
    return base_dir_var["value"] if base_dir_var else CLONE_DIR


def get_base_dir_for_repo(cursor, repo_id):
    """
    Retorna o BASE_DIR correto baseado no ambiente do repositório.
    
    Args:
        cursor: Cursor do banco de dados
        repo_id: ID do repositório
        
    Returns:
        str: Caminho do BASE_DIR correspondente ao ambiente
    """
    
    # Busca environment_id do repositório
    cursor.execute(
        "SELECT environment_id FROM repositories WHERE id = %s", (repo_id,)
    )
    repo = cursor.fetchone()
    
    if not repo:
        return CLONE_DIR  # Fallback para compatibilidade
    
    # Busca nome do ambiente
    cursor.execute(
        "SELECT name FROM environments WHERE id = %s", (repo['environment_id'],)
    )
    env = cursor.fetchone()
    
    if not env:
        return CLONE_DIR  # Fallback
    
    # Mapeia ambiente para sufixo
    suffix_map = {
        'Produção': 'PRD',
        'Homologação': 'HOM',
        'Desenvolvimento': 'DEV',
        'Testes': 'TST'
    }
    suffix = suffix_map.get(env['name'], 'PRD')
    
    # Busca variável BASE_DIR_{SUFFIX}
    cursor.execute(
        "SELECT value FROM server_variables WHERE name = %s", (f"BASE_DIR_{suffix}",)
    )
    base_dir_var = cursor.fetchone()
    
    return base_dir_var["value"] if base_dir_var else CLONE_DIR
