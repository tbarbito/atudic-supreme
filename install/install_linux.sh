#!/bin/bash
# =============================================================================
# 🚀 ATUDIC DEVOPS - INSTALADOR LINUX (Ubuntu/Debian/CentOS/RHEL)
# =============================================================================
# Instala o sistema como serviço systemd
# Uso: sudo ./install_linux.sh
# =============================================================================

set -e  # Parar em caso de erro

echo "=========================================="
echo "🚀 ATUDIC DEVOPS - Instalador Linux"
echo "=========================================="
echo ""

# Verificar se está rodando como root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ Este script precisa ser executado como root (use sudo)"
    exit 1
fi

# Variáveis de configuração
APP_NAME="atudic-devops"
APP_USER="barbito"
INSTALL_DIR="/opt/atudic-devops"
SERVICE_NAME="atudic-devops"
PYTHON_VERSION="3.9"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Funções auxiliares
print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

# Detectar distribuição Linux
detect_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        DISTRO=$ID
        VERSION=$VERSION_ID
    else
        print_error "Não foi possível detectar a distribuição Linux"
        exit 1
    fi
    
    print_info "Distribuição detectada: $DISTRO $VERSION"
}

# Instalar dependências do sistema
install_system_dependencies() {
    echo ""
    echo "📦 Instalando dependências do sistema..."
    echo ""
    
    if [[ "$DISTRO" == "ubuntu" ]] || [[ "$DISTRO" == "debian" ]]; then
        apt-get update
        apt-get install -y \
            python3 \
            python3-pip \
            python3-venv \
            postgresql \
            postgresql-contrib \
            git \
            curl \
            nginx
            
    elif [[ "$DISTRO" == "centos" ]] || [[ "$DISTRO" == "rhel" ]] || [[ "$DISTRO" == "fedora" ]]; then
        dnf install -y \
            python3 \
            python3-pip \
            postgresql-server \
            postgresql-contrib \
            git \
            curl \
            nginx
            
        # Inicializar PostgreSQL no CentOS/RHEL
        postgresql-setup --initdb
    else
        print_error "Distribuição não suportada: $DISTRO"
        exit 1
    fi
    
    print_success "Dependências do sistema instaladas"
}

# Criar usuário do sistema
create_system_user() {
    echo ""
    echo "👤 Criando usuário do sistema..."
    echo ""
    
    if id "$APP_USER" &>/dev/null; then
        print_info "Usuário $APP_USER já existe"
    else
        useradd -r -s /bin/bash -d "$INSTALL_DIR" -m "$APP_USER"
        print_success "Usuário $APP_USER criado"
    fi
}

# Copiar arquivos da aplicação
install_application() {
    echo ""
    echo "📂 Instalando aplicação..."
    echo ""
    
    # Criar diretório de instalação
    mkdir -p "$INSTALL_DIR"
    
    # Copiar arquivos do diretório atual
    CURRENT_DIR=$(pwd)
    
    print_info "Copiando arquivos de: $CURRENT_DIR"
    
    # Copiar arquivos principais
    cp -f "$CURRENT_DIR/app.py" "$INSTALL_DIR/" 2>/dev/null || print_error "app.py não encontrado"
    cp -f "$CURRENT_DIR/index.html" "$INSTALL_DIR/" 2>/dev/null || print_error "index.html não encontrado"
    cp -f "$CURRENT_DIR/integration.js" "$INSTALL_DIR/" 2>/dev/null || print_error "integration.js não encontrado"
    cp -f "$CURRENT_DIR/api-client.js" "$INSTALL_DIR/" 2>/dev/null || print_error "api-client.js não encontrado"
    
    # Criar diretórios necessários
    mkdir -p "$INSTALL_DIR/logs"
    mkdir -p "$INSTALL_DIR/cloned_repos"
    
    # Definir permissões
    chown -R "$APP_USER:$APP_USER" "$INSTALL_DIR"
    chmod 755 "$INSTALL_DIR"
    
    print_success "Arquivos da aplicação instalados em $INSTALL_DIR"
}

# Criar arquivo requirements.txt
create_requirements() {
    echo ""
    echo "📝 Criando requirements.txt..."
    echo ""
    
    cat > "$INSTALL_DIR/requirements.txt" << 'EOF'
Flask==3.0.0
Flask-CORS==4.0.0
psycopg2-binary==2.9.9
python-dotenv==1.0.0
cryptography==41.0.7
pytz==2023.3
EOF
    
    print_success "requirements.txt criado"
}

# Criar ambiente virtual Python e instalar dependências
setup_python_environment() {
    echo ""
    echo "🐍 Configurando ambiente Python..."
    echo ""
    
    # Criar venv
    cd "$INSTALL_DIR"
    python3 -m venv venv
    
    # Ativar venv e instalar dependências
    source "$INSTALL_DIR/venv/bin/activate"
    pip install --upgrade pip
    pip install -r "$INSTALL_DIR/requirements.txt"
    deactivate
    
    chown -R "$APP_USER:$APP_USER" "$INSTALL_DIR/venv"
    
    print_success "Ambiente Python configurado"
}

# Configurar PostgreSQL
setup_postgresql() {
    echo ""
    echo "🐘 Configurando PostgreSQL..."
    echo ""
    
    # Iniciar PostgreSQL
    systemctl start postgresql
    systemctl enable postgresql
    
    # Criar banco e usuário
    print_info "Digite a senha para o usuário PostgreSQL 'atudic':"
    read -s DB_PASSWORD
    echo ""
    
    sudo -u postgres psql << EOF
-- Criar usuário
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_user WHERE usename = 'atudic') THEN
        CREATE USER atudic WITH PASSWORD '$DB_PASSWORD';
    END IF;
