# NOVO ARQUIVO: ./src/services/tools.py

from src.models import db, Cliente, Produto, Mensagem, Usuario
from werkzeug.security import generate_password_hash
from datetime import datetime

# =========================================================
# FUNÇÕES DE AÇÃO PARA O GEMINI USAR (FUNCTION CALLING)
# =========================================================

def adicionar_cliente(nome: str, telefone: str, tem_suporte: bool) -> str:
    """
    Cadastra um novo cliente na base de dados.
    Args:
        nome (str): Nome do cliente.
        telefone (str): Número de telefone único do cliente (chave primária).
        tem_suporte (bool): Indica se o cliente tem um plano de suporte ativo.
    Returns:
        str: Uma mensagem de confirmação ou erro.
    """
    with db.session.begin(): # Garante que a sessão é aberta e fechada corretamente
        if Cliente.query.filter_by(telefone=telefone).first():
            return f"❌ Erro: Cliente com telefone {telefone} já existe."
            
        novo_cliente = Cliente(
            telefone=telefone, 
            nome=nome, 
            modo='bot',
            tem_suporte=tem_suporte
        )
        db.session.add(novo_cliente)
        db.session.commit()
    return f"✅ Cliente {nome} cadastrado com sucesso!"

def buscar_informacoes_cliente(termo_busca: str) -> dict:
    """
    Busca um cliente pelo nome ou telefone e retorna suas informações e histórico de conversa.
    Args:
        termo_busca (str): Nome ou telefone (completo ou parcial) do cliente.
    Returns:
        dict: Dados do cliente e resumo das últimas 5 mensagens, ou erro.
    """
    # Tenta buscar por nome ou telefone
    cliente = Cliente.query.filter(
        (Cliente.nome.ilike(f'%{termo_busca}%')) | 
        (Cliente.telefone.ilike(f'%{termo_busca}%'))
    ).first()
    
    if not cliente:
        return {"status": "erro", "mensagem": f"Cliente '{termo_busca}' não encontrado."}
        
    # Puxa o histórico (máximo 5 mensagens)
    historico = Mensagem.query.filter_by(cliente_id=cliente.id) \
                            .order_by(Mensagem.timestamp.desc()) \
                            .limit(5).all()
    
    mensagens_formatadas = []
    for msg in historico:
        # A API do Gemini precisa da role 'model' ou 'user'
        role_map = {'user': 'Cliente', 'model': 'Bot', 'human': 'Atendente'}
        mensagens_formatadas.append(f"[{role_map[msg.role]} às {msg.timestamp.strftime('%H:%M')}]: {msg.conteudo}")

    return {
        "status": "sucesso",
        "nome": cliente.nome,
        "telefone": cliente.telefone,
        "modo_chat": cliente.modo,
        "suporte_ativo": "Sim" if cliente.tem_suporte else "Não",
        "data_cadastro": cliente.created_at.strftime('%d/%m/%Y'),
        "ultimas_mensagens": mensagens_formatadas
    }

def listar_produtos_ativos() -> dict:
    """
    Retorna o catálogo completo de produtos ativos.
    Returns:
        dict: Lista de produtos com nome, descrição e preço.
    """
    produtos = Produto.query.filter_by(ativo=True).all()
    if not produtos:
        return {"status": "alerta", "mensagem": "Nenhum produto ativo encontrado no catálogo."}
        
    lista_produtos = []
    for p in produtos:
        lista_produtos.append({
            "nome": p.nome,
            "preco": p.preco,
            "descricao_resumo": p.descricao[:100] + "..." # Resumo para não poluir
        })
        
    return {"status": "sucesso", "total": len(produtos), "produtos": lista_produtos}

TOOLS_MAP = {
    "adicionar_cliente": adicionar_cliente,
    "buscar_informacoes_cliente": buscar_informacoes_cliente,
    "listar_produtos_ativos": listar_produtos_ativos
}

# =========================================================
# Mapeamento de Permissões (TOOLS_PERMISSIONS) - Onde fica a regra
# =========================================================
TOOLS_PERMISSIONS = {
    # Adicionar/Deletar é só para o Admin
    "adicionar_cliente": ["admin"], 
    
    # Buscar é permitido para todos
    "buscar_informacoes_cliente": ["admin", "atendente"],
    
    # Listar produtos é permitido para todos
    "listar_produtos_ativos": ["admin", "atendente"]
}