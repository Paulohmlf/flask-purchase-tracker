import os
import logging
from waitress import serve
from app import app  # Importa o seu aplicativo Flask do arquivo app.py

# Configura logs simples para o console (apenas para ver que está rodando)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%H:%M:%S')

if __name__ == "__main__":
    try:
        PORTA = 8080
        THREADS = 6  # Número de tarefas simultâneas (ideal para escritórios pequenos/médios)
        
        print("\n" + "="*60)
        print(f"🚀 INICIANDO SERVIDOR DE PRODUÇÃO - NUTRANE COMPRAS")
        print("="*60)
        print(f"✅ Status: ONLINE")
        print(f"🏠 Local:  http://localhost:{PORTA}")
        print(f"📡 Rede:   http://0.0.0.0:{PORTA} (Acesse pelo IP deste PC)")
        print(f"⚙️  Modo:   Produção (Waitress) com {THREADS} threads")
        print("-" * 60)
        print("Logs de erro serão salvos automaticamente na pasta 'logs/'.")
        print("Pressione Ctrl+C para encerrar o servidor.")
        print("-" * 60 + "\n")

        # INICIA O SERVIDOR WAITRESS COM CONFIGURAÇÕES ROBUSTAS
        serve(
            app,
            host='0.0.0.0',
            port=PORTA,
            threads=THREADS,          # Permite 6 requisições ao mesmo tempo
            connection_limit=200,     # Aguenta até 200 conexões na fila
            channel_timeout=30,       # Derruba conexões presas após 30s
            ident="ServidorNutrane"   # Identificação interna do servidor
        )
        
    except Exception as e:
        print("\n" + "!"*50)
        print(f"❌ ERRO CRÍTICO AO INICIAR O SERVIDOR:")
        print(f"{e}")
        print("!"*50)
        
        # Tenta gravar o erro no log do sistema, se o app estiver acessível
        try:
            app.logger.error(f"FALHA FATAL NO STARTUP DO SERVIDOR: {e}", exc_info=True)
            print(" -> O erro foi registrado no arquivo de logs.")
        except:
            pass
            
        input("\nPressione ENTER para fechar a janela...")