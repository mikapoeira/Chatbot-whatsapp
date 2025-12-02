import os
from functools import wraps
from datetime import datetime
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, flash
# --- CORREÇÃO 1: Adicionei 'Usuario' aqui ---
from src.models import db, Cliente, Mensagem, Produto, Usuario, BotConfig 
# --- CORREÇÃO 2: Adicionei os módulos de hash ---
from werkzeug.security import generate_password_hash, check_password_hash 
from src.services.gemini_service import configurar_gemini, iniciar_modelo, gerar_prompt_dinamico
from twilio.twiml.messaging_response import MessagingResponse
# --- CORREÇÃO 3: Import global do Client do Twilio ---
from twilio.rest import Client 

app = Flask(__name__)

# --- CONFIGURAÇÕES ---
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.getenv('ADMIN_SECRET_TOKEN', 'dev_secret_key')

db.init_app(app)
configurar_gemini()

# --- DECORATOR DE AUTH ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ==========================================
# ROTAS DE VISUALIZAÇÃO (HTML)
# ==========================================

@app.route('/', endpoint='dashboard')
@login_required
def index():
    return render_template('index.html')

@app.route('/chats', endpoint='conversas')
@login_required
def chats_view():
    clientes = Cliente.query.order_by(Cliente.created_at.desc()).all()
    return render_template('chats.html', clientes=clientes)

@app.route('/products', endpoint='produtos')
@login_required
def products_view():
    produtos = Produto.query.all()
    return render_template('products.html', produtos=produtos)

@app.route('/settings', endpoint='configuracoes', methods=['GET', 'POST']) # <--- Aceita POST agora
@login_required
def settings_view():
    # Busca a config (sempre existe pois o init_db cria)
    config = BotConfig.query.first()

    if request.method == 'POST':
        # Atualiza os dados vindos do formulário
        novo_nome = request.form.get('nome_bot')
        nova_personalidade = request.form.get('personalidade')
        
        if config:
            config.nome_bot = novo_nome
            config.personalidade = nova_personalidade
            db.session.commit()
            flash('Configurações atualizadas com sucesso!')
        
        return redirect(url_for('configuracoes'))

    # Renderiza passando o objeto 'config' pro HTML ler
    return render_template('settings.html', config=config)

# ==========================================
# ROTAS DA API
# ==========================================

@app.route('/api/chat/<int:cliente_id>')
@login_required
def api_get_chat(cliente_id):
    msgs = Mensagem.query.filter_by(cliente_id=cliente_id).order_by(Mensagem.timestamp).all()
    data = []
    for m in msgs:
        role_fmt = 'human' if m.role == 'human' else m.role
        data.append({
            'role': role_fmt,
            'conteudo': m.conteudo,
            'time': m.timestamp.strftime('%H:%M')
        })
    return jsonify(data)

@app.route('/api/toggle_mode/<int:cliente_id>', methods=['POST'])
@login_required
def api_toggle_mode(cliente_id):
    data = request.json
    novo_modo = data.get('modo')
    cliente = Cliente.query.get_or_404(cliente_id)
    cliente.modo = novo_modo
    db.session.commit()
    return jsonify({'status': 'ok', 'novo_modo': cliente.modo})

@app.route('/api/send_human', methods=['POST'])
@login_required
def api_send_human():
    data = request.json
    cliente_id = data.get('cliente_id')
    texto = data.get('texto')
    
    cliente = Cliente.query.get_or_404(cliente_id)
    
    # --- CORREÇÃO 4: Envio Real via Twilio ---
    try:
        account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        from_number = os.getenv('TWILIO_PHONE_NUMBER')

        if account_sid and auth_token and from_number:
            client = Client(account_sid, auth_token)
            client.messages.create(
                body=texto, 
                from_=from_number, 
                to=cliente.telefone
            )
            print("Mensagem enviada para o Twilio com sucesso.")
        else:
            print("⚠️ Twilio não configurado no .env, salvando apenas no banco.")

    except Exception as e:
        print(f"❌ Erro ao enviar Twilio: {e}")

    # Salva no banco
    nova_msg = Mensagem(cliente_id=cliente.id, role='human', conteudo=texto)
    db.session.add(nova_msg)
    
    cliente.modo = 'humano'
    db.session.commit()
    
    return jsonify({'status': 'enviado'})

