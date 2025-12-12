import os
import pymysql
import pymysql.cursors
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv

# 1. Carrega as configurações do banco igual ao app.py
load_dotenv()

DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME')
DB_PORT = int(os.getenv('DB_PORT', 3306))

def get_db_connection():
    try:
        conn = pymysql.connect(
            host=DB_HOST, user=DB_USER, password=DB_PASSWORD,
            database=DB_NAME, port=DB_PORT,
            charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor,
            autocommit=True
        )
        return conn
    except Exception as e:
        print(f"❌ Erro ao conectar no banco: {e}")
        return None

def listar_usuarios():
    conn = get_db_connection()
    if not conn: return
    
    with conn.cursor() as cursor:
        cursor.execute("SELECT id, nome_completo, email, nivel_acesso, aprovado FROM usuarios")
        users = cursor.fetchall()
        
    conn.close()
    
    print("\n--- USUÁRIOS NO BANCO ---")
    print(f"{'ID':<5} | {'NOME':<25} | {'EMAIL':<30} | {'NÍVEL':<10} | {'STATUS'}")
    print("-" * 90)
    for u in users:
        status = "✅ Ativo" if u['aprovado'] == 1 else "⛔ Pendente"
        print(f"{u['id']:<5} | {u['nome_completo'][:25]:<25} | {u['email'][:30]:<30} | {u['nivel_acesso']:<10} | {status}")
    print("-" * 90 + "\n")

def ativar_usuario():
    email = input("Digite o EMAIL do usuário para ativar: ").strip()
    conn = get_db_connection()
    if not conn: return
    
    with conn.cursor() as cursor:
        cursor.execute("UPDATE usuarios SET aprovado = 1 WHERE email = %s", (email,))
        if cursor.rowcount > 0:
            print(f"✅ Sucesso! O usuário {email} agora pode fazer login.")
        else:
            print("❌ Usuário não encontrado.")
    conn.close()

def resetar_senha():
    email = input("Digite o EMAIL do usuário para trocar a senha: ").strip()
    nova_senha = input("Digite a NOVA SENHA: ").strip()
    
    conn = get_db_connection()
    if not conn: return
    
    hash_senha = generate_password_hash(nova_senha)
    
    with conn.cursor() as cursor:
        cursor.execute("UPDATE usuarios SET senha = %s WHERE email = %s", (hash_senha, email))
        if cursor.rowcount > 0:
            print(f"✅ Sucesso! Senha de {email} atualizada.")
        else:
            print("❌ Usuário não encontrado.")
    conn.close()

def menu():
    while True:
        print("=== FERRAMENTA DE RECUPERAÇÃO ===")
        print("1. Listar Usuários")
        print("2. Ativar um Usuário (Aprovar)")
        print("3. Resetar Senha")
        print("4. Sair")
        opcao = input("Escolha: ")
        
        if opcao == '1': listar_usuarios()
        elif opcao == '2': ativar_usuario()
        elif opcao == '3': resetar_senha()
        elif opcao == '4': break
        else: print("Opção inválida.")

if __name__ == "__main__":
    menu()