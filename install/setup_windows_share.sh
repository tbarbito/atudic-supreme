#!/bin/bash
# =============================================================================
# Script para configurar compartilhamentos Windows no Linux
# =============================================================================

echo "=============================================="
echo "🔗 CONFIGURAÇÃO DE COMPARTILHAMENTOS WINDOWS"
echo "=============================================="
echo ""

# Variáveis - EDITE AQUI!
WIN_IP="192.168.15.11"           # IP da máquina Windows
WIN_USER="tiago.barbieri"      # Usuário Windows
WIN_DOMAIN="sp01"           # Domínio Windows (se aplicável)
WIN_PASS="yg12Rd34@lnx"        # Senha Windows
MOUNT_BASE="/mnt/protheus"      # Base dos pontos de montagem

# Lista de compartilhamentos
declare -a SHARES=("builds" "fontes" "patches" "includes" "logs")

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_error() { echo -e "${RED}❌ $1${NC}"; }
print_info() { echo -e "${YELLOW}ℹ️  $1${NC}"; }

# Verificar se está rodando como root
if [ "$EUID" -ne 0 ]; then 
    print_error "Execute como root: sudo ./setup_windows_shares.sh"
    exit 1
fi

# Passo 1: Instalar CIFS
echo "📦 Instalando cifs-utils..."
apt update -qq
apt install -y cifs-utils
print_success "cifs-utils instalado"

# Passo 2: Criar arquivo de credenciais
echo ""
print_info "Criando arquivo de credenciais..."
cat > /etc/samba-credentials << EOF
username=$WIN_USER
password=$WIN_PASS
domain=$WIN_DOMAIN
EOF
chmod 600 /etc/samba-credentials
print_success "Credenciais configuradas"

# Passo 3: Criar pontos de montagem
echo ""
print_info "Criando pontos de montagem..."
for share in "${SHARES[@]}"; do
    mkdir -p "$MOUNT_BASE/$share"
    print_info "Criado: $MOUNT_BASE/$share"
done
chown -R barbito:barbito "$MOUNT_BASE"
print_success "Pontos de montagem criados"

# Passo 4: Montar compartilhamentos
echo ""
print_info "Montando compartilhamentos..."
for share in "${SHARES[@]}"; do
    echo "Montando $share..."
    mount -t cifs "//$WIN_IP/$share" "$MOUNT_BASE/$share" \
        -o credentials=/etc/samba-credentials,uid=1000,gid=1000,file_mode=0777,dir_mode=0777 \
        2>/dev/null
    
    if [ $? -eq 0 ]; then
        print_success "$share montado com sucesso"
    else
        print_error "Falha ao montar $share (verifique se existe no Windows)"
    fi
done

# Passo 5: Adicionar ao fstab
echo ""
print_info "Configurando montagem automática..."

# Backup do fstab
cp /etc/fstab /etc/fstab.backup.$(date +%Y%m%d_%H%M%S)

# Remover entradas antigas se existirem
sed -i '/# Compartilhamentos Protheus Windows/d' /etc/fstab
sed -i "/\\/mnt\\/protheus\\//d" /etc/fstab

# Adicionar novas entradas
echo "" >> /etc/fstab
echo "# Compartilhamentos Protheus Windows" >> /etc/fstab
for share in "${SHARES[@]}"; do
    echo "//$WIN_IP/$share $MOUNT_BASE/$share cifs credentials=/etc/samba-credentials,uid=1000,gid=1000,file_mode=0777,dir_mode=0777,_netdev,nofail 0 0" >> /etc/fstab
done

print_success "fstab configurado"

# Passo 6: Testar
echo ""
print_info "Testando montagens..."
mount -a
sleep 2

echo ""
echo "=============================================="
echo "📊 RESULTADO DAS MONTAGENS:"
echo "=============================================="
df -h | grep "$MOUNT_BASE" || print_error "Nenhum compartilhamento montado"

echo ""
echo "=============================================="
echo "✅ CONFIGURAÇÃO CONCLUÍDA!"
echo "=============================================="
echo ""
echo "📂 Compartilhamentos montados em:"
for share in "${SHARES[@]}"; do
    echo "   $MOUNT_BASE/$share"
done
echo ""
echo "🔧 Agora cadastre as variáveis no sistema:"
echo "   BUILD_DIR_PRD    = $MOUNT_BASE/builds"
echo "   FONTES_DIR_PRD   = $MOUNT_BASE/fontes"
echo "   PATCHES_DIR_PRD  = $MOUNT_BASE/patches"
echo "   INCLUDE_DIR_PRD  = $MOUNT_BASE/includes"
echo "   LOG_DIR_PRD      = $MOUNT_BASE/logs"
echo ""
echo "🌐 Acesse: http://192.168.15.14:5000"
echo ""