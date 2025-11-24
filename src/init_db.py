import os
from flask import Flask
from src.models import db, BotConfig
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
            db.create_all()
            
            # Verifica se já existe configuração no banco
            if not BotConfig.query.first():
                print("⚙️ Banco vazio. Carregando configurações do .env e arquivo txt...")
                
                # 1. Pega variáveis curtas do .env
                nome_bot_env = os.getenv('CHATBOT_NAME', 'Assistente')
                empresa_env = os.getenv('COMPANY_NAME', 'Minha Empresa')
                
                # 2. Pega texto longo do arquivo .txt
                texto_prompt = carregar_texto_prompt()
                
                # 3. Salva no Banco
                config_inicial = BotConfig(
                    nome_bot=nome_bot_env,
                    nome_empresa=empresa_env,
                    personalidade=texto_prompt,
                    regras_negocio="" # Se quiser, pode criar um segundo txt para regras
                )
                
                db.session.add(config_inicial)
                db.session.commit()
                print(f"✅ Configuração salva para: {nome_bot_env} da {empresa_env}")
            
            else:
                print("ℹ️ Configuração já existe no banco. Pulando inicialização.")

        except Exception as e:
            print(f"❌ Erro crítico no init_db: {e}")

if __name__ == "__main__":
    init_database()