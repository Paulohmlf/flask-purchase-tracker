import sqlite3
from werkzeug.security import generate_password_hash

def criar_banco():
    connection = sqlite3.connect('database.db')
    cursor = connection.cursor()
    
    # 1. Usuários
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

    # 2. Empresas (Lojas/Unidades)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS empresas_compras (
        codi_empresa INTEGER PRIMARY KEY,
        nome_empresa TEXT NOT NULL
    )
    ''')

    # 3. Acompanhamento (COM NOVOS CAMPOS DO PDF: Categoria e Observação)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS acompanhamento_compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        
        numero_solicitacao TEXT NOT NULL,
        numero_orcamento TEXT,
        numero_pedido TEXT,
        item_comprado TEXT,
        categoria TEXT,                    -- NOVO: Ex: Rolamento, Correia 
        fornecedor TEXT,
        data_compra TEXT,
        
        nota_fiscal TEXT,
        serie_nota TEXT,
        arquivo_anexo TEXT,
        observacao TEXT,                   -- NOVO: Comentários/Updates 
        
        codi_empresa INTEGER NOT NULL,
        id_responsavel_chamado INTEGER,
        id_comprador_responsavel INTEGER,
        prazo_entrega TEXT,
        data_entrega_reprogramada TEXT,
        status_compra TEXT DEFAULT 'Aguardando Aprovação',
        data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (codi_empresa) REFERENCES empresas_compras (codi_empresa),
        FOREIGN KEY (id_responsavel_chamado) REFERENCES usuarios (id),
        FOREIGN KEY (id_comprador_responsavel) REFERENCES usuarios (id)
    )
    ''')
    
    # --- DADOS INICIAIS ---
    
    # Admin
    senha_admin = generate_password_hash('123456')
    try:
        cursor.execute("INSERT INTO usuarios (nome_completo, email, senha, nivel_acesso, aprovado) VALUES (?, ?, ?, ?, ?)",
                       ('Administrador', 'admin@nutrane.com.br', senha_admin, 'admin', 1))
    except sqlite3.IntegrityError: pass

    # --- EMPRESAS ATUALIZADAS (BASEADO NO CSV) ---
    empresas = [
        (2, 'Durancho Sertania'),
        (7, 'Nutrane Bahia'),
        (4, 'Nutrane Carpina'),
        (1, 'Nutrane Pesqueira'),
        (6, 'Nutrane Piaui'),
        (10, 'Nutrind')
    ]
    try:
        # A instrução REPLACE INTO é mais segura para garantir que as empresas estejam corretas
        # sem violar a chave primária se o script for rodado mais de uma vez.
        cursor.executemany("REPLACE INTO empresas_compras (codi_empresa, nome_empresa) VALUES (?, ?)", empresas)
        print("Unidades (Filiais) atualizadas conforme CSV!")
    except sqlite3.IntegrityError: pass

    connection.commit()
    connection.close()
    print("Banco recriado com Categoria, Observação e Novas Unidades!")

if __name__ == '__main__':
    criar_banco()