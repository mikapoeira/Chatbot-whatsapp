import os
from functools import wraps
from datetime import datetime # Para timestamp e manipulação de datas
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, flash
# IMPORTANTE: Garanta que você está importando TUDO que precisa.
from src.models import db, Cliente, Mensagem, Produto, Usuario, BotConfig 
from werkzeug.security import generate_password_hash, check_password_hash
from src.services.gemini_service import configurar_gemini, iniciar_modelo, gerar_prompt_dinamico
from twilio.rest import Client # Para enviar mensagens ativas
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

# --- CONFIGURAÇÕES ---
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.getenv('ADMIN_SECRET_TOKEN', 'dev_secret_key')

db.init_app(app)
configurar_gemini()

# Permite qualquer usuário logado (Admin ou Atendente)
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session or not session['admin_logged_in']:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Restringe APENAS para o Administrador
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Checa se está logado (login_required já faz isso, mas é bom redundância)
        if 'admin_logged_in' not in session or not session['admin_logged_in']:
            return redirect(url_for('login'))
        
        # CHECAGEM DE PERMISSÃO
        if session.get('user_role') != 'admin':
            flash('Acesso negado. Você não tem permissão de administrador.', 'error') # <-- Adicionado tag 'error'
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
        # Busca as contagens nas tabelas corretas
        # Use o modelo 'Cliente' (a nova tabela 'cliente') e 'Mensagem'
        total_clientes = db.session.query(Cliente).count() # Usando db.session para garantir o contexto
        total_msgs = db.session.query(Mensagem).count()
        total_produtos = db.session.query(Produto).count()
    
    except Exception as e:
        # O erro geralmente é 'relation does not exist' ou 'column not found'
        print(f"❌ ERRO CRÍTICO NA DASHBOARD (DB): {e}. Usando zero para evitar crash.")
        total_clientes = 0
        total_msgs = 0
        total_produtos = 0
    
    return render_template(
        'index.html', 
        total_clientes=total_clientes, 
        total_msgs=total_msgs, 
        total_produtos=total_produtos
    )

@app.route('/chats', endpoint='conversas')
@login_required
def chats_view():
    # A lista de conversas é baseada na tabela Mensagem, 
    # que referencia a tabela Cliente (a nova).
    # Vamos puxar todas as mensagens únicas, agrupadas por cliente, para a lista lateral.
    
    # 1. Busca todos os clientes que JÁ TIVERAM conversas (para a sidebar)
    # E ordena pelo timestamp da última mensagem (usando join ou subquery complexa).
    # Como alternativa simples e direta (que o Jinja precisa):
    
    # Busca clientes da tabela de conversas
    clientes_com_conversa = Mensagem.query.with_entities(Mensagem.cliente_id).distinct()
    
    # Filtra e ordena a tabela Cliente (Tabela 6) por data de criação (ou ID)
    clientes = Cliente.query.filter(Cliente.id.in_(clientes_com_conversa)) \
                           .order_by(Cliente.created_at.desc()).all()
    
    return render_template('chats.html', clientes=clientes)

@app.route('/products', endpoint='produtos')
@login_required
def products_view():
    produtos = Produto.query.all()
    return render_template('products.html', produtos=produtos)

