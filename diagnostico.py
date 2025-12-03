import sys
import os
import time

print("\n--- INICIANDO DIAGNOSTICO ---")
print(f"Python em uso: {sys.executable}")

print("\n1. Testando Bibliotecas...")
try:
    import mysql.connector
    import dotenv
    import waitress
    print("   [OK] Todas as bibliotecas encontradas.")
except ImportError as e:
    print(f"   [ERRO FATAL] Falta instalar biblioteca: {e}")
    input("Pressione Enter para sair..."); sys.exit(1)

print("\n2. Testando Importação do App...")
try:
    # Tenta importar o app igual o Waitress faria
    from app import app
    print("   [OK] App importado com sucesso (Sem erros de sintaxe).")
except Exception as e:
    print(f"   [ERRO FATAL] O app.py tem um erro: {e}")
    import traceback
    traceback.print_exc()
    input("Pressione Enter para sair..."); sys.exit(1)

print("\n3. Testando Conexão com Banco de Dados...")
try:
    from app import get_db_connection
    conn = get_db_connection()
    if conn:
        print("   [OK] Conexão com MariaDB realizada com sucesso!")
        conn.close()
    else:
        print("   [ERRO] O Banco conectou mas retornou vazio. Verifique o arquivo .env")
except Exception as e:
    print(f"   [ERRO] Falha ao conectar no banco: {e}")
    print("   Verifique se o IP 192.168.12.41 está correto e acessível.")

print("\n4. Testando Servidor Waitress (Porta 8081)...")
print("   (Vamos tentar a porta 8081 para evitar conflito com processos zumbis)")
try:
    from waitress import serve
    print("   >>> O servidor vai tentar iniciar agora. Se aparecer 'Serving on...', DEU CERTO!")
    print("   >>> Acesse http://localhost:8081 para testar.")
    print("   >>> Pressione Ctrl+C para parar o teste.\n")
    serve(app, host='0.0.0.0', port=8081)
except Exception as e:
    print(f"   [ERRO FATAL] O Waitress falhou: {e}")

input("\nDiagnóstico finalizado. Pressione Enter...")