# ==========================================
# WEBHOOK WHATSAPP
# ==========================================
@app.route('/whatsapp', methods=['POST'])
def whatsapp_reply():
    remetente = request.values.get('From', '')
    msg_usuario = request.values.get('Body', '').strip()
    resp = MessagingResponse()

    if not msg_usuario:
        return str(resp)

    cliente = Cliente.query.filter_by(telefone=remetente).first()
    if not cliente:
        cliente = Cliente(telefone=remetente, nome="Novo Lead", modo='bot')
        db.session.add(cliente)
        db.session.commit()

    msg_db = Mensagem(cliente_id=cliente.id, role='user', conteudo=msg_usuario)
    db.session.add(msg_db)
    db.session.commit()

    if cliente.modo == 'humano':
        return str(resp)

    try:
        historico_db = Mensagem.query.filter_by(cliente_id=cliente.id).order_by(Mensagem.timestamp).limit(30).all()
        history_gemini = []
        for h in historico_db:
            role = 'user' if h.role == 'user' else 'model'
            history_gemini.append({"role": role, "parts": [h.conteudo]})

        prompt = gerar_prompt_dinamico()
        model = iniciar_modelo(prompt)
        chat = model.start_chat(history=history_gemini)
        
        response = chat.send_message(msg_usuario)
        texto_resposta = response.text

        msg_bot = Mensagem(cliente_id=cliente.id, role='model', conteudo=texto_resposta)
        db.session.add(msg_bot)
        db.session.commit()

        paragrafos = [p.strip() for p in texto_resposta.split('\n') if p.strip()]
        for p in paragrafos:
            resp.message(p)

    except Exception as e:
        print(f"Erro Gemini: {e}")
        resp.message("Estou processando muita coisa agora, um momento...")

    return str(resp)

# ==========================================
# LOGIN / LOGOUT / SYNC
# ==========================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario_form = request.form.get('username')
        senha_form = request.form.get('password')
        
        # --- CORREÇÃO 5: Login via Banco + Hash ---
        user_db = Usuario.query.filter_by(username=usuario_form).first()
        
        if user_db and check_password_hash(user_db.password_hash, senha_form):
            session['admin_logged_in'] = True
            return redirect(url_for('dashboard'))
            
        flash('Login inválido ou senha incorreta.')
        
    return render_template('login.html')

@app.route('/logout', endpoint='logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('login'))

@app.route('/api/sync/produtos', methods=['POST'])
def sync_produtos():
    try:
        data = request.json
        Produto.query.delete()
        for item in data:
            p = Produto(nome=item.get('nome'), descricao=item.get('descricao'), preco=str(item.get('preco')))
            db.session.add(p)
        db.session.commit()
        return jsonify({'status': 'ok'})
    except:
        return jsonify({'error': 'erro'}), 500
    
@app.route('/settings/new_user', methods=['POST'])
@login_required
def create_user():
    username = request.form.get('new_username')
    password = request.form.get('new_password')
    
    # --- CORREÇÃO 6: Validação Básica ---
    if not username or not password:
        flash('Preencha todos os campos.')
        return redirect(url_for('settings'))

    if Usuario.query.filter_by(username=username).first():
        flash('Erro: Esse usuário já existe.')
        return redirect(url_for('settings'))
    
    hashed = generate_password_hash(password)
    novo_user = Usuario(username=username, password_hash=hashed, role='suporte')
    db.session.add(novo_user)
    db.session.commit()
    
    flash(f'Usuário {username} criado com sucesso!')
    return redirect(url_for('settings'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)