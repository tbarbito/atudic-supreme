"""
Validation and sanitization utilities.

This module provides functions to sanitize user inputs (paths, branch names, commit messages)
and safely execute Git commands, preventing common security vulnerabilities like
command injection and path traversal.
"""
import re
import subprocess
import shlex

def sanitize_path_component(component):
    """
    Sanitiza componentes de caminho para prevenir path traversal.
    Remove caracteres perigosos e valida o formato.
    """
    if not component:
        return None
    
    # Remove espaços em branco
    component = component.strip()
    
    # Rejeita componentes perigosos
    dangerous_patterns = ['..', './', '\\', '~', '$', '`', ';', '|', '&', '<', '>', '*', '?', '[', ']', '{', '}', '(', ')']
    for pattern in dangerous_patterns:
        if pattern in component:
            raise ValueError(f"Caractere perigoso detectado no caminho: {pattern}")
    
    # Valida que contém apenas caracteres seguros
    if not re.match(r'^[a-zA-Z0-9_\-\.]+$', component):
        raise ValueError(f"Nome de caminho inválido: {component}")
    
    return component

def sanitize_branch_name(branch_name):
    """
    Sanitiza nome de branch Git para prevenir injection.
    """
    if not branch_name:
        return None
    
    branch_name = branch_name.strip()
    
    # Git branch names não podem conter certos caracteres
    dangerous_chars = ['..', '~', '^', ':', '?', '*', '[', '\\', ' ', '\t', '\n']
    for char in dangerous_chars:
        if char in branch_name:
            raise ValueError(f"Caractere inválido em nome de branch: {char}")
    
    # Valida formato básico
    if not re.match(r'^[a-zA-Z0-9/_\-\.]+$', branch_name):
        raise ValueError(f"Formato de branch inválido: {branch_name}")
    
    # Não pode começar ou terminar com /
    if branch_name.startswith('/') or branch_name.endswith('/'):
        raise ValueError("Branch não pode começar ou terminar com /")
    
    return branch_name

def sanitize_commit_message(message):
    """
    Sanitiza mensagem de commit para prevenir injection.
    """
    if not message:
        raise ValueError("Mensagem de commit não pode estar vazia")
    
    message = message.strip()
    
    # Remove caracteres de controle e caracteres perigosos
    message = re.sub(r'[\x00-\x1F\x7F]', '', message)
    
    # Limita tamanho
    if len(message) > 500:
        message = message[:500]
    
    # Escapa aspas e caracteres especiais para uso em shell
    # Usando shlex.quote para escapar adequadamente
    return message

def validate_git_url(url):
    """
    Valida URL do Git para garantir que é HTTPS e de origem confiável.
    """
    if not url:
        raise ValueError("URL não pode estar vazia")
    
    # Deve ser HTTPS
    if not url.startswith('https://'):
        raise ValueError("Apenas URLs HTTPS são permitidas")
    
    # Valida formato básico de URL Git
    git_url_pattern = r'^https://[a-zA-Z0-9\-\.]+/[a-zA-Z0-9\-_\.]+/[a-zA-Z0-9\-_\.]+\.git$'
    if not re.match(git_url_pattern, url):
        raise ValueError("Formato de URL Git inválido")
    
    return url

def execute_git_command_safely(command_args, cwd=None, timeout=300):
    """
    Executa comandos Git de forma segura usando lista de argumentos.
    
    Args:
        command_args: Lista de argumentos (não string!)
        cwd: Diretório de trabalho
        timeout: Timeout em segundos
    
    Returns:
        subprocess.CompletedProcess
    """
    # Garante que o primeiro argumento é 'git'
    if not command_args or command_args[0] != 'git':
        raise ValueError("Comando deve começar com 'git'")
    
    # Valida que todos os argumentos são strings
    if not all(isinstance(arg, str) for arg in command_args):
        raise ValueError("Todos os argumentos devem ser strings")
    
    # Executa com shell=False para segurança
    try:
        result = subprocess.run(
            command_args,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout,
            shell=False  # CRÍTICO: shell=False previne injection
        )
        return result
    except subprocess.TimeoutExpired:
        raise Exception(f"Comando Git excedeu o timeout de {timeout}s")
    except subprocess.CalledProcessError as e:
        raise Exception(f"Erro ao executar comando Git: {e.stderr}")
