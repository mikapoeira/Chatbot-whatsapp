FROM python:3.9-slim

WORKDIR /app

# Instala dependências do sistema
RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*

# Instala Python libs
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia código
COPY . .
ENV PYTHONPATH=/app

# --- A MUDANÇA ESTÁ AQUI ---
# Executa o script de inicialização E DEPOIS (&&) sobe o servidor
CMD ["sh", "-c", "python src/init_db.py && gunicorn --bind 0.0.0.0:5000 src.main:app"]