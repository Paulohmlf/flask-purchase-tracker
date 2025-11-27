import sqlite3
from werkzeug.security import generate_password_hash

def criar_banco():
    print("🔄 Criando tabelas do banco de dados...")
    connection = sqlite3.connect('database.db')
    cursor = connection.cursor()
    
    # 1. Tabela de Usuários
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome_completo TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        senha TEXT NOT NULL,
        nivel_acesso TEXT DEFAULT 'comprador',
        aprovado INTEGER DEFAULT 0 
    )
    ''')

    # 2. Tabela de Empresas (Unidades)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS empresas_compras (
        codi_empresa INTEGER PRIMARY KEY,
        nome_empresa TEXT NOT NULL
    )
    ''')

    # 3. Tabela Principal do Pedido (Cabeçalho)
    # Inclui a nova coluna 'solicitante_real'
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS acompanhamento_compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        
        numero_solicitacao TEXT NOT NULL,
        numero_orcamento TEXT,
        numero_pedido TEXT,
        item_comprado TEXT,  -- Título/Resumo do pedido
        categoria TEXT,
        fornecedor TEXT,
        data_compra TEXT,
        
        nota_fiscal TEXT,
        serie_nota TEXT,
        observacao TEXT,                   
        
        codi_empresa INTEGER NOT NULL,
        id_responsavel_chamado INTEGER,   -- Usuário do Sistema
        id_comprador_responsavel INTEGER, -- Usuário do Sistema
        solicitante_real TEXT,            -- Nome de quem pediu na ponta (Texto livre)
        
        prazo_entrega TEXT,
        data_entrega_reprogramada TEXT,
        status_compra TEXT DEFAULT 'Aguardando Aprovação',
        data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        
        FOREIGN KEY (codi_empresa) REFERENCES empresas_compras (codi_empresa),
        FOREIGN KEY (id_responsavel_chamado) REFERENCES usuarios (id),
        FOREIGN KEY (id_comprador_responsavel) REFERENCES usuarios (id)
    )
    ''')
    
    # 4. Tabela de Itens do Pedido (1 Pedido -> Vários Itens)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS pedidos_itens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pedido_id INTEGER NOT NULL,
        nome_item TEXT NOT NULL,
        categoria TEXT,
        quantidade INTEGER DEFAULT 1,
        unidade_medida TEXT DEFAULT 'UN',
        valor_estimado REAL DEFAULT 0.0,
        FOREIGN KEY (pedido_id) REFERENCES acompanhamento_compras (id) ON DELETE CASCADE
    )
    ''')
    
    # 5. Tabela de Múltiplos Anexos
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS pedidos_anexos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pedido_id INTEGER NOT NULL,
        nome_arquivo TEXT NOT NULL,
        nome_original TEXT,
        data_upload TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (pedido_id) REFERENCES acompanhamento_compras (id) ON DELETE CASCADE
    )
    ''')
    
    # --- DADOS INICIAIS (SEED) ---
    
    # Criar Administrador Padrão
    senha_admin = generate_password_hash('123456')
    try:
        cursor.execute("INSERT INTO usuarios (nome_completo, email, senha, nivel_acesso, aprovado) VALUES (?, ?, ?, ?, ?)",
                       ('Administrador', 'admin@nutrane.com.br', senha_admin, 'admin', 1))
        print("👤 Usuário Admin criado.")
    except sqlite3.IntegrityError: 
        print("👤 Usuário Admin já existe.")

    # Criar Empresas/Unidades do CSV
    empresas = [
        (2, 'Durancho Sertania'),
        (7, 'Nutrane Bahia'),
        (4, 'Nutrane Carpina'),
        (1, 'Nutrane Pesqueira'),
        (6, 'Nutrane Piaui'),
        (10, 'Nutrind')
    ]
    try:
        cursor.executemany("REPLACE INTO empresas_compras (codi_empresa, nome_empresa) VALUES (?, ?)", empresas)
        print("🏢 Unidades (Filiais) cadastradas.")
    except sqlite3.IntegrityError: pass

    connection.commit()
    connection.close()
    print("✅ Banco de dados recriado com sucesso (Estrutura Completa)!")

if __name__ == '__main__':
    criar_banco()