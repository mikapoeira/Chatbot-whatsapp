import os
from flask import Flask
from src.models import db, Produto, Cliente, Mensagem # Importa suas tabelas

app = Flask(__name__)

# Configura conexão com o Banco (Lê do docker-compose)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Inicializa o banco no App
db.init_app(app)

@app.route('/')
def home():
    return "O Bot Braga está vivo e conectado ao Banco!"

# Essa é a mágica: Cria as tabelas assim que roda
if __name__ == '__main__':
    with app.app_context():
        try:
            db.create_all() # <--- ISSO CRIA AS TABELAS NO POSTGRES
            print("Sucesso! Tabelas criadas (ou já existiam).")
        except Exception as e:
            print(f"Erro ao conectar no banco: {e}")
    
    # Roda o servidor
    app.run(host='0.0.0.0', port=5000, debug=True)