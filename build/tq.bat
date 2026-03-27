@echo off
setlocal

echo --------------------------------------------------------------------------
echo ATENCAO: Toda vez que esse script for executado, a pasta destino do RPO 
echo sempre sera criada pois ele busca a data e hora atual do sistema para 
echo nomear a pasta e busca a pasta atual do RPO para substituicao nos appserver.ini
echo Execute com precisao e cuidado!
echo --------------------------------------------------------------------------

:: Define a pasta que você quer analisar.
:: Altere o caminho abaixo para o seu diretório alvo onde se encontra a pasta do RPO
:: que será substituida na TQ.
set "PASTA_ALVO=D:\TotvsHML\Microsiga\Protheus\apo\hml"

:: Declara uma variável para armazenar o nome do diretório mais recente.
set "ORIGEM="

:: O comando 'dir' lista os diretórios (/AD) em formato simples (/b) e ordenados por data (/OD).
:: O laço 'for' processa cada linha da saída. A cada iteração, ele define a variável,
:: então, ao final, a variável terá o valor da última linha (o mais recente).
echo "Procurando o diretorio mais recente em: %PASTA_ALVO%"
for /f "delims=" %%p in ('dir "%PASTA_ALVO%"\202* /AD /b /OD') do (
    set "ORIGEM=%%p"
)

:: Chama o PowerShell para obter a data e hora já no formato exato que queremos.
:: Get-Date -Format 'yyyyMMdd_HHmm' é o comando do PowerShell para formatação.
:: O laço FOR /F captura a saída desse comando e a armazena na variável DESTINO.
FOR /F "usebackq" %%A IN (`powershell -NoProfile -Command "Get-Date -Format 'yyyyMMdd_HHmm'"`) DO (
    SET "DESTINO=%%A"
)

:: Mostra em tela as pastas que serão atualizadas e confirma o processamento.
echo -------------------------------------------
echo Pasta de ORIGEM %ORIGEM%
echo -------------------------------------------
echo -------------------------------------------
echo Pasta de DESTINO %DESTINO%
echo -------------------------------------------
echo -------------------------------------------
echo CONFIRMA PROCESSAMENTO? (CTRL + C CANCELA)
echo -------------------------------------------

pause

echo REALIZANDO COPIA DO RPO COMPILACAO PARA SERVIDORES PROTHEUS...
:: Copia RPOs usando robocopy
robocopy D:\TotvsHML\Microsiga\Protheus\apo\cmp D:\TotvsHML\Microsiga\Protheus\apo\hml\%DESTINO% tttm120.rpo mgfcustom.rpo

echo REALIZANDO TQ...
:: Usando o aplicativo fart.exe (https://github.com/lionello/fart-it) que 
:: Substitui a string final das chaves do RPOCustom e SourcePath (pasta do RPO)
:: nas pastas onde se encontram os arquivos .ini do appserver
fart -r D:\TotvsHML\Microsiga\Protheus\bin\appserver*.ini %ORIGEM% %DESTINO%  

echo PROCESSO CONCLUIDO!

pause