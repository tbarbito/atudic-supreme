#!/bin/bash
# =============================================================================
# 🗑️ ATUDIC DEVOPS - DESINSTALADOR LINUX
# =============================================================================
# Remove completamente o sistema e serviço
# Uso: sudo ./uninstall_linux.sh
# =============================================================================

set -e

echo "=========================================="
echo "🗑️  ATUDIC DEVOPS - Desinstalador Linux"
echo "=========================================="
echo ""

# Verificar se está rodando como root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ Este script precisa ser executado como root (use sudo)"
    exit 1
fi

# Variáveis
SERVICE_NAME="atudic-devops"
INSTALL_DIR="/opt/atudic-devops"
APP_USER="atudic"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

# Confirmação
echo "⚠️  ATENÇÃO: Esta ação irá:"
echo ""
echo "   • Parar e remover o serviço $SERVICE_NAME"
echo "   • Remover todos os arquivos em $INSTALL_DIR"
echo "   • Remover o usuário $APP_USER (OPCIONAL)"
echo "   • Remover banco de dados PostgreSQL (OPCIONAL)"
echo ""
read -p "Tem certeza que deseja continuar? (digite SIM para confirmar): " CONFIRM

if [ "$CONFIRM" != "SIM" ]; then
    echo "Desinstalação cancelada."
    exit 0
fi

echo ""
print_info "Iniciando desinstalação..."

# Parar serviço
if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo ""
    print_info "Parando serviço..."
    systemctl stop "$SERVICE_NAME"
    print_success "Serviço parado"
fi

# Desabilitar serviço
if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
    echo ""
    print_info "Desabilitando serviço..."
    systemctl disable "$SERVICE_NAME"
    print_success "Serviço desabilitado"
fi

# Remover arquivo de serviço
if [ -f "/etc/systemd/system/${SERVICE_NAME}.service" ]; then
    echo ""
    print_info "Removendo arquivo de serviço..."
    rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
    systemctl daemon-reload
    print_success "Arquivo de serviço removido"
fi

# Remover diretório de instalação
if [ -d "$INSTALL_DIR" ]; then
    echo ""
    print_info "Removendo diretório de instalação..."
    rm -rf "$INSTALL_DIR"
    print_success "Diretório removido: $INSTALL_DIR"
fi

# Remover usuário (opcional)
echo ""
read -p "Deseja remover o usuário do sistema '$APP_USER'? (s/N): " REMOVE_USER

if [[ "$REMOVE_USER" =~ ^[Ss]$ ]]; then
    if id "$APP_USER" &>/dev/null; then
        userdel -r "$APP_USER" 2>/dev/null || userdel "$APP_USER"
        print_success "Usuário $APP_USER removido"
    fi
fi

# Remover banco de dados (opcional)
echo ""
read -p "Deseja remover o banco de dados PostgreSQL? (s/N): " REMOVE_DB

if [[ "$REMOVE_DB" =~ ^[Ss]$ ]]; then
    echo ""
    print_info "Removendo banco de dados..."
    
    sudo -u postgres psql << EOF
DROP DATABASE IF EXISTS atudic_devops;
DROP USER IF EXISTS atudic_user;
EOF
    
    print_success "Banco de dados removido"
fi

# Remover configuração Nginx (opcional)
if [ -f "/etc/nginx/sites-available/atudic-devops" ]; then
    echo ""
    read -p "Deseja remover a configuração do Nginx? (s/N): " REMOVE_NGINX
    
    if [[ "$REMOVE_NGINX" =~ ^[Ss]$ ]]; then
        rm -f "/etc/nginx/sites-enabled/atudic-devops"
        rm -f "/etc/nginx/sites-available/atudic-devops"
        systemctl reload nginx
        print_success "Configuração Nginx removida"
    fi
fi

echo ""
echo "=========================================="
echo "✅ DESINSTALAÇÃO CONCLUÍDA!"
echo "=========================================="
echo ""

exit 0
