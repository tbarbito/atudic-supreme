# 🚀 ATURPO DEVOPS - Guia de Instalação

## 📋 Índice

- [Pré-requisitos](#pré-requisitos)
- [Instalação Linux](#instalação-linux)
- [Instalação Windows](#instalação-windows)
- [Pós-Instalação](#pós-instalação)
- [Gerenciamento do Serviço](#gerenciamento-do-serviço)
- [Desinstalação](#desinstalação)
- [Troubleshooting](#troubleshooting)

---

## 🔧 Pré-requisitos

### Linux (Ubuntu/Debian/CentOS/RHEL)

- **Sistema Operacional**: Ubuntu 20.04+, Debian 11+, CentOS 8+, RHEL 8+
- **Acesso**: Usuário com privilégios sudo
- **Conexão**: Internet (para download de dependências)

### Windows

- **Sistema Operacional**: Windows 10/11 ou Windows Server 2016+
- **Python**: 3.9 ou superior ([Download](https://www.python.org/downloads/))
- **PostgreSQL**: 13 ou superior ([Download](https://www.postgresql.org/download/windows/))
- **Acesso**: Conta com privilégios de Administrador

---

## 🐧 Instalação Linux

### Passo 1: Download dos Arquivos

Coloque os seguintes arquivos no mesmo diretório:
```
aturpo-devops/
├── app.py
├── index.html
├── integration.js
├── api-client.js
└── install_linux.sh
```

### Passo 2: Dar Permissão de Execução

```bash
chmod +x install_linux.sh
```

### Passo 3: Executar o Instalador

```bash
sudo ./install_linux.sh
```

### Passo 4: Seguir as Instruções

O instalador irá:

1. ✅ Detectar a distribuição Linux
2. ✅ Instalar Python 3, PostgreSQL, Git, Nginx
3. ✅ Criar usuário do sistema `aturpo`
4. ✅ Configurar ambiente virtual Python
5. ✅ Criar banco de dados PostgreSQL
6. ✅ Instalar como serviço systemd
7. ✅ (Opcional) Configurar Nginx como reverse proxy
8. ✅ (Opcional) Configurar firewall

### Passo 5: Acessar o Sistema

Após a instalação, acesse:
```
http://localhost:5000
ou
http://SEU_IP:5000
```

**Credenciais padrão:**
- Usuário: `admin`
- Senha: `admin123`

⚠️ **IMPORTANTE**: Altere a senha padrão no primeiro acesso!

---

## 🪟 Instalação Windows

### Passo 1: Pré-requisitos

#### Instalar Python

1. Acesse: https://www.python.org/downloads/
2. Baixe Python 3.11 ou superior
3. Durante a instalação, **MARQUE** a opção:
   ☑️ **"Add Python to PATH"**

#### Instalar PostgreSQL

1. Acesse: https://www.postgresql.org/download/windows/
2. Baixe PostgreSQL 13 ou superior
3. Durante a instalação, anote a senha do usuário `postgres`

### Passo 2: Download dos Arquivos

Coloque os seguintes arquivos no mesmo diretório:
```
aturpo-devops\
├── app.py
├── index.html
├── integration.js
├── api-client.js
└── install_windows.ps1
```

### Passo 3: Executar o Instalador

1. Clique com botão direito no arquivo `install_windows.ps1`
2. Selecione **"Executar com PowerShell"**
3. Se aparecer aviso de segurança, selecione **"Executar mesmo assim"**

**OU** abra PowerShell como Administrador e execute:

```powershell
cd "C:\caminho\para\aturpo-devops"
.\install_windows.ps1
```

### Passo 4: Seguir as Instruções

O instalador irá:

1. ✅ Verificar Python e PostgreSQL
2. ✅ Baixar e instalar NSSM (Service Manager)
3. ✅ Criar diretório `C:\AturpoDevOps`
4. ✅ Configurar ambiente virtual Python
5. ✅ Configurar banco de dados PostgreSQL
6. ✅ Instalar como serviço Windows
7. ✅ (Opcional) Configurar Windows Firewall

### Passo 5: Acessar o Sistema

Após a instalação, acesse:
```
http://localhost:5000
```

**Credenciais padrão:**
- Usuário: `admin`
- Senha: `admin123`

⚠️ **IMPORTANTE**: Altere a senha padrão no primeiro acesso!

---

## 🎯 Pós-Instalação

### Configurações Importantes

#### 1. Alterar Senha Padrão

1. Faça login com `admin` / `admin123`
2. Clique no ícone de usuário no canto superior direito
3. Selecione **"Alterar Senha"**
4. Digite a nova senha

#### 2. Configurar GitHub (Opcional)

Se você vai usar integração com GitHub:

1. Acesse **Configurações** → **GitHub**
2. Gere um Personal Access Token no GitHub
3. Configure usuário e token

#### 3. Criar Ambientes

1. Acesse **Ambientes**
2. Crie ambientes (DEV, HML, PRD)
3. Configure variáveis de ambiente específicas

#### 4. Configurar Variáveis de Servidor

1. Acesse **Variáveis de Servidor**
2. Adicione as variáveis necessárias para seus scripts

---

## 🔄 Gerenciamento do Serviço

### Linux

#### Ver Status
```bash
sudo systemctl status aturpo-devops
```

#### Parar Serviço
```bash
sudo systemctl stop aturpo-devops
```

#### Iniciar Serviço
```bash
sudo systemctl start aturpo-devops
```

#### Reiniciar Serviço
```bash
sudo systemctl restart aturpo-devops
```

#### Ver Logs em Tempo Real
```bash
sudo journalctl -u aturpo-devops -f
```

#### Desabilitar Inicialização Automática
```bash
sudo systemctl disable aturpo-devops
```

#### Habilitar Inicialização Automática
```bash
sudo systemctl enable aturpo-devops
```

### Windows

#### Ver Status
```powershell
Get-Service -Name AturpoDevOps
```

#### Parar Serviço
```powershell
Stop-Service -Name AturpoDevOps
```

#### Iniciar Serviço
```powershell
Start-Service -Name AturpoDevOps
```

#### Reiniciar Serviço
```powershell
Restart-Service -Name AturpoDevOps
```

#### Ver Logs
```powershell
Get-Content C:\AturpoDevOps\logs\*.log -Tail 50 -Wait
```

#### Gerenciar via Interface Gráfica

1. Pressione `Win + R`
2. Digite `services.msc`
3. Procure por **"ATURPO DevOps Dashboard"**

---

## 🗑️ Desinstalação

### Linux

```bash
sudo chmod +x uninstall_linux.sh
sudo ./uninstall_linux.sh
```

O desinstalador irá:
- ✅ Parar e remover o serviço
- ✅ Remover arquivos de `/opt/aturpo-devops`
- ✅ (Opcional) Remover usuário do sistema
- ✅ (Opcional) Remover banco de dados
- ✅ (Opcional) Remover configuração Nginx

### Windows

1. Clique com botão direito no arquivo `uninstall_windows.ps1`
2. Selecione **"Executar com PowerShell"**

**OU** execute como Administrador:

```powershell
.\uninstall_windows.ps1
```

O desinstalador irá:
- ✅ Parar e remover o serviço
- ✅ Remover arquivos de `C:\AturpoDevOps`
- ✅ (Opcional) Remover banco de dados
- ✅ (Opcional) Remover regra de firewall

---

## 🔍 Troubleshooting

### Linux

#### Erro: "Porta 5000 já está em uso"

```bash
# Verificar processo usando porta 5000
sudo lsof -i :5000

# Matar processo se necessário
sudo kill -9 <PID>
```

#### Erro: "Permissão negada ao acessar banco"

```bash
# Verificar se PostgreSQL está rodando
sudo systemctl status postgresql

# Verificar permissões do usuário
sudo -u postgres psql -c "\du"
```

#### Logs não aparecem

```bash
# Verificar permissões do diretório de logs
ls -la /opt/aturpo-devops/logs/

# Ajustar permissões se necessário
sudo chown -R aturpo:aturpo /opt/aturpo-devops/logs/
```

### Windows

#### Erro: "NSSM não encontrado"

O instalador baixa automaticamente o NSSM. Se houver erro:

1. Baixe manualmente: https://nssm.cc/download
2. Extraia `nssm.exe` para `C:\Windows\System32\`

#### Erro: "Python não encontrado"

1. Verifique se Python está no PATH:
   ```powershell
   python --version
   ```
2. Se não estiver, reinstale Python marcando "Add to PATH"

#### Serviço não inicia

1. Verifique logs:
   ```powershell
   Get-Content C:\AturpoDevOps\logs\service-error.log
   ```

2. Teste manualmente:
   ```powershell
   cd C:\AturpoDevOps
   .\venv\Scripts\activate
   python app.py
   ```

#### Erro de conexão com PostgreSQL

1. Verifique se PostgreSQL está rodando:
   ```powershell
   Get-Service postgresql*
   ```

2. Teste conexão:
   ```powershell
   psql -U aturpo_user -d aturpo_devops -h localhost
   ```

3. Verifique arquivo `.env`:
   ```powershell
   Get-Content C:\AturpoDevOps\.env
   ```

---

## 📞 Suporte

Para mais informações ou suporte:

- 📧 Email: suporte@aturpo.com.br
- 📖 Documentação: [Link para documentação]
- 🐛 Issues: [Link para issues]

---

## 📝 Notas de Versão

### Versão 1.0.0

- ✅ Instalação automatizada Linux e Windows
- ✅ Instalação como serviço em ambos SO
- ✅ Configuração automática de PostgreSQL
- ✅ Scripts de desinstalação
- ✅ Suporte para múltiplas distribuições Linux
- ✅ Integração com Nginx (opcional)
- ✅ Configuração de firewall (opcional)

---

**Desenvolvido por ATURPO** | Versão 1.0.0