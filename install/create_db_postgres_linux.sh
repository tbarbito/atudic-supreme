# Atualizar repositórios
sudo apt update

# Instalar PostgreSQL
sudo apt install postgresql postgresql-contrib -y

# Verificar status
sudo systemctl status postgresql

# Criar usuário e banco
sudo -u postgres psql -c "CREATE USER atudic WITH PASSWORD 'atudic';"
sudo -u postgres psql -c "CREATE DATABASE atudic_devops OWNER atudic;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE atudic_devops TO atudic;"

# Instalar driver Python
pip install psycopg2-binary python-dotenv