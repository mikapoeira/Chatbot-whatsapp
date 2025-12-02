import os
from flask import Flask
from werkzeug.security import generate_password_hash # <--- NOVA IMPORTAÇÃO
from src.models import db, BotConfig, Usuario # <--- ADICIONEI 'Usuario' AQUI
from src.main import app

def carregar_texto_prompt():
    """Lê o arquivo de texto externo para não sujar o código Python"""
    caminho_arquivo = os.path.join(os.getcwd(), 'system_prompt.txt')
    
    try:
        if os.path.exists(caminho_arquivo):
            with open(caminho_arquivo, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            print("⚠️ Arquivo 'system_prompt.txt' não encontrado. Usando genérico.")
            return "Você é um assistente virtual prestativo."
    except Exception as e:
        print(f"❌ Erro ao ler arquivo de prompt: {e}")
        return "Erro ao carregar personalidade."

def init_database():
    print("🔄 Verificando Banco de Dados...")
    with app.app_context():
        try:
            # Cria todas as tabelas (BotConfig, Cliente, Mensagem, Produto, USUARIO)
            db.create_all()
            
            # =========================================
            # 1. CONFIGURAÇÃO DO BOT (Prompt)
            # =========================================
            texto_prompt = carregar_texto_prompt()
            nome_bot = os.getenv('CHATBOT_NAME', 'Assistente')
            empresa = os.getenv('COMPANY_NAME', 'Empresa')

            config = BotConfig.query.first()
            
            if not config:
                print("⚙️ Criando configuração inicial do Bot...")
                config = BotConfig(
                    nome_bot=nome_bot,
                    nome_empresa=empresa,
                    personalidade=texto_prompt
                )
                db.session.add(config)
            else:
                print("♻️ Atualizando prompt existente...")
                config.nome_bot = nome_bot
                config.nome_empresa = empresa
                config.personalidade = texto_prompt
            
            db.session.commit()

            # =========================================
            # 2. CRIAÇÃO DO ADMIN COM SEGURANÇA (NOVO)
            # =========================================
            admin_user = os.getenv('ADMIN_USER', 'admin')
            
            # Verifica se já existe esse usuário no banco
            if not Usuario.query.filter_by(username=admin_user).first():
                print(f"👤 Criando Super Usuário '{admin_user}'...")
                
                # Pega a senha plana do .env
                senha_plana = os.getenv('ADMIN_SECRET_TOKEN', 'admin')
                
                # TRANSFORMA EM HASH (A mágica acontece aqui)
                senha_hash = generate_password_hash(senha_plana)
                
                novo_admin = Usuario(
                    username=admin_user, 
                    password_hash=senha_hash, # Salva o hash, nunca a senha real
                    role='admin'
                )
                
                db.session.add(novo_admin)
                db.session.commit()
                print("🔒 Admin criado com sucesso (Senha protegida por Hash)!")
            else:
                print("ℹ️ Usuário Admin já existe no banco.")
                
            print("✅ Tudo sincronizado!")

        except Exception as e:
            print(f"❌ Erro crítico no init_db: {e}")

if __name__ == "__main__":
    init_database()