# =============================================================================
# Script PowerShell para gerenciar serviços remotamente em servidores Windows
# =============================================================================
# opção 1: Usando Invoke-Command para executar comandos remotamente
# Certifique-se de que o PowerShell Remoting esteja habilitado no servidor remoto.
# Execute: winrm quickconfig
# Precisa ter permissões de administrador na máquina de destino.
# =============================================================================
# Para parar o serviço
# =============================================================================
Invoke-Command -ComputerName "NOME_DO_SERVIDOR" -ScriptBlock { Stop-Service -Name "NomeDoServico" }

# Para iniciar o serviço
Invoke-Command -ComputerName "NOME_DO_SERVIDOR" -ScriptBlock { Start-Service -Name "NomeDoServico" }

# Para ver o status
Invoke-Command -ComputerName "NOME_DO_SERVIDOR" -ScriptBlock { Get-Service -Name "NomeDoServico" }

# =============================================================================
# opção 2: Usando Get-Service com o parâmetro -ComputerName
# =============================================================================
# Pega o serviço remotamente e "joga" para o comando Stop-Service
Get-Service -Name "NomeDoServico" -ComputerName "NOME_DO_SERVIDOR" | Stop-Service

# Pega o serviço remotamente e "joga" para o comando Start-Service
Get-Service -Name "NomeDoServico" -ComputerName "NOME_DO_SERVIDOR" | Start-Service

# Substitua "NomeDoServico" pelo nome real do seu serviço para forçar a parada do processo associado ao serviço
Get-CimInstance -ClassName Win32_Service -Filter "Name='NomeDoServico'" | Select-Object -ExpandProperty ProcessId | Stop-Process -Force