from flask import Flask, request, jsonify
from src.models import db, Cliente, Mensagem, Produto
from src.services.gemini_service import configurar_gemini, iniciar_modelo, gerar_prompt_dinamico
from twilio.twiml.messaging_response import MessagingResponse
import os

app = Flask(__name__)

# Configuração do Banco
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Inicializa extensões
db.init_app(app)
configurar_gemini()

# --- ROTA DO WHATSAPP ---
@app.route('/whatsapp', methods=['POST'])
def whatsapp_reply():
    remetente = request.values.get('From', '') # Ex: whatsapp:+5511999999999
    msg_usuario = request.values.get('Body', '').strip()
    resp = MessagingResponse()

    if not msg_usuario:
        return str(resp)

    # 1. Identifica ou Cria o Cliente no Banco
    cliente = Cliente.query.filter_by(telefone=remetente).first()
    
    if not cliente:
        # Novo usuário
        cliente = Cliente(telefone=remetente, nome="Desconhecido")
        db.session.add(cliente)
        db.session.commit()
        
        # Opcional: Saudação inicial fixa antes da IA responder
        # resp.message("Olá! Bem-vindo.") 

    # 2. Salva a mensagem do usuário no histórico
    msg_db_user = Mensagem(cliente_id=cliente.id, role='user', conteudo=msg_usuario)
    db.session.add(msg_db_user)
    db.session.commit()

    try:
        # 3. Reconstrói o histórico para o Gemini (Contexto)
        # Pegamos as últimas 30 mensagens para ele lembrar da conversa
        historico_db = Mensagem.query.filter_by(cliente_id=cliente.id).order_by(Mensagem.timestamp).limit(30).all()
        
        history_gemini = []
        for h in historico_db:
            # Mapeia: 'user' -> 'user', 'model' -> 'model'
            history_gemini.append({"role": h.role, "parts": [h.conteudo]})

        # 4. Gera Prompt Fresquinho e Inicia Chat
        prompt_atual = gerar_prompt_dinamico()
        model = iniciar_modelo(prompt_atual)
        chat = model.start_chat(history=history_gemini)
        
        # 5. Envia para a IA
        response = chat.send_message(msg_usuario)
        texto_resposta = response.text

        # 6. Salva resposta da IA no Banco
        msg_db_bot = Mensagem(cliente_id=cliente.id, role='model', conteudo=texto_resposta)
        db.session.add(msg_db_bot)
        db.session.commit()

        # 7. Formata para o WhatsApp (Quebra linhas se necessário)
        paragrafos = [p.strip() for p in texto_resposta.split('\n') if p.strip()]
        for p in paragrafos:
            resp.message(p)

    except Exception as e:
        print(f"Erro Gemini: {e}")
        # Em caso de erro, não deixe o usuário no vácuo
        resp.message("Desculpe, estou processando muita informação. Pode repetir?")

    return str(resp)


# --- ROTA DE API (Para o n8n atualizar produtos) ---
@app.route('/api/sync/produtos', methods=['POST'])
def sync_produtos():
    # Verifica Token de Segurança
    token_recebido = request.headers.get('X-Admin-Token')
    if token_recebido != os.getenv('ADMIN_SECRET_TOKEN'):
        return jsonify({'error': 'Acesso negado'}), 403
    
    # Verifica Feature Flag (Se este cliente permite sync externo)
    if os.getenv('ENABLE_EXTERNAL_SYNC') != 'true':
         return jsonify({'error': 'Sync desativado neste ambiente'}), 400

    try:
        dados = request.json
        # Estratégia: Apaga tudo e recria (Simples e eficaz para catálogos pequenos)
        Produto.query.delete()
        
        novos_produtos = []
        for item in dados:
            p = Produto(
                nome=item.get('nome', 'Sem Nome'), 
                descricao=item.get('descricao', ''), 
                preco=str(item.get('preco', ''))
            )
            novos_produtos.append(p)
            
        db.session.add_all(novos_produtos)
        db.session.commit()
        return jsonify({'status': 'Sincronizado', 'items': len(novos_produtos)})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)