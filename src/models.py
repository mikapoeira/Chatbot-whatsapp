from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
import time

# Inicializamos o objeto db aqui (sem import circular)
db = SQLAlchemy()

# ----------------------------------------------------------------
# TABELA 1: CONFIGURAÇÃO DO BOT (Prompt e Personalidade)
# ----------------------------------------------------------------
class BotConfig(db.Model):
    __tablename__ = 'bot_configs'

    id = db.Column(db.Integer, primary_key=True)
    nome_bot = db.Column(db.String(50), default="Assistente")
    nome_empresa = db.Column(db.String(100), default="Minha Empresa")
    
    # Aqui fica o texto gigante que veio do system_prompt.txt
    personalidade = db.Column(db.Text, nullable=False)
    
    # Campo extra opcional se quiser separar regras de negócio
    regras_negocio = db.Column(db.Text, default="") 

# ----------------------------------------------------------------
# TABELA 2: CLIENTES (Quem manda mensagem)
# ----------------------------------------------------------------
class Cliente(db.Model):
    __tablename__ = 'clientes'

    id = db.Column(db.Integer, primary_key=True)
    telefone = db.Column(db.String(50), unique=True, nullable=False)
    nome = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relacionamento para pegar as mensagens desse cliente
    mensagens = db.relationship('Mensagem', backref='cliente', lazy=True)

# ----------------------------------------------------------------
# TABELA 3: MENSAGENS (Histórico)
# ----------------------------------------------------------------
class Mensagem(db.Model):
    __tablename__ = 'mensagens'

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False) # 'user' ou 'model'
    conteudo = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# ----------------------------------------------------------------
# TABELA 4: PRODUTOS (Catálogo)
# ----------------------------------------------------------------
class Produto(db.Model):
    __tablename__ = 'produtos'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text, nullable=False)
    preco = db.Column(db.String(50), nullable=True)
    ativo = db.Column(db.Boolean, default=True)