import google.generativeai as genai
import os
from src.models import Produto, BotConfig
# Importe as ferramentas e as permissões de tools do tools.py
from src.services.tools import TOOLS_MAP, TOOLS_PERMISSIONS 
from google.generativeai.types import Tool
import traceback

def configurar_gemini():
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key: 
        raise ValueError("A chave GEMINI_API_KEY não foi encontrada no .env")
    genai.configure(api_key=api_key)

def gerar_prompt_dinamico():
    config = BotConfig.query.first()
    if not config:
        return "Você é um assistente virtual útil."

    produtos = Produto.query.filter_by(ativo=True).all()
    if produtos:
        texto_produtos = "\n".join([f"- {p.nome}: {p.descricao} | Preço: {p.preco}" for p in produtos])
    else:
        texto_produtos = "Nenhum produto específico cadastrado no momento."

    prompt_final = f"""
    ### INSTRUÇÕES DO SISTEMA ###
    Você é {config.nome_bot}, assistente da {config.nome_empresa}.
    
    {config.personalidade}

    --------------------
    ### CATÁLOGO DE PRODUTOS/SERVIÇOS ATUALIZADO ###
    {texto_produtos}
    """
    return prompt_final

def iniciar_modelo(prompt_sistema):
    return genai.GenerativeModel('gemini-2.5-flash', system_instruction=prompt_sistema)

def processar_assistente_prompt(prompt_usuario: str, user_role: str) -> str:
    print(f"\n[DEBUG] --- Iniciando Assistente Pessoal ---")
    
    try:
        # 1. Filtro de Tools
        tools_disponiveis = []
        for tool_name, func in TOOLS_MAP.items():
            permissoes = TOOLS_PERMISSIONS.get(tool_name, [])
            if user_role in permissoes:
                tools_disponiveis.append(func)
        
        # 2. Instrução
        if not tools_disponiveis:
             system_instruction = f"Você é um assistente sem permissões (Role: {user_role})."
        else:
            system_instruction = f"""
            Você é o Assistente Admin (Role: {user_role}).
            Tools disponíveis: {[f.__name__ for f in tools_disponiveis]}.
            Responda direto.
            """

        # 3. Modelo
        model = genai.GenerativeModel('gemini-2.5-flash', system_instruction=system_instruction)
        chat = model.start_chat(history=[])
        
        # Envia msg
        if tools_disponiveis:
            response = chat.send_message(prompt_usuario, tools=tools_disponiveis)
        else:
            response = chat.send_message(prompt_usuario)

        # 4. Loop de Function Calling
        def contem_function_call(resp):
            for part in resp.parts:
                if part.function_call: return True
            return False

        while contem_function_call(response):
            for part in response.parts:
                if part.function_call:
                    fc = part.function_call
                    print(f"[DEBUG] Tool: {fc.name}")
                    
                    func = TOOLS_MAP.get(fc.name)
                    if func:
                        try:
                            args = dict(fc.args)
                            resultado = func(**args)
                        except Exception as e:
                            resultado = f"Erro na tool: {e}"
                    else:
                        resultado = "Tool não encontrada."

                    # Devolve pro modelo
                    response = chat.send_message(
                        genai.protos.Content(
                            parts=[genai.protos.Part(
                                function_response=genai.protos.FunctionResponse(
                                    name=fc.name,
                                    response={'result': resultado}
                                )
                            )]
                        )
                    )
        
        return response.text

    except Exception as e:
        print(f"❌ Erro Assistente: {e}")
        traceback.print_exc()
        return "Erro interno no processamento."