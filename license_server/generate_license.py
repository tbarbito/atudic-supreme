#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate License - AtuDIC/DevOps
Gerenciador de licenças via linha de comando
"""

import os
import sys
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Configurações
LICENSE_API_URL = os.getenv('LICENSE_API_URL', 'http://localhost:5000')
API_SECRET = os.getenv('API_SECRET', 'change-this-secret-key-in-production')

# =================================================================
# FUNÇÕES AUXILIARES
# =================================================================

def make_request(method, endpoint, data=None):
    """Faz requisição para a API do license server"""
    headers = {
        'Content-Type': 'application/json',
        'X-API-Secret': API_SECRET
    }
    
    url = f"{LICENSE_API_URL}{endpoint}"
    
    try:
        if method == 'GET':
            response = requests.get(url, headers=headers, timeout=10)
        elif method == 'POST':
            response = requests.post(url, headers=headers, json=data, timeout=10)
        else:
            raise ValueError(f"Método não suportado: {method}")
        
        return response
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro na requisição: {e}")
        sys.exit(1)

# =================================================================
# COMANDOS
# =================================================================

def create_license(customer_name, customer_email, company_name, plan_type, days, hardware_id=None):
    """Cria uma nova licença"""
    print(f"🔧 Criando licença para {customer_name}...")
    
    data = {
        'customer_name': customer_name,
        'customer_email': customer_email,
        'company_name': company_name,
        'plan_type': plan_type,
        'days': days
    }

    if hardware_id:
        data['hardware_id'] = hardware_id
    
    response = make_request('POST', '/api/license/create', data)
    
    if response.status_code == 201:
        result = response.json()
        print(f"\n✅ LICENÇA CRIADA COM SUCESSO!\n")
        print(f"📋 Chave: {result['license_key']}")
        print(f"👤 Cliente: {customer_name}")
        print(f"🏢 Empresa: {company_name}")
        print(f"📦 Plano: {plan_type}")
        print(f"📅 Expira em: {result['expires_at']}")
        if hardware_id:
            print(f"🔒 Licença já vinculada ao hardware: {hardware_id[:16]}...")
        print(f"\n💾 Envie esta chave para o cliente ativar o sistema.\n")
        return result['license_key']
    else:
        print(f"❌ Erro ao criar licença: {response.text}")
        sys.exit(1)

def get_status(license_key):
    """Retorna status de uma licença"""
    print(f"🔍 Buscando status da licença {license_key}...")
    
    response = make_request('GET', f'/api/license/{license_key}/status')
    
    if response.status_code == 200:
        result = response.json()
        license_data = result['license']
        
        print(f"\n📊 STATUS DA LICENÇA\n")
        print(f"📋 Chave: {license_data['license_key']}")
        print(f"👤 Cliente: {license_data['customer_name']}")
        print(f"📧 Email: {license_data['customer_email']}")
        print(f"🏢 Empresa: {license_data['company_name']}")
        print(f"📦 Plano: {license_data['plan_type']}")
        print(f"✅ Ativa: {'Sim' if license_data['is_active'] else 'Não'}")
        print(f"📅 Criada em: {license_data['created_at']}")
        print(f"📅 Expira em: {license_data['expires_at']}")
        print(f"💻 Hardware ID: {license_data['hardware_id'] or 'Não vinculado'}")
        print(f"🔄 Validações: {license_data['validation_count']}")
        print(f"🕐 Última validação: {license_data['last_validation'] or 'Nunca'}")
        
        if result['recent_logs']:
            print(f"\n📝 ÚLTIMAS VALIDAÇÕES:\n")
            for log in result['recent_logs'][:5]:
                status_emoji = {
                    'SUCCESS': '✅',
                    'ACTIVATED': '🆕',
                    'BLOCKED': '🚫',
                    'EXPIRED': '⏰',
                    'HARDWARE_MISMATCH': '⚠️',
                    'INVALID': '❌'
                }.get(log['status'], '❓')
                
                print(f"{status_emoji} {log['created_at']} - {log['status']}")
                print(f"   {log['message']}")
                print(f"   IP: {log['ip_address']}")
                print()
    else:
        print(f"❌ Erro: {response.text}")
        sys.exit(1)

def block_license(license_key):
    """Bloqueia uma licença"""
    print(f"🚫 Bloqueando licença {license_key}...")
    
    response = make_request('POST', f'/api/license/{license_key}/block')
    
    if response.status_code == 200:
        print(f"✅ Licença bloqueada com sucesso!")
        print(f"⚠️  O cliente será bloqueado na próxima validação (até 24h).")
    else:
        print(f"❌ Erro: {response.text}")
        sys.exit(1)

def activate_license(license_key):
    """Ativa/Reativa uma licença"""
    print(f"✅ Ativando licença {license_key}...")
    
    response = make_request('POST', f'/api/license/{license_key}/activate')
    
    if response.status_code == 200:
        print(f"✅ Licença ativada com sucesso!")
        print(f"🔓 O cliente pode usar o sistema imediatamente.")
    else:
        print(f"❌ Erro: {response.text}")
        sys.exit(1)

def renew_license(license_key, days):
    """Renova uma licença"""
    print(f"🔄 Renovando licença {license_key} por {days} dias...")
    
    data = {'days': days}
    response = make_request('POST', f'/api/license/{license_key}/renew', data)
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Licença renovada com sucesso!")
        print(f"📅 Nova data de expiração: {result['new_expires_at']}")
    else:
        print(f"❌ Erro: {response.text}")
        sys.exit(1)

def test_connection():
    """Testa conexão com o servidor"""
    print(f"🔌 Testando conexão com {LICENSE_API_URL}...")
    
    try:
        response = requests.get(f"{LICENSE_API_URL}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"\n✅ SERVIDOR ONLINE")
            print(f"📡 Status: {data['status']}")
            print(f"🏷️  Serviço: {data['service']}")
            print(f"📦 Versão: {data['version']}")
            print(f"💾 Database: {data['database']}")
        else:
            print(f"❌ Servidor respondeu com erro: {response.status_code}")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"❌ Não foi possível conectar ao servidor: {e}")
        sys.exit(1)

# =================================================================
# MENU INTERATIVO
# =================================================================

def show_menu():
    """Mostra menu interativo"""
    print("\n" + "="*60)
    print("🔐 GERENCIADOR DE LICENÇAS - AtuDIC/DevOps")
    print("="*60)
    print("\n1️⃣  Criar nova licença")
    print("2️⃣  Ver status de licença")
    print("3️⃣  Bloquear licença")
    print("4️⃣  Ativar/Reativar licença")
    print("5️⃣  Renovar licença")
    print("6️⃣  Testar conexão com servidor")
    print("0️⃣  Sair")
    print("\n" + "="*60)
    
    choice = input("\n👉 Escolha uma opção: ").strip()
    return choice

def interactive_mode():
    """Modo interativo"""
    while True:
        choice = show_menu()
        
        if choice == '1':
            print("\n📝 CRIAR NOVA LICENÇA")
            print("-" * 40)
            customer_name = input("👤 Nome do cliente: ").strip()
            customer_email = input("📧 Email do cliente: ").strip()
            company_name = input("🏢 Nome da empresa: ").strip()
            
            print("\n💻 Hardware ID do cliente:")
            print("   (Solicite ao cliente executar: python3 activate_license.py)")
            print("   (O Hardware ID será exibido no início)")
            hardware_id = input("💾 Hardware ID (deixe vazio para não vincular): ").strip() or None
            
            print("\n📦 Planos disponíveis:")
            print("  • basic - 5 usuários, 20 repos")
            print("  • standard - 10 usuários, 50 repos")
            print("  • premium - ilimitado")
            plan_type = input("📦 Plano (basic/standard/premium): ").strip().lower()
            days = int(input("📅 Dias de validade: ").strip())
            
            create_license(customer_name, customer_email, company_name, plan_type, days, hardware_id)
            input("\n⏎ Pressione ENTER para continuar...")
        
        elif choice == '2':
            license_key = input("\n📋 Digite a chave da licença: ").strip()
            get_status(license_key)
            input("\n⏎ Pressione ENTER para continuar...")
        
        elif choice == '3':
            license_key = input("\n📋 Digite a chave da licença para BLOQUEAR: ").strip()
            confirm = input(f"⚠️  Confirma o bloqueio de {license_key}? (s/N): ").strip().lower()
            if confirm == 's':
                block_license(license_key)
            else:
                print("❌ Operação cancelada.")
            input("\n⏎ Pressione ENTER para continuar...")
        
        elif choice == '4':
            license_key = input("\n📋 Digite a chave da licença para ATIVAR: ").strip()
            activate_license(license_key)
            input("\n⏎ Pressione ENTER para continuar...")
        
        elif choice == '5':
            license_key = input("\n📋 Digite a chave da licença: ").strip()
            days = int(input("📅 Quantos dias adicionar? ").strip())
            renew_license(license_key, days)
            input("\n⏎ Pressione ENTER para continuar...")
        
        elif choice == '6':
            test_connection()
            input("\n⏎ Pressione ENTER para continuar...")
        
        elif choice == '0':
            print("\n👋 Até logo!\n")
            sys.exit(0)
        
        else:
            print("\n❌ Opção inválida!")
            input("\n⏎ Pressione ENTER para continuar...")

# =================================================================
# MAIN
# =================================================================

def main():
    if len(sys.argv) == 1:
        # Modo interativo
        interactive_mode()
    
    # Modo CLI
    command = sys.argv[1]
    
    if command == 'test':
        test_connection()
    
    elif command == 'create':
        if len(sys.argv) < 7:
            print("Uso: generate_license.py create <nome> <email> <empresa> <plano> <dias> [hardware_id]")
            sys.exit(1)
        hardware_id = sys.argv[7] if len(sys.argv) > 7 else None
        create_license(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], int(sys.argv[6]), hardware_id)
    
    elif command == 'status':
        if len(sys.argv) < 3:
            print("Uso: generate_license.py status <chave>")
            sys.exit(1)
        get_status(sys.argv[2])
    
    elif command == 'block':
        if len(sys.argv) < 3:
            print("Uso: generate_license.py block <chave>")
            sys.exit(1)
        block_license(sys.argv[2])
    
    elif command == 'activate':
        if len(sys.argv) < 3:
            print("Uso: generate_license.py activate <chave>")
            sys.exit(1)
        activate_license(sys.argv[2])
    
    elif command == 'renew':
        if len(sys.argv) < 4:
            print("Uso: generate_license.py renew <chave> <dias>")
            sys.exit(1)
        renew_license(sys.argv[2], int(sys.argv[3]))
    
    else:
        print(f"❌ Comando desconhecido: {command}")
        print("\nComandos disponíveis:")
        print("  • test - Testa conexão")
        print("  • create - Cria licença")
        print("  • status - Ver status")
        print("  • block - Bloquear")
        print("  • activate - Ativar")
        print("  • renew - Renovar")
        sys.exit(1)

if __name__ == '__main__':
    main()
