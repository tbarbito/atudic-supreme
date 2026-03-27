"""
Cryptography utilities for token encryption/decryption.

This module provides the TokenEncryption class for secure encryption
and decryption of sensitive tokens (e.g., GitHub tokens, API keys).
"""
import os
import base64
from cryptography.fernet import Fernet


class TokenEncryption:
    """
    Gerenciador de criptografia para tokens sensíveis.
    Versão robusta com tratamento de erros melhorado.
    """
    
    def __init__(self, key_filename='.encryption_key'):
        """Inicializa o sistema de criptografia"""
        # Get base directory - will be passed from app.py or use current directory
        import sys
        if hasattr(sys, 'frozen'):
            # Rodando como executável empacotado
            base_dir = os.path.dirname(sys.executable)
        else:
            # Rodando como script Python - usa diretório do projeto
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            
        self.key_file = os.path.join(base_dir, key_filename)
        self.key = None
        self.cipher = None
        
        try:
            self.key = self._get_or_create_key()
            self.cipher = Fernet(self.key)
            print(f"   ✓ Criptografia inicializada: {self.key_file}")
        except Exception as e:
            print(f"   ❌ ERRO ao inicializar criptografia: {e}")
            raise
    
    def _get_or_create_key(self):
        """
        Obtém chave de criptografia existente ou cria uma nova.
        """
        try:
            if os.path.exists(self.key_file):
                # Carrega chave existente
                print(f"   📂 Carregando chave existente...")
                with open(self.key_file, 'rb') as f:
                    key = f.read()
                
                # Valida que a chave é válida
                try:
                    Fernet(key)  # Testa se é uma chave válida
                    print(f"   ✓ Chave válida carregada")
                    return key
                except Exception as e:
                    print(f"   ⚠️  Chave inválida encontrada, gerando nova: {e}")
                    # Remove chave inválida
                    os.remove(self.key_file)
            
            # Gera nova chave
            print(f"   🔑 Gerando nova chave de criptografia...")
            key = Fernet.generate_key()
            
            # Cria diretório se não existir
            base_dir = os.path.dirname(self.key_file)
            if base_dir:  # Só cria se houver diretório pai
                os.makedirs(base_dir, exist_ok=True)
            
            # Salva chave com permissões restritas
            with open(self.key_file, 'wb') as f:
                f.write(key)
            
            # Define permissões apenas para owner (Unix/Linux)
            try:
                os.chmod(self.key_file, 0o600)
                print(f"   ✓ Permissões definidas: 0600")
            except Exception as e:
                print(f"   ⚠️  Não foi possível definir permissões: {e}")
            
            print(f"   ✓ Nova chave criada: {self.key_file}")
            print(f"")
            print(f"   ⚠️  IMPORTANTE: Faça backup desta chave!")
            print(f"   📋 Backup recomendado:")
            print(f"      cp {self.key_file} {self.key_file}.backup")
            print(f"")
            
            return key
            
        except PermissionError as e:
            raise Exception(f"Sem permissão para criar arquivo de chave: {e}")
        except OSError as e:
            raise Exception(f"Erro ao acessar sistema de arquivos: {e}")
    
    def encrypt_token(self, token):
        """Criptografa um token."""
        if not token:
            return None
        
        if not self.cipher:
            raise Exception("Sistema de criptografia não inicializado!")
        
        try:
            token_bytes = token.encode('utf-8')
            encrypted_bytes = self.cipher.encrypt(token_bytes)
            return base64.b64encode(encrypted_bytes).decode('utf-8')
        except Exception as e:
            raise Exception(f"Erro ao criptografar token: {e}")
    
    def decrypt_token(self, encrypted_token):
        """Descriptografa um token."""
        if not encrypted_token:
            return None
        
        if not self.cipher:
            raise Exception("Sistema de criptografia não inicializado!")
        
        try:
            encrypted_bytes = base64.b64decode(encrypted_token.encode('utf-8'))
            decrypted_bytes = self.cipher.decrypt(encrypted_bytes)
            return decrypted_bytes.decode('utf-8')
        except Exception as e:
            print(f"❌ Erro ao descriptografar token: {type(e).__name__}")
            raise Exception(f"Erro ao descriptografar token: token pode estar corrompido")
    
    def is_initialized(self):
        """Verifica se o sistema está inicializado"""
        return self.cipher is not None

    def has_backup(self):
        """Verifica se existe um backup da chave."""
        backup_path = self.key_file + '.backup'
        return os.path.exists(backup_path)

    def create_backup(self):
        """Cria backup da chave de criptografia. Retorna o caminho do backup."""
        if not self.key:
            raise Exception("Chave de criptografia não carregada")
        backup_path = self.key_file + '.backup'
        with open(backup_path, 'wb') as f:
            f.write(self.key)
        try:
            os.chmod(backup_path, 0o600)
        except Exception:
            pass
        return backup_path

    def get_key_info(self):
        """Retorna informações sobre a chave (sem expor a chave em si)."""
        import hashlib
        info = {
            'initialized': self.is_initialized(),
            'key_file': self.key_file,
            'key_exists': os.path.exists(self.key_file),
            'has_backup': self.has_backup(),
        }
        if self.key:
            info['key_fingerprint'] = hashlib.sha256(self.key).hexdigest()[:16]
        return info


# Instância global
token_encryption = None

def init_crypto():
    """
    Inicializa a instância global de criptografia.
    Deve ser chamado na inicialização da aplicação via run.py.
    """
    global token_encryption
    try:
        token_encryption = TokenEncryption()
        print("🔐 Criptografia inicializada (instância global)")
        return token_encryption
    except Exception as e:
        print(f"❌ Falha ao inicializar criptografia global: {e}")
        return None
