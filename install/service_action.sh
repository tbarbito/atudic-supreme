# !/bin/bash
# =============================================================================
# Script Bash para gerenciar serviços remotamente em servidores Linux via systemctl
# =============================================================================
# Certifique-se de que o SSH esteja configurado e que você tenha acesso ao servidor remoto.
# =============================================================================
# ============================================================================
# opcão 1: Usando systemctl com SSH
# =============================================================================
# Para parar o serviço
systemctl -H meu_usuario@servidor-remoto stop meu_servico.service

# Para iniciar o serviço
systemctl -H meu_usuario@servidor-remoto start meu_servico.service

# Para ver o status
systemctl -H meu_usuario@servidor-remoto status meu_servico.service

# =============================================================================
# opção 2: Usando SSH para executar comandos remotamente
# =============================================================================
# Para parar o serviço
ssh meu_usuario@servidor-remoto "sudo systemctl stop meu_servico.service"

# Para iniciar o serviço
ssh meu_usuario@servidor-remoto "sudo systemctl start meu_servico.service"

# Para ver o status
ssh meu_usuario@servidor-remoto "sudo systemctl status meu_servico.service"