@app.route('/settings', endpoint='configuracoes', methods=['GET', 'POST']) # <--- Aceita POST agora
@admin_required
def settings_view():
    try:
        # Busca a config (sempre existe pois o init_db cria)
        config = BotConfig.query.first()
        usuarios = Usuario.query.all()
    except Exception as e:
        config = MockConfig()
        usuarios = []
        # Em caso de falha de conexão/tabela, cria um objeto vazio para o HTML não cair
        print(f"❌ ERRO CRÍTICO no Settings (Falha BotConfig): {e}")
        flash('Erro de conexão com o Banco de Dados. A página pode não carregar corretamente.', 'error')
        
        # Cria um objeto mock para evitar crash do Jinja no HTML
        class MockConfig:
            nome_bot = "ERRO"
            personalidade = "ERRO DE CONEXÃO"
        config = MockConfig()

    if request.method == 'POST':
        # Atualiza os dados vindos do formulário
        novo_nome = request.form.get('nome_bot')
        nova_personalidade = request.form.get('personalidade')
        
        
        if config.nome_bot != "ERRO":
            novo_nome = request.form.get('nome_bot')
            nova_personalidade = request.form.get('personalidade')
            config.nome_bot = novo_nome
            config.personalidade = nova_personalidade
            db.session.commit()
            flash('Configurações atualizadas com sucesso!')
        
        return redirect(url_for('configuracoes'))

    return render_template(
        'settings.html', 
        config=config,
        usuarios=usuarios # <--- NOVO CONTEXTO
    )

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
        
        user_db = Usuario.query.filter_by(username=usuario_form).first()
        
        # --- BLOC DA CHECAGEM E SUCESSO ---
        if user_db and check_password_hash(user_db.password_hash, senha_form):
            
            # Lógica de Sucesso: Salva a role e a sessão
            session['admin_logged_in'] = True
            session['user_role'] = user_db.role 
            
            # Se for admin, garante que a role é 'admin' na sessão
            if user_db.role == 'admin':
                session['user_role'] = 'admin' 
            
            # ÚNICO return válido no bloco de sucesso
            return redirect(url_for('dashboard'))

        else: # <--- ADICIONE ESTE BLOCO ELSE
            # --- TRATAMENTO DE FALHA ---
            flash('Login inválido ou senha incorreta.', 'error')
            # Retorna o redirecionamento
            return redirect(url_for('login')) 
        # --- FIM DO BLOC DE CHECAGEM ---

    # Se o método for GET (ou for redirecionado após a falha)
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
@admin_required # <-- Novo decorator
def create_user():
    # --- CÓDIGO FALTANTE: Pegando os dados do formulário ---
    username = request.form.get('username')
    password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')
    role = request.form.get('role')
    
    if password != confirm_password:
        flash('As senhas não coincidem. O usuário não foi criado.', 'error')
        return redirect(url_for('configuracoes'))

    # Adicionando validação básica para não criar usuário vazio
    if not username or not password:
        flash('Nome de usuário e senha são obrigatórios.', 'error')
        return redirect(url_for('configuracoes'))
        
    if Usuario.query.filter_by(username=username).first():
        flash('Erro: Esse usuário já existe.', 'error')
        return redirect(url_for('configuracoes'))
        
    hashed = generate_password_hash(password)
    novo_user = Usuario(username=username, password_hash=hashed, role=role) 
    db.session.add(novo_user)
    db.session.commit()
    
    flash(f'Usuário {username} criado com sucesso como {role}!', 'success')
    return redirect(url_for('configuracoes'))

@app.route('/settings/change_password', methods=['POST'])
@login_required # Garante que apenas usuários logados podem acessar
def change_own_password():
    # 1. Obter dados do formulário
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    # 2. Obter o usuário logado
    user_id = session.get('user_id')
    current_user = Usuario.query.get(user_id)
    
    # 3. Validação: As senhas coincidem?
    if new_password != confirm_password:
        flash('As novas senhas não coincidem. Por favor, digite novamente.', 'error')
        return redirect(url_for('configuracoes'))

    # 4. Validação: A senha é válida (ex: 6 caracteres)?
    if not new_password or len(new_password) < 6:
        flash('A senha deve ter pelo menos 6 caracteres.', 'error')
        return redirect(url_for('configuracoes'))

    # 5. Atualiza o hash da senha e salva no DB
    current_user.password_hash = generate_password_hash(new_password)
    db.session.commit()

    flash('Sua senha foi alterada com sucesso! Utilize a nova senha no próximo login.', 'success')
    return redirect(url_for('configuracoes'))

# ==========================================
# ROTAS DE CLIENTES
# ==========================================

# 1. Listagem de Clientes (Acesso: Admin e Atendente)
@app.route('/clientes', endpoint='list_clientes')
@login_required 
def list_clientes():
    # Garantindo que o cliente_id seja referenciado à nova tabela 'cliente'
    todos_clientes = Cliente.query.all()
    user_role = session.get('user_role', 'atendente') 
    
    # O HTML vai decidir se mostra o botão de cadastro
    return render_template(
        'clientes.html', 
        clientes=todos_clientes, 
        user_role=user_role
    )

# 2. Criação de Cliente (Acesso: SÓ ADMIN PODE CADASTRAR)
@app.route('/clientes/create', methods=['POST'])
@admin_required # <-- Restrito ao Admin
def create_cliente():
    # --- Lógica Genérica de Criação (a ser customizada na outra branch) ---
    numero = request.form.get('numero_cliente')
    nome = request.form.get('nome_cliente')
    tem_suporte = 'suporte' in request.form 
    
    if not numero or not nome:
        flash('Nome e Número do Cliente são obrigatórios.', 'error')
        return redirect(url_for('list_clientes'))

    novo_cliente = Cliente(
        numero_cliente=numero,
        nome_cliente=nome,
        tem_suporte=tem_suporte,
        # data_vencimento NÃO existe nesta branch main!
    )
    
    db.session.add(novo_cliente)
    db.session.commit()
    flash(f'Cliente {nome} cadastrado com sucesso!', 'success')
    return redirect(url_for('list_clientes'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)