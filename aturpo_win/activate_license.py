#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ativação de Licença - Cliente
AtuRPO/DevOps
"""

import os
from license_system import (
    save_license_key,
    validate_license_hybrid,
    get_hardware_id,
    clear_license_cache,
    init_license_cache_db
)

def main():
    print("=" * 60)
    print("🔐 ATIVAÇÃO DE LICENÇA - AtuRPO/DevOps")
    print("=" * 60)
    print()

    # Inicializar banco de cache (criar tabelas se não existirem)
    init_license_cache_db()
    
    # Mostrar hardware ID
    hardware_id = get_hardware_id()
    print(f"💻 Hardware ID desta máquina:")
    print(f"   {hardware_id}")
    print()
    print("   (Envie este ID ao fornecedor se solicitado)")
    print()
    
    # Solicitar chave
    license_key = input("📋 Digite a chave de licença: ").strip()
    
    if not license_key:
        print("\n❌ Chave inválida!")
        return
    
    # Validar formato básico (XXXX-XXXX-XXXX-XXXX-XXXX)
    if len(license_key.replace('-', '')) != 20:
        print("\n❌ Formato de chave inválido!")
        print("   Formato esperado: XXXX-XXXX-XXXX-XXXX-XXXX")
        return
    
    print("\n🔄 Validando licença com o servidor...")
    print("   (Isso pode levar alguns segundos)")
    print()
    
    # Limpar cache antigo
    clear_license_cache()
    
    # Salvar chave
    if not save_license_key(license_key):
        print("❌ Erro ao salvar chave de licença!")
        return
    
    # Validar
    result = validate_license_hybrid(license_key)
    
    if result['valid']:
        license = result['license']
        print("=" * 60)
        print("✅ LICENÇA ATIVADA COM SUCESSO!")
        print("=" * 60)
        print()
        print(f"👤 Cliente: {license['customer_name']}")
        print(f"🏢 Empresa: {license['company_name']}")
        print(f"📦 Plano: {license['plan_type']}")
        print(f"📅 Válida até: {license['expires_at']}")
        print()
        print("🎉 Você já pode usar o sistema!")
        print()
    else:
        print("=" * 60)
        print("❌ FALHA NA ATIVAÇÃO")
        print("=" * 60)
        print()
        print(f"Erro: {result.get('error')}")
        print()
        print("Possíveis causas:")
        print("  • Chave de licença inválida")
        print("  • Licença expirada")
        print("  • Licença já vinculada a outra máquina")
        print("  • Sem conexão com o servidor")
        print()
        print("Entre em contato com o suporte para assistência.")
        print()
        
        # Remover chave inválida
        if os.path.exists('license.key'):
            os.remove('license.key')

if __name__ == '__main__':
    main()
