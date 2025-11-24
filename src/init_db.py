# Arquivo: src/init_db.py
from flask import Flask
from src.models import db, BotConfig
from src.main import app # Importa o app para pegar as configs

def init_database():
    print("🔄 Verificando Banco de Dados...")
    with app.app_context():
        try:
            # 1. Cria as tabelas se não existirem
            db.create_all()
            print("✅ Tabelas verificadas/criadas com sucesso.")

            # 2. Cria a configuração padrão se estiver vazio (Seed inicial)
            if not BotConfig.query.first():
                print("⚙️ Criando configuração padrão do Bot...")
                config_padrao = BotConfig(
                    nome_bot="Assistente",
                    nome_empresa="Minha Empresa",
                    personalidade="Seja prestativo.",
                    regras_negocio=""
                )
                db.session.add(config_padrao)
                db.session.commit()
                print("✅ Configuração padrão salva.")
            
        except Exception as e:
            print(f"❌ Erro ao inicializar banco: {e}")

if __name__ == "__main__":
    init_database()