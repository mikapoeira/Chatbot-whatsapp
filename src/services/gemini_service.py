import google.generativeai as genai
import os
from src.models import Produto, BotConfig

def configurar_gemini():
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key: 
        raise ValueError("A chave GEMINI_API_KEY não foi encontrada no .env")
    genai.configure(api_key=api_key)

def gerar_prompt_dinamico():
    """
    Busca a configuração (personalidade) e os produtos no Banco de Dados
    e monta o System Instruction final.
    """
    # 1. Busca configurações (Prompt Base carregado do txt)
    config = BotConfig.query.first()
    
    # Fallback de segurança se o banco estiver vazio
    if not config:
        return "Você é um assistente virtual útil."

    # 2. Busca Produtos Ativos
    produtos = Produto.query.filter_by(ativo=True).all()
    if produtos:
        texto_produtos = "\n".join([f"- {p.nome}: {p.descricao} | Preço: {p.preco}" for p in produtos])
    else:
        texto_produtos = "Nenhum produto específico cadastrado no momento."

    # 3. MONTA O PROMPT FINAL
    # Aqui misturamos a personalidade (vinda do txt) com os produtos (vindos do banco)
    prompt_final = f"""
    ### INSTRUÇÕES DO SISTEMA ###
    Você é {config.nome_bot}, assistente da {config.nome_empresa}.
    
    {config.personalidade}

    --------------------
    ### CATÁLOGO DE PRODUTOS/SERVIÇOS ATUALIZADO ###
    Use a lista a seguir como referência se perguntado sobre itens específicos:
    {texto_produtos}
    """
    
    return prompt_final

def iniciar_modelo(prompt_sistema):
    # Inicializa o modelo com as instruções montadas acima
    return genai.GenerativeModel('gemini-2.0-flash-lite', system_instruction=prompt_sistema)