END \$\$;

-- Criar banco de dados
SELECT 'CREATE DATABASE atudic_devops OWNER atudic'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'atudic_devops')\gexec

-- Conceder privilégios
GRANT ALL PRIVILEGES ON DATABASE atudic_devops TO atudic;
EOF
    
    print_success "PostgreSQL configurado"
    
    # Criar arquivo .env
    cat > "$INSTALL_DIR/.env" << EOF
DB_HOST=localhost
DB_PORT=5432
DB_NAME=atudic_devops
DB_USER=atudic
DB_PASSWORD=$DB_PASSWORD
FLASK_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
EOF
    
    chmod 600 "$INSTALL_DIR/.env"
    chown "$APP_USER:$APP_USER" "$INSTALL_DIR/.env"
    
    print_success "Arquivo .env criado"
}

# Criar arquivo de serviço systemd
create_systemd_service() {
    echo ""
    echo "⚙️  Criando serviço systemd..."
    echo ""
    
    cat > "/etc/systemd/system/${SERVICE_NAME}.service" << EOF
[Unit]
Description=ATUDIC DevOps Dashboard
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$INSTALL_DIR/venv/bin"
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/app.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$SERVICE_NAME

# Limites de recursos
LimitNOFILE=65536
TimeoutStartSec=300
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF
    
    print_success "Serviço systemd criado"
}

# Configurar Nginx (opcional)
configure_nginx() {
    echo ""
    read -p "🌐 Deseja configurar Nginx como reverse proxy? (s/N): " CONFIGURE_NGINX
    
    if [[ "$CONFIGURE_NGINX" =~ ^[Ss]$ ]]; then
        echo ""
        print_info "Configurando Nginx..."
        
        read -p "Digite o domínio ou IP do servidor (ex: atudic-devops.exemplo.com): " SERVER_NAME
        
        cat > "/etc/nginx/sites-available/$APP_NAME" << EOF
server {
    listen 80;
    server_name $SERVER_NAME;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_cache_bypass \$http_upgrade;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
        
        # Habilitar site
        ln -sf "/etc/nginx/sites-available/$APP_NAME" "/etc/nginx/sites-enabled/"
        
        # Testar configuração
        nginx -t
        
        # Reiniciar Nginx
        systemctl restart nginx
        systemctl enable nginx
        
        print_success "Nginx configurado"
    fi
}

# Configurar firewall
configure_firewall() {
    echo ""
    read -p "🔥 Deseja configurar o firewall? (s/N): " CONFIGURE_FW
    
    if [[ "$CONFIGURE_FW" =~ ^[Ss]$ ]]; then
        echo ""
        print_info "Configurando firewall..."
        
        if command -v ufw &> /dev/null; then
            # UFW (Ubuntu/Debian)
            ufw allow 5000/tcp
            ufw allow 80/tcp
            ufw allow 443/tcp
            print_success "UFW configurado"
            
        elif command -v firewall-cmd &> /dev/null; then
            # firewalld (CentOS/RHEL)
            firewall-cmd --permanent --add-port=5000/tcp
            firewall-cmd --permanent --add-port=80/tcp
            firewall-cmd --permanent --add-port=443/tcp
            firewall-cmd --reload
            print_success "firewalld configurado"
        fi
    fi
}

# Iniciar serviço
start_service() {
    echo ""
    echo "🚀 Iniciando serviço..."
    echo ""
    
    # Recarregar systemd
    systemctl daemon-reload
    
    # Habilitar serviço para iniciar com o sistema
    systemctl enable "$SERVICE_NAME"
    
    # Iniciar serviço
    systemctl start "$SERVICE_NAME"
    
    # Aguardar alguns segundos
    sleep 3
    
    # Verificar status
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        print_success "Serviço iniciado com sucesso!"
    else
        print_error "Falha ao iniciar o serviço"
        systemctl status "$SERVICE_NAME"
        exit 1
    fi
}

# Exibir informações finais
show_final_info() {
    echo ""
    echo "=========================================="
    echo "✅ INSTALAÇÃO CONCLUÍDA!"
    echo "=========================================="
    echo ""
    echo "📌 Informações importantes:"
    echo ""
    echo "   Diretório: $INSTALL_DIR"
    echo "   Usuário: $APP_USER"
    echo "   Serviço: $SERVICE_NAME"
    echo ""
    echo "🔧 Comandos úteis:"
    echo ""
    echo "   Verificar status:    sudo systemctl status $SERVICE_NAME"
    echo "   Parar serviço:       sudo systemctl stop $SERVICE_NAME"
    echo "   Iniciar serviço:     sudo systemctl start $SERVICE_NAME"
    echo "   Reiniciar serviço:   sudo systemctl restart $SERVICE_NAME"
    echo "   Ver logs:            sudo journalctl -u $SERVICE_NAME -f"
    echo "   Desabilitar serviço: sudo systemctl disable $SERVICE_NAME"
    echo ""
    echo "🌐 Acesso à aplicação:"
    echo ""
    echo "   URL: http://$(hostname -I | awk '{print $1}'):5000"
    echo ""
    echo "   Usuário padrão: admin"
    echo "   Senha padrão: admin123"
    echo ""
    echo "⚠️  IMPORTANTE: Altere a senha padrão após o primeiro login!"
    echo ""
}

# EXECUÇÃO PRINCIPAL
main() {
    detect_distro
    install_system_dependencies
    create_system_user
    install_application
    create_requirements
    setup_python_environment
    setup_postgresql
    create_systemd_service
    configure_nginx
    configure_firewall
    start_service
    show_final_info
}

# Executar instalação
main

exit 0
