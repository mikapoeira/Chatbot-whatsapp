from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
import time

# AQUI ESTÁ O SEGREDO: Nós criamos o db aqui, não importamos.
db = SQLAlchemy()

# ----------------------------------------------------------------
# TABELA 1: CONFIGURAÇÕES DO BOT (Prompt Dinâmico)
# ----------------------------------------------------------------
class BotConfig(db.Model):
    __tablename__ = 'bot_configs'

    id = db.Column(db.Integer, primary_key=True)
    nome_bot = db.Column(db.String(50), default="Assistente")
    nome_empresa = db.Column(db.String(100), default="Minha Empresa")
    personalidade = db.Column(db.Text, default="Seja formal e educado.")
    regras_negocio = db.Column(db.Text, default="") 

# ----------------------------------------------------------------
# TABELA 2: CLIENTES
# ----------------------------------------------------------------
class Cliente(db.Model):
    __tablename__ = 'clientes'

    id = db.Column(db.Integer, primary_key=True)
    telefone = db.Column(db.String(50), unique=True, nullable=False)
    nome = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    mensagens = db.relationship('Mensagem', backref='cliente', lazy=True)

# ----------------------------------------------------------------
# TABELA 3: PRODUTOS
# ----------------------------------------------------------------
class Produto(db.Model):
    __tablename__ = 'produtos'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text, nullable=False)
    preco = db.Column(db.String(50), nullable=True)
    ativo = db.Column(db.Boolean, default=True)

# ----------------------------------------------------------------
# TABELA 4: SESSÃO/MENSAGENS
# ----------------------------------------------------------------
class SessaoChat(db.Model):
    # Tabela simplificada para guardar sessão em memória se preferir,
    # ou podemos usar a tabela de Mensagens para reconstruir o histórico.
    __tablename__ = 'sessoes'
    telefone = db.Column(db.String(50), primary_key=True)
    historico = db.Column(JSONB, default=list)
    last_seen = db.Column(db.Float, default=time.time)

class Mensagem(db.Model):
    __tablename__ = 'mensagens'

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    conteudo = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)