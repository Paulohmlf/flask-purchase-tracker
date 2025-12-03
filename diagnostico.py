import os
import pymysql
from dotenv import load_dotenv

# Carrega as senhas do arquivo .env
load_dotenv()

# Configurações do Banco (Lidas do .env)
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME')
DB_PORT = int(os.getenv('DB_PORT', 3306))

def atualizar_tabelas():
    print("🔄 Conectando ao Banco de Dados...")
    
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT,
            autocommit=True
        )
        cursor = conn.cursor()
        print("✅ Conectado com sucesso!")

        # --- 1. Adicionar Colunas na Tabela de PEDIDOS (Cabeçalho) ---
        print("\n📦 Atualizando tabela 'acompanhamento_compras'...")
        
        comandos_pedidos = [
            # Coluna para Lead Time (Data exata que chegou)
            "ALTER TABLE acompanhamento_compras ADD COLUMN data_entrega_real DATE",
            
            # Coluna Booleana (0 ou 1) para OTIF (Entregue Corretamente?)
            "ALTER TABLE acompanhamento_compras ADD COLUMN entrega_conforme TINYINT(1) DEFAULT NULL",
            
            # Coluna de Texto para Detalhes (O que deu errado?)
            "ALTER TABLE acompanhamento_compras ADD COLUMN detalhes_entrega TEXT"
        ]

        for cmd in comandos_pedidos:
            try:
                cursor.execute(cmd)
                print(f"   👉 Executado: {cmd.split('ADD COLUMN')[1].strip()}")
            except pymysql.err.OperationalError as e:
                if e.args[0] == 1060: # Erro 1060 = Coluna já existe
                    print(f"   ⚠️ Coluna já existe (Ignorado): {cmd.split('ADD COLUMN')[1].split()[0]}")
                else:
                    print(f"   ❌ Erro: {e}")

        # --- 2. Adicionar Coluna na Tabela de ITENS (Produtos) ---
        print("\n🛒 Atualizando tabela 'pedidos_itens'...")
        
        # Coluna para Análise Financeira (Valor R$)
        cmd_item = "ALTER TABLE pedidos_itens ADD COLUMN valor_unitario DECIMAL(10,2) DEFAULT 0.00"
        
        try:
            cursor.execute(cmd_item)
            print(f"   👉 Executado: valor_unitario")
        except pymysql.err.OperationalError as e:
            if e.args[0] == 1060:
                print(f"   ⚠️ Coluna valor_unitario já existe (Ignorado)")
            else:
                print(f"   ❌ Erro: {e}")

        conn.close()
        print("\n🚀 FASE 1 CONCLUÍDA: Banco de dados atualizado com sucesso!")

    except Exception as e:
        print(f"\n❌ ERRO FATAL AO CONECTAR: {e}")
        print("Verifique se o arquivo .env está correto e se o banco está ligado.")

if __name__ == '__main__':
    atualizar_tabelas()