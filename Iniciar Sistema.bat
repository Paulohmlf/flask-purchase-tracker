@echo off
echo ==========================================
echo      INICIANDO SISTEMA DE COMPRAS
echo ==========================================
echo.
echo 1. Verificando ambiente...
cd /d "%~dp0"

echo 2. Ativando o Python...
call .venv\Scripts\activate

echo 3. Iniciando o Servidor (Waitress)...
echo    O sistema ficara disponivel em:
echo    - Neste PC: http://localhost:8080
echo    - Na Rede:  http://SEU_IP_AQUI:8080
echo.
echo    NAO FECHE ESTA JANELA ENQUANTO USAR O SISTEMA!
echo.

waitress-serve --host=0.0.0.0 --port=8080 app:app

if %errorlevel% neq 0 (
    echo.
    echo !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    echo ERRO CRITICO: O sistema fechou sozinho.
    echo Verifique a mensagem de erro acima.
    echo !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    pause
)