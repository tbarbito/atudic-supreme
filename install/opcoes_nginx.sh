# Descobrir quem está na porta 80
echo "🔍 Verificando porta 80..."
sudo lsof -i :80

echo ""
echo "Escolha uma opção:"
echo "1) Parar Apache2 e usar Nginx na porta 80"
echo "2) Manter Apache2 e usar Nginx na porta 8000"
echo "3) Remover Nginx e usar apenas porta 5000"
read -p "Digite a opção (1/2/3): " opcao

case $opcao in
    1)
        echo "⏹️  Parando Apache2..."
        sudo systemctl stop apache2
        sudo systemctl disable apache2
        echo "🚀 Iniciando Nginx..."
        sudo systemctl start nginx
        sudo systemctl status nginx
        echo "✅ Acesse: http://atudic.com.br"
        ;;
    2)
        echo "🔧 Configurando Nginx na porta 8000..."
        sudo sed -i 's/listen 80;/listen 8000;/g' /etc/nginx/sites-available/atudic-devops
        sudo nginx -t
        sudo systemctl restart nginx
        sudo ufw allow 8000/tcp
        echo "✅ Acesse: http://atudic.com.br:8000"
        ;;
    3)
        echo "🗑️  Removendo Nginx..."
        sudo systemctl stop nginx
        sudo systemctl disable nginx
        echo "✅ Acesse: http://atudic.com.br:5000"
        ;;
esac