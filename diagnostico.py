import os
import pymysql
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME')
}

def renomear():
    print("🔄 Conectando ao Banco...")
    try:
        conn = pymysql.connect(**DB_CONFIG, autocommit=True)
        cursor = conn.cursor()
        
        # Comando para renomear a coluna
        # CHANGE COLUMN antigo novo TIPO
        sql = "ALTER TABLE acompanhamento_compras CHANGE COLUMN requisicao_compra data_abertura VARCHAR(50)"
        
        cursor.execute(sql)
        print("✅ Sucesso! Coluna renomeada para 'data_abertura'.")
        
        conn.close()
    except Exception as e:
        print(f"❌ Erro (Talvez já tenha sido renomeada?): {e}")

if __name__ == '__main__':
    renomear()