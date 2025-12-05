# Loja Fictícia Dark Store roupas - Chatbot & Management System

Sistema de gerenciamento de atendimento automatizado via WhatsApp, integrando **Google Gemini AI**, **Flask**, **PostgreSQL** e **n8n**. O projeto inclui painel administrativo, controle de fluxo (Bot vs Humano) e webhooks ativos via Twilio.

---

## 📂 Estrutura do Projeto

```text
./
├── automations/            # Workflows do n8n (ex: Atualizar_produtos_db.json)
├── scripts/                # Scripts utilitários (seed, manutenção)
├── src/
│   ├── services/           # Lógica de IA (Gemini), Tools e WhatsApp
│   ├── templates/          # Frontend (HTML/Jinja2 + Tailwind)
│   ├── config.py           # Configurações gerais
│   ├── init_db.py          # Script de inicialização do banco
│   ├── main.py             # Entrypoint da aplicação Flask
│   ├── models.py           # Schemas do SQLAlchemy
│   └── __init__.py
├── docker-compose.yml      # Orquestração dos serviços (App, DB, n8n)
├── Dockerfile              # Build da imagem Python
├── requirements.txt        # Dependências Python
├── resumo.py               # Script auxiliar de contexto
└── system_prompt.txt       # Personalidade e regras do Bot
```

## 🛠️ Pré-requisitos
------------------

*   **Docker & Docker Compose** (Obrigatório).
    
*   **Ngrok** (Para expor o localhost para Twilio/n8n).
    
*   **Conta Twilio** (SID, Token e Número).
    
*   **Google Gemini API Key**.
    

🚀 Instalação e Execução
------------------------

### 1\. Variáveis de Ambiente (.env)

Crie um arquivo .env na raiz:
```text
# App
PROJECT_NAME=project_bot
APP_PORT=5000
SECRET_KEY=dev_secret_key_change_in_prod

# Database
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=chatbot_db
DATABASE_URL=postgresql://postgres:postgres@db:5432/chatbot_db

# Integrações
GEMINI_API_KEY=sua_chave_gemini
TWILIO_ACCOUNT_SID=seu_sid
TWILIO_AUTH_TOKEN=seu_token
TWILIO_PHONE_NUMBER=whatsapp:+14155238886

# Configurações do Negócio
CHATBOT_NAME="Rosa"
COMPANY_NAME="Dark Store roupas"
ADMIN_USER=admin
ADMIN_SECRET_TOKEN=admin
ENABLE_EXTERNAL_SYNC=True `
```

### 2\. Inicialização (Docker)

```bash
# Sobe a aplicação, banco e n8n em background
docker-compose up --build -d `
```
_O script src/init\_db.py rodará automaticamente para criar tabelas e o usuário admin._

📡 Configuração de Webhooks
---------------------------

Para o sistema funcionar, o mundo externo precisa acessar seu container.

1.  **Exponha a porta:** ngrok http 5000
    
2.  https://seu-url-ngrok.app/whatsapp
    

⚙️ Automação (n8n)
------------------

O n8n roda em http://localhost:5678.

1.  **Acesso:** Abra o navegador na porta 5678.
    
2.  **Importação:** Importe o workflow localizado em ./automations/Atualizar\_produtos\_db.json.
    
3.  **Configuração:**
    
    *   No node _HTTP Request_ do n8n, use a URL: http://host.docker.internal:5000/api/sync/produtos
        
    *   Isso garante que o container do n8n enxergue o container da App.
        

🔌 API Endpoints
----------------

### 💬 Chat e Mensageria

| Método | Rota | Descrição |
| :--- | :--- | :--- |
| **POST** | `/whatsapp` | Webhook principal do Twilio. Recebe e processa mensagens. |
| **POST** | `/api/send_human` | Envia mensagem manual (`{cliente_id, texto}`). |
| **GET** | `/api/chat/<id>` | Retorna histórico JSON da conversa. |



### 🔧 Controle e Sync

| Método | Rota | Descrição |
| :--- | :--- | :--- |
| **POST** | `/api/toggle_mode/<id>` | Alterna modo do cliente (`bot` vs `humano`). |
| **POST** | `/api/assistente_pessoal` | IA interna para comandos administrativos (Function Calling). |
| **POST** | `/api/sync/produtos` | Recebe JSON de produtos para atualizar o catálogo. |

🖥️ Acesso ao Sistema
---------------------

*   **URL:** http://localhost:5000
    
*   **Login Padrão:** admin / admin (Definido no .env)
    

🐛 Troubleshooting
------------------

*   **Erro de DB na primeira execução:** O Postgres pode demorar uns segundos para aceitar conexão. Dê um restart no container app se necessário.
    
*   **Twilio não responde:** Verifique se a URL do Ngrok não expirou/mudou.
    
*   **Loop de mensagens:** Verifique se o número do remetente no Twilio é diferente do destinatário.
    

> Desenvolvido para **Loja ficticia**.