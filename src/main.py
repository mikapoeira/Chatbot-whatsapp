import os
from functools import wraps
from datetime import datetime
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
import traceback # <--- ADICIONE ISSO AQUI
import sys

# Imports locais (Garanta que src.models e src.services existem)
from src.models import db, Cliente, Mensagem, Produto, Usuario, BotConfig
from src.services.gemini_service import (
    configurar_gemini, 
    iniciar_modelo, 
    gerar_prompt_dinamico, 
    processar_assistente_prompt
)

# CUSTOS DE TOKENS
COST_MESSAGE = 5  
COST_SESSION = 9  

app = Flask(__name__)

# --- CONFIGURAÇÕES ---
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.getenv('ADMIN_SECRET_TOKEN', 'dev_secret_key')

db.init_app(app)

# Configura Gemini ao iniciar
try:
    configurar_gemini()
except Exception as e:
    print(f"⚠️ Aviso: Falha ao configurar Gemini na inicialização: {e}")

# ==========================================
# FUNÇÕES AUXILIARES (TOKENS & AUTH)
# ==========================================

def verificar_e_consumir_token(quantidade=1):
    """Verifica e consome tokens do saldo global."""
    try:
        config = BotConfig.query.first()
        if not config:
            return False
        
        if config.saldo_tokens is None:
            config.saldo_tokens = 0
            db.session.commit()
            return False

        if config.saldo_tokens < quantidade:
            print(f"⚠️ SALDO INSUFICIENTE: Tem {config.saldo_tokens}, precisa de {quantidade}.")
            return False

        config.saldo_tokens -= quantidade
        db.session.commit()
        return True
    except Exception as e:
        print(f"❌ Erro ao verificar tokens: {e}")
        db.session.rollback()
        return False

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session or not session['admin_logged_in']:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session or not session['admin_logged_in']:
            return redirect(url_for('login'))
        if session.get('user_role') != 'admin':
            flash('Acesso negado. Apenas administradores.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# ==========================================
# ROTAS DE VISUALIZAÇÃO (HTML)
# ==========================================

@app.route('/', endpoint='dashboard')
@login_required
def index():
    try:
        total_clientes = db.session.query(Cliente).count()
        total_msgs = db.session.query(Mensagem).count()
        total_produtos = db.session.query(Produto).count()
        
        config = BotConfig.query.first()
        saldo_tokens = config.saldo_tokens if config and config.saldo_tokens is not None else 0
    except:
        total_clientes = total_msgs = total_produtos = saldo_tokens = 0
    
    return render_template('index.html', 
                           total_clientes=total_clientes, 
                           total_msgs=total_msgs, 
                           total_produtos=total_produtos,
                           saldo_tokens=saldo_tokens)

@app.route('/chats', endpoint='conversas')
@login_required
def chats_view():
    # Busca clientes que possuem mensagens, ordenados por atividade recente
    clientes_ids = db.session.query(Mensagem.cliente_id).distinct().all()
    ids_lista = [c[0] for c in clientes_ids]
    
    clientes = Cliente.query.filter(Cliente.id.in_(ids_lista)).order_by(Cliente.id.desc()).all()
    return render_template('chats.html', clientes=clientes)

@app.route('/products', endpoint='produtos')
@login_required
def products_view():
    produtos = Produto.query.all()
    return render_template('products.html', produtos=produtos)

@app.route('/settings', endpoint='configuracoes', methods=['GET', 'POST'])
@admin_required
def settings_view():
    config = BotConfig.query.first()
    usuarios = Usuario.query.all()
    
    if request.method == 'POST':
        if not config:
            config = BotConfig(nome_bot="Bot", personalidade="Assistente", saldo_tokens=0)
            db.session.add(config)
            
        config.nome_bot = request.form.get('nome_bot')
        config.personalidade = request.form.get('personalidade')
        db.session.commit()
        flash('Configurações atualizadas!')
        return redirect(url_for('configuracoes'))

    return render_template('settings.html', config=config, usuarios=usuarios)

@app.route('/clientes', endpoint='list_clientes')
@login_required 
def list_clientes():
    todos_clientes = Cliente.query.all()
    user_role = session.get('user_role', 'atendente') 
    return render_template('clientes.html', clientes=todos_clientes, user_role=user_role)

@app.route('/assistente_pessoal', endpoint='assistente_pessoal')
@login_required
def assistente_pessoal_view():
    return render_template('assistente_pessoal.html')

# ==========================================
# ROTAS DE AÇÃO (LOGIN/USERS/CLIENTES)
# ==========================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario_form = request.form.get('username')
        senha_form = request.form.get('password')
        user_db = Usuario.query.filter_by(username=usuario_form).first()
        
        if user_db and check_password_hash(user_db.password_hash, senha_form):
            session['admin_logged_in'] = True
            session['user_role'] = user_db.role 
            session['user_id'] = user_db.id # Útil para logs
            return redirect(url_for('dashboard'))
        else:
            flash('Login inválido.', 'error')
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout', endpoint='logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/settings/new_user', methods=['POST'])
@admin_required
def create_user():
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role')
    
    if Usuario.query.filter_by(username=username).first():
        flash('Usuário já existe.', 'error')
    else:
        hashed = generate_password_hash(password)
        novo_user = Usuario(username=username, password_hash=hashed, role=role)
        db.session.add(novo_user)
        db.session.commit()
        flash(f'Usuário {username} criado!', 'success')
    return redirect(url_for('configuracoes'))

@app.route('/settings/delete_user/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    if user_id == session.get('user_id'):
        flash('Não pode excluir a si mesmo.', 'error')
    else:
        Usuario.query.filter_by(id=user_id).delete()
        db.session.commit()
        flash('Usuário excluído.', 'success')
    return redirect(url_for('configuracoes'))

@app.route('/clientes/create', methods=['POST'])
@admin_required
def create_cliente():
    # CORREÇÃO: Usando os campos do modelo unificado (telefone/nome)
    telefone = request.form.get('numero_cliente') # No HTML ainda chama numero_cliente
    nome = request.form.get('nome_cliente')
    tem_suporte = 'suporte' in request.form 
    
    if not telefone or not nome:
        flash('Dados incompletos.', 'error')
    else:
        novo = Cliente(telefone=telefone, nome=nome, tem_suporte=tem_suporte, modo='bot')
        db.session.add(novo)
        db.session.commit()
        flash(f'Cliente {nome} criado!', 'success')
    return redirect(url_for('list_clientes'))

# ==========================================
# APIS (JSON)
# ==========================================

@app.route('/api/chat/<int:cliente_id>')
@login_required
def api_get_chat(cliente_id):
    try:
        msgs = Mensagem.query.filter_by(cliente_id=cliente_id).order_by(Mensagem.timestamp).all()
        data = []
        for m in msgs:
            # Formata role
            r = m.role.lower()
            role_fmt = 'bot' if r in ['model','bot'] else ('human' if r in ['human','atendente'] else 'user')
            
            # Formata hora
            hora = m.timestamp.strftime('%H:%M') if m.timestamp else '--:--'
            
            data.append({'role': role_fmt, 'conteudo': m.conteudo, 'time': hora})
        return jsonify(data)
    except Exception as e:
        print(f"Erro API Chat: {e}")
        return jsonify([]), 500

@app.route('/api/send_human', methods=['POST'])
@login_required
def api_send_human():
    data = request.json
    cliente = Cliente.query.get_or_404(data.get('cliente_id'))
    
    if not verificar_e_consumir_token(COST_MESSAGE):
        return jsonify({'error': 'Sem saldo'}), 402

    # Envio Twilio
    try:
        sid = os.getenv('TWILIO_ACCOUNT_SID')
        token = os.getenv('TWILIO_AUTH_TOKEN')
        from_ = os.getenv('TWILIO_PHONE_NUMBER')
        if sid and token:
            Client(sid, token).messages.create(body=data.get('texto'), from_=from_, to=cliente.telefone)
    except Exception as e:
        print(f"Erro Twilio: {e}")
        # Retorna erro mas salva no banco? Decisão de negócio.
        return jsonify({'error': 'Falha no envio'}), 500

    msg = Mensagem(cliente_id=cliente.id, role='human', conteudo=data.get('texto'))
    db.session.add(msg)
    cliente.modo = 'humano'
    db.session.commit()
    return jsonify({'status': 'ok'})

@app.route('/api/toggle_mode/<int:cliente_id>', methods=['POST'])
@login_required
def api_toggle_mode(cliente_id):
    c = Cliente.query.get_or_404(cliente_id)
    c.modo = request.json.get('modo')
    db.session.commit()
    return jsonify({'status': 'ok'})

@app.route('/api/assistente_pessoal', methods=['POST'])
@login_required
def api_assistente_pessoal():
    user_role = session.get('user_role', 'atendente')
    prompt = request.json.get('prompt', '').strip()
    
    if not prompt: return jsonify({'resposta': 'Digite algo.'})
    
    try:
        # Chama serviço Gemini com tools
        resp = processar_assistente_prompt(prompt, user_role)
        return jsonify({'resposta': resp})
    except Exception as e:
        print(f"Erro Assistente: {e}")
        return jsonify({'resposta': 'Erro interno.'}), 500

@app.route('/api/sync/produtos', methods=['POST'])
def sync_produtos():
    # Rota protegida por token no header (idealmente)
    try:
        Produto.query.delete()
        for item in request.json:
            p = Produto(nome=item.get('nome'), descricao=item.get('descricao'), preco=str(item.get('preco')))
            db.session.add(p)
        db.session.commit()
        return jsonify({'status': 'ok'})
    except:
        return jsonify({'error': 'erro'}), 500

# ==========================================
# WEBHOOK WHATSAPP (A PÉROLA)
# ==========================================
# --- SUBSTITUA A FUNÇÃO whatsapp_reply INTEIRA POR ISSO ---
@app.route('/whatsapp', methods=['POST'])
def whatsapp_reply():
    print("\n" + "="*50, flush=True)
    print(">>> [INIT] WEBHOOK (MODO ENVIO ATIVO)", flush=True)
    
    # 1. Captura e Setup
    remetente = request.values.get('From', '')
    texto = request.values.get('Body', '').strip()
    resp_xml_vazio = MessagingResponse() # Vamos retornar vazio pro webhook não reclamar

    if not texto:
        return Response(str(resp_xml_vazio), content_type='application/xml')

    # 2. Banco e Cliente
    try:
        cliente = Cliente.query.filter_by(telefone=remetente).first()
        if not cliente:
            print(f">>> Novo cliente: {remetente}")
            cliente = Cliente(telefone=remetente, nome="Novo Lead", modo='bot')
            db.session.add(cliente)
            db.session.commit()

        # Salva msg user
        msg_user = Mensagem(cliente_id=cliente.id, role='user', conteudo=texto)
        db.session.add(msg_user)
        db.session.commit()
    except Exception as e:
        print(f"!!! [ERRO DB] {e}")
        return Response(str(resp_xml_vazio), content_type='application/xml')

    # 3. Verifica Modo/Tokens
    if cliente.modo == 'humano' or not verificar_e_consumir_token(COST_MESSAGE):
        print(">>> Bot pausado (Humano ou Sem Tokens)")
        return Response(str(resp_xml_vazio), content_type='application/xml')

    # 4. GERAÇÃO DA IA (Igual antes)
    resposta_ia = ""
    try:
        msgs = Mensagem.query.filter_by(cliente_id=cliente.id).order_by(Mensagem.timestamp).limit(20).all()
        history = [{"role": "user" if m.role=="user" else "model", "parts": [m.conteudo]} for m in msgs]
        
        print(">>> Chamando Gemini...", flush=True)
        model = iniciar_modelo(gerar_prompt_dinamico())
        chat = model.start_chat(history=history)
        resposta_ia = chat.send_message(texto).text
        print(f">>> Gemini Respondeu: {resposta_ia[:30]}...")

    except Exception as e:
        print(f"!!! [ERRO IA] {e}")
        resposta_ia = "Desculpe, tive um erro técnico rápido."

    # 5. O PULO DO GATO: ENVIO ATIVO VIA API (Aqui a gente pega o erro!)
    if resposta_ia:
        # Salva no DB antes
        try:
            msg_bot = Mensagem(cliente_id=cliente.id, role='model', conteudo=resposta_ia)
            db.session.add(msg_bot)
            db.session.commit()
        except:
            pass # Segue o jogo

        # ENVIA DIRETO PRO TWILIO (Sem depender do retorno do Webhook)
        try:
            account_sid = os.getenv('TWILIO_ACCOUNT_SID')
            auth_token = os.getenv('TWILIO_AUTH_TOKEN')
            # O numero do .env TEM QUE TER 'whatsapp:'
            from_number = os.getenv('TWILIO_PHONE_NUMBER') 

            print(f">>> [ENVIANDO] De: {from_number} Para: {remetente}", flush=True)
            
            client = Client(account_sid, auth_token)
            message = client.messages.create(
                body=resposta_ia,
                from_=from_number,
                to=remetente
            )
            print(f">>> [SUCESSO] Mensagem enviada! SID: {message.sid}", flush=True)
            
        except Exception as e:
            # AQUI VAI APARECER O ERRO REAL NO SEU TERMINAL
            print(f"!!! [ERRO TWILIO API] O motivo do silencio é: {e}", flush=True)

    # Retorna XML vazio só pra fechar a conexão HTTP com 200 OK
    return Response(str(resp_xml_vazio), content_type='application/xml')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)