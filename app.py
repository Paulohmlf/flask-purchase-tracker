import os
import math
import json
import logging
from logging.handlers import RotatingFileHandler
from io import BytesIO
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import pymysql
import pymysql.cursors
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, date, timedelta
from collections import defaultdict
import pdfplumber
import re
from dotenv import load_dotenv
from xhtml2pdf import pisa 

# 1. CARREGA AS VARIÁVEIS DE AMBIENTE
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'chave_padrao_se_nao_achar')

# --- CONFIGURAÇÃO DE LOGS (REGISTO DE ERROS) ---
# Cria a pasta 'logs' se ela não existir
if not os.path.exists('logs'):
    os.makedirs('logs')

# Configura o ficheiro para guardar os erros (limite de 1MB, guarda 10 backups)
file_handler = RotatingFileHandler('logs/erros_sistema.log', maxBytes=1024 * 1024, backupCount=10, encoding='utf-8')
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [em %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.ERROR)

# Anexa esta configuração à aplicação Flask
app.logger.addHandler(file_handler)
# -----------------------------------------------

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 2. CONFIGURAÇÕES DA BASE DE DADOS
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME')
DB_PORT = int(os.getenv('DB_PORT', 3306))

# --- TRATAMENTO GLOBAL DE ERROS ---
@app.errorhandler(Exception)
def handle_exception(e):
    """Captura qualquer erro não tratado no sistema e grava no log."""
    app.logger.error(f"ERRO CRÍTICO NÃO TRATADO: {e}", exc_info=True)
    return "Ocorreu um erro interno no sistema. O administrador foi notificado via log.", 500

# --- FUNÇÕES AUXILIARES ---

def allowed_file(filename):
    """Verifica se a extensão do ficheiro é permitida"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db_connection():
    """Estabelece conexão com o MariaDB usando PyMySQL"""
    try:
        if not DB_HOST or not DB_USER:
            print("❌ ERRO CRÍTICO: Variáveis do .env não encontradas!")
            return None

        conn = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True
        )
        return conn
    except Exception as e:
        # LOG ADICIONADO AQUI
        app.logger.error(f"Falha ao conectar na Base de Dados: {e}")
        print(f"❌ Erro ao conectar na Base de Dados: {e}")
        return None

def salvar_anexos_multiplos(conn, pedido_id, files):
    """Guarda ficheiros na pasta e regista na base de dados"""
    cursor = conn.cursor()
    for arq in files:
        if arq and allowed_file(arq.filename) and arq.filename != '':
            nome_original = arq.filename
            nome_seguro = secure_filename(f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{nome_original}")
            caminho_completo = os.path.join(app.config['UPLOAD_FOLDER'], nome_seguro)
            arq.save(caminho_completo)
            
            cursor.execute('''
                INSERT INTO pedidos_anexos (pedido_id, nome_arquivo, nome_original) 
                VALUES (%s, %s, %s)
            ''', (pedido_id, nome_seguro, nome_original))
    cursor.close()

def safe_float(valor_str):
    """Converte string de moeda para float de forma segura"""
    if not valor_str: 
        return 0.0
    try:
        limpo = str(valor_str).replace('.', '').replace(',', '.')
        return float(limpo)
    except:
        return 0.0

# --- ROTAS DE AUTENTICAÇÃO ---

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        senha = request.form['senha']
        
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM usuarios WHERE email = %s', (email,))
            user = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if user and check_password_hash(user['senha'], senha) and user['aprovado'] == 1:
                session['user_id'] = user['id']
                session['user_name'] = user['nome_completo']
                session['user_nivel'] = user['nivel_acesso']
                return redirect(url_for('dashboard'))
        else:
            flash('Erro de conexão com a base de dados.')
        
        flash('Login inválido ou pendente.')
    return render_template('login.html')

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nome = request.form['nome']
        email = request.form['email']
        senha = request.form['senha']
        
        try:
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute('INSERT INTO usuarios (nome_completo, email, senha) VALUES (%s, %s, %s)', 
                            (nome, email, generate_password_hash(senha)))
                cursor.close()
                conn.close()
                flash('Aguarde aprovação.')
                return redirect(url_for('login'))
        except Exception as e:
            flash('Email já existe.')
    return render_template('registro.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- ROTAS PRINCIPAIS ---

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: 
        return redirect(url_for('login'))
    
    if request.args.get('limpar'):
        session.pop('filtros_memoria', None)
        return redirect(url_for('dashboard'))

    if request.args:
        filtros_atuais = request.args.to_dict()
        session['filtros_memoria'] = filtros_atuais
    elif 'filtros_memoria' in session:
        return redirect(url_for('dashboard', **session['filtros_memoria']))

    conn = get_db_connection()
    if not conn: 
        return "Erro Base de Dados"

    busca = request.args.get('busca', '')
    f_solicitacao = request.args.get('f_solicitacao', '')
    f_empresa = request.args.get('f_empresa', '')
    f_comprador = request.args.get('f_comprador', '')
    f_status = request.args.get('f_status', '')
    f_data_inicio = request.args.get('f_data_inicio', '')
    f_data_fim = request.args.get('f_data_fim', '')
    
    pagina = request.args.get('page', 1, type=int)
    itens_por_pagina = 10
    offset = (pagina - 1) * itens_por_pagina

    conditions = []
    params = []

    if busca:
        conditions.append("(c.numero_solicitacao LIKE %s OR c.numero_pedido LIKE %s OR c.fornecedor LIKE %s OR c.item_comprado LIKE %s)")
        t = f'%{busca}%'
        params.extend([t, t, t, t])
    
    if f_solicitacao:
        conditions.append("c.numero_solicitacao LIKE %s")
        params.append(f'%{f_solicitacao}%')

    if f_empresa:
        conditions.append("c.codi_empresa = %s")
        params.append(f_empresa)
    
    if f_comprador:
        conditions.append("c.id_comprador_responsavel = %s")
        params.append(f_comprador)
        
    if f_status:
        conditions.append("c.status_compra = %s")
        params.append(f_status)
    
    if f_data_inicio:
        conditions.append("c.data_registro >= %s")
        params.append(f_data_inicio + ' 00:00:00')
    
    if f_data_fim:
        conditions.append("c.data_registro <= %s")
        params.append(f_data_fim + ' 23:59:59')

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    
    sql_joins = """
        FROM acompanhamento_compras c 
        JOIN empresas_compras e ON c.codi_empresa = e.codi_empresa 
        LEFT JOIN usuarios u1 ON c.id_responsavel_chamado = u1.id 
        LEFT JOIN usuarios u2 ON c.id_comprador_responsavel = u2.id
    """

    cursor = conn.cursor()

    cursor.execute(f'SELECT count(*) as total {sql_joins} {where_clause}', params)
    total_registros = cursor.fetchone()['total']
    total_paginas = math.ceil(total_registros / itens_por_pagina)
    
    cursor.execute(f'SELECT c.*, e.nome_empresa, u2.nome_completo as nome_comprador {sql_joins} {where_clause} ORDER BY c.id DESC LIMIT %s OFFSET %s', params + [itens_por_pagina, offset])
    pedidos = cursor.fetchall()

    cursor.execute(f"SELECT c.status_compra, COUNT(*) as qtd {sql_joins} {where_clause} GROUP BY c.status_compra", params)
    dados_status = cursor.fetchall()
    
    where_forn = where_clause + " AND " if where_clause else "WHERE "
    cursor.execute(f"SELECT c.fornecedor, COUNT(*) as qtd {sql_joins} {where_forn} c.status_compra NOT LIKE '%%Entregue%%' GROUP BY c.fornecedor ORDER BY qtd DESC LIMIT 5", params)
    dados_forn = cursor.fetchall()
    
    cursor.execute(f"SELECT u2.nome_completo, COUNT(*) as qtd {sql_joins} {where_forn} c.status_compra NOT LIKE '%%Entregue%%' GROUP BY u2.nome_completo", params)
    dados_comp = cursor.fetchall()

    cursor.execute(f"SELECT c.status_compra, c.prazo_entrega, c.data_entrega_reprogramada {sql_joins} {where_clause}", params)
    all_orders = cursor.fetchall()

    cursor.execute("SELECT * FROM empresas_compras ORDER BY nome_empresa")
    lista_empresas = cursor.fetchall()
    cursor.execute("SELECT * FROM usuarios WHERE nivel_acesso IN ('comprador', 'admin') ORDER BY nome_completo")
    lista_compradores = cursor.fetchall()
    
    cursor.close()
    conn.close()

    kpis = {'total': len(all_orders), 'abertos': 0, 'atrasados': 0}
    timeline_data = defaultdict(int)
    hoje = date.today()
    
    for r in all_orders:
        if 'Entregue' not in r['status_compra']:
            kpis['abertos'] += 1
            dt_val = r['data_entrega_reprogramada'] or r['prazo_entrega']
            if dt_val:
                try:
                    if isinstance(dt_val, str):
                        dt_obj = datetime.strptime(dt_val, '%Y-%m-%d').date()
                    else:
                        dt_obj = dt_val
                    
                    if (dt_obj - hoje).days <= 0:
                        kpis['atrasados'] += 1
                    start_week = dt_obj - timedelta(days=dt_obj.weekday())
                    timeline_data[start_week] += 1
                except:
                    pass

    sorted_dates = sorted(timeline_data.keys())
    
    for p in pedidos:
        s = p['status_compra']
        if s == 'Aguardando Aprovação':
            p.update({'cor_s': '#9b59b6', 'txt_s': 'ORÇAMENTO'})
        elif s in ['Confirmado', 'Orçamento', 'Em Trânsito']:
            p.update({'cor_s': '#3c7ea8', 'txt_s': 'COMPRADO'}) # Azul Oceano
        elif 'Entregue' in s:
            p.update({'cor_s': '#0ca956', 'txt_s': 'ENTREGUE'}) # Verde Nutrane
        else:
            p.update({'cor_s': '#95a5a6', 'txt_s': s})

        dt_val = p['data_entrega_reprogramada'] or p['prazo_entrega']
        p_dt_obj = None
        if dt_val:
            if isinstance(dt_val, str):
                p_dt_obj = datetime.strptime(dt_val, '%Y-%m-%d').date()
            else:
                p_dt_obj = dt_val

        if p_dt_obj and 'Entregue' not in s:
            dias = (p_dt_obj - hoje).days
            if dias <= 0:
                p.update({'cor_p': '#dc3545', 'txt_p': 'ATRASADO'}) # Vermelho Erro
            elif dias <= 2:
                p.update({'cor_p': '#f1c40f', 'txt_p': 'ATENÇÃO'})
            else:
                p.update({'cor_p': '#0ca956', 'txt_p': 'NO PRAZO'}) # Verde Nutrane
        else:
            p.update({'cor_p': 'transparent', 'txt_p': '-'})
        
        if p['prazo_entrega']: 
            if not isinstance(p['prazo_entrega'], str):
                p['prazo_entrega'] = p['prazo_entrega'].strftime('%d/%m/%Y')
        if p['data_entrega_reprogramada']:
            if not isinstance(p['data_entrega_reprogramada'], str):
                p['data_entrega_reprogramada'] = p['data_entrega_reprogramada'].strftime('%d/%m/%Y')

    colors = ['#3c7ea8', '#0ca956', '#f1c40f', '#dc3545', '#9b59b6', '#5d8db5']

    return render_template('dashboard.html', pedidos=pedidos, pagina=pagina, total_paginas=total_paginas,
                           busca=busca, f_solicitacao=f_solicitacao, f_empresa=f_empresa, f_comprador=f_comprador, f_status=f_status,
                           f_data_inicio=f_data_inicio, f_data_fim=f_data_fim,
                           lista_empresas=lista_empresas, lista_compradores=lista_compradores, 
                           lista_status=["Aguardando Aprovação", "Orçamento", "Confirmado", "Em Trânsito", "Entregue Parcialmente", "Entregue Totalmente"],
                           kpis=kpis,
                           graf_status={'labels': [r['status_compra'] for r in dados_status], 'values': [r['qtd'] for r in dados_status], 'colors': colors},
                           graf_forn={'labels': [r['fornecedor'] for r in dados_forn], 'values': [r['qtd'] for r in dados_forn]},
                           graf_comp={'labels': [r['nome_completo'] or 'Sem' for r in dados_comp], 'values': [r['qtd'] for r in dados_comp]},
                           graf_timeline={'labels': [d.strftime('%d/%m') for d in sorted_dates], 'values': [timeline_data[d] for d in sorted_dates]})

# --- ROTA DE PERFORMANCE (COM FILTROS) ---
@app.route('/performance')
def performance():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    conn = get_db_connection()
    if not conn: return "Erro Base de Dados"
    cursor = conn.cursor()

    # 1. Captura Filtros da URL
    f_inicio = request.args.get('inicio', '')
    f_fim = request.args.get('fim', '')
    
    # 2. Monta a cláusula WHERE dinamicamente (baseada em data_registro)
    where_base = ""
    params = []
    
    if f_inicio and f_fim:
        where_base = " AND data_registro BETWEEN %s AND %s"
        params = [f_inicio, f_fim]
    elif f_inicio:
        where_base = " AND data_registro >= %s"
        params = [f_inicio]
    elif f_fim:
        where_base = " AND data_registro <= %s"
        params = [f_fim]

    # --- KPI 1: Lead Time ---
    cursor.execute(f"""
        SELECT AVG(DATEDIFF(data_entrega_real, data_registro)) as media 
        FROM acompanhamento_compras 
        WHERE data_entrega_real IS NOT NULL {where_base}
    """, params)
    res_lead = cursor.fetchone()
    lead_time = round(res_lead['media'] or 0)

    # --- KPI 2: OTIF (Qualidade) ---
    cursor.execute(f"""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN entrega_conforme = 1 THEN 1 ELSE 0 END) as perfeitas,
            SUM(CASE WHEN entrega_conforme = 0 THEN 1 ELSE 0 END) as problemas
        FROM acompanhamento_compras 
        WHERE status_compra LIKE '%%Entregue%%' {where_base}
    """, params)
    dados_otif = cursor.fetchone()
    
    total_entregue = dados_otif['total'] if dados_otif and dados_otif['total'] else 0
    perfeitas = dados_otif['perfeitas'] or 0
    problemas = dados_otif['problemas'] or 0
    pct_otif = round((perfeitas / total_entregue) * 100, 1) if total_entregue > 0 else 0
    nao_avaliados = total_entregue - perfeitas - problemas
    if nao_avaliados < 0: nao_avaliados = 0

    # --- KPI 3: Backlog (Financeiro em Aberto) ---
    cursor.execute(f"""
        SELECT SUM(i.quantidade * i.valor_unitario) as total_money
        FROM pedidos_itens i
        JOIN acompanhamento_compras c ON i.pedido_id = c.id
        WHERE c.status_compra NOT LIKE '%%Entregue%%' {where_base.replace('data_registro', 'c.data_registro')}
    """, params)
    res_backlog = cursor.fetchone()
    backlog_val = res_backlog['total_money'] or 0.0
    backlog_fmt = "{:,.2f}".format(backlog_val).replace(',', 'X').replace('.', ',').replace('X', '.')

    # --- Gráfico 1: Atraso por Unidade ---
    cursor.execute(f"""
        SELECT 
            e.nome_empresa,
            COUNT(*) as total_pedidos,
            SUM(CASE WHEN c.prazo_entrega < CURDATE() AND c.status_compra NOT LIKE '%%Entregue%%' THEN 1 ELSE 0 END) as atrasados
        FROM acompanhamento_compras c
        JOIN empresas_compras e ON c.codi_empresa = e.codi_empresa
        WHERE 1=1 {where_base.replace('AND', 'AND c.')}
        GROUP BY e.nome_empresa
        HAVING total_pedidos > 0
        ORDER BY atrasados DESC
    """, params)
    unidades = cursor.fetchall()
    
    labels_atraso = []
    values_atraso = []
    for u in unidades:
        taxa = (u['atrasados'] / u['total_pedidos']) * 100 if u['total_pedidos'] > 0 else 0
        labels_atraso.append(u['nome_empresa'])
        values_atraso.append(round(taxa, 1))

    # --- Falhas Recentes (Tabela) ---
    cursor.execute(f"""
        SELECT id, fornecedor, data_entrega_real, detalhes_entrega 
        FROM acompanhamento_compras 
        WHERE entrega_conforme = 0 {where_base}
        ORDER BY data_entrega_real DESC LIMIT 10
    """, params)
    falhas = cursor.fetchall()
    
    cursor.close()
    conn.close()

    return render_template('performance.html',
                           kpis={'lead_time': lead_time, 'otif': pct_otif, 'backlog': backlog_fmt},
                           graf_atraso={'labels': labels_atraso, 'dados': values_atraso}, 
                           graf_qualidade=[perfeitas, problemas, nao_avaliados],
                           falhas=falhas,
                           filtro_inicio=f_inicio, 
                           filtro_fim=f_fim)

# --- ROTA PDF (COM FILTROS E NOVO TEMPLATE) ---
@app.route('/download_performance_pdf')
def download_performance_pdf():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    conn = get_db_connection()
    if not conn: return "Erro Base de Dados"
    cursor = conn.cursor()

    # Pega os mesmos filtros da URL (passados pelo botão do HTML)
    f_inicio = request.args.get('inicio', '')
    f_fim = request.args.get('fim', '')
    
    where_base = ""
    params = []
    
    if f_inicio and f_fim:
        where_base = " AND data_registro BETWEEN %s AND %s"
        params = [f_inicio, f_fim]
    elif f_inicio:
        where_base = " AND data_registro >= %s"
        params = [f_inicio]
    elif f_fim:
        where_base = " AND data_registro <= %s"
        params = [f_fim]

    # Recalcula tudo com o filtro para o PDF
    cursor.execute(f"SELECT AVG(DATEDIFF(data_entrega_real, data_registro)) as lead_time FROM acompanhamento_compras WHERE data_entrega_real IS NOT NULL {where_base}", params)
    res_lead = cursor.fetchone()
    lead_time = round(res_lead['lead_time'] or 0)

    cursor.execute(f"SELECT COUNT(*) as total, SUM(CASE WHEN entrega_conforme = 1 THEN 1 ELSE 0 END) as perfeitas FROM acompanhamento_compras WHERE status_compra LIKE '%%Entregue%%' {where_base}", params)
    d_otif = cursor.fetchone()
    total_otif = d_otif['total'] if d_otif and d_otif['total'] else 0
    perfeitas = d_otif['perfeitas'] if d_otif and d_otif['perfeitas'] else 0
    otif = round((perfeitas / total_otif * 100), 1) if total_otif > 0 else 0

    # Listas detalhadas para o PDF
    cursor.execute(f"""
        SELECT c.id, e.nome_empresa, c.fornecedor, c.data_compra, c.prazo_entrega, c.data_entrega_real, c.entrega_conforme, c.detalhes_entrega,
        (SELECT COALESCE(SUM(i.quantidade * i.valor_unitario), 0) FROM pedidos_itens i WHERE i.pedido_id = c.id) as valor_total
        FROM acompanhamento_compras c
        JOIN empresas_compras e ON c.codi_empresa = e.codi_empresa
        WHERE c.status_compra LIKE '%%Entregue%%' {where_base.replace('AND', 'AND c.')}
        ORDER BY c.data_entrega_real DESC
    """, params)
    entregas = cursor.fetchall()

    cursor.execute(f"""
        SELECT c.id, e.nome_empresa, c.fornecedor, c.prazo_entrega, DATEDIFF(CURDATE(), c.prazo_entrega) as dias_atraso,
        (SELECT COALESCE(SUM(i.quantidade * i.valor_unitario), 0) FROM pedidos_itens i WHERE i.pedido_id = c.id) as valor_total
        FROM acompanhamento_compras c
        JOIN empresas_compras e ON c.codi_empresa = e.codi_empresa
        WHERE c.prazo_entrega < CURDATE() AND c.status_compra NOT LIKE '%%Entregue%%' {where_base.replace('AND', 'AND c.')}
        ORDER BY dias_atraso DESC
    """, params)
    atrasos = cursor.fetchall()
    
    cursor.close()
    conn.close()

    html = render_template('pdf_relatorio.html', kpis={'lead_time': lead_time, 'otif': otif}, entregas=entregas, atrasos=atrasos, hoje=date.today().strftime('%d/%m/%Y'))
    pdf_io = BytesIO()
    pisa.CreatePDF(html, dest=pdf_io)
    pdf_io.seek(0)
    
    nome_arquivo = f"Relatorio_Performance_{f_inicio}_ate_{f_fim}.pdf" if f_inicio else f"Relatorio_Geral_{date.today()}.pdf"
    
    return send_file(pdf_io, download_name=nome_arquivo, as_attachment=True)

# --- ROTAS DE CADASTRO E EDIÇÃO ---

@app.route('/nova_compra', methods=['GET', 'POST'])
def nova_compra():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if not conn:
        return "Erro de Base de Dados"
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM empresas_compras')
    empresas = cursor.fetchall()
    cursor.execute('SELECT * FROM usuarios WHERE aprovado = 1')
    usuarios = cursor.fetchall()
    
    dados_form = {}
    
    if request.method == 'POST':
        f = request.form
        names = f.getlist('nome_item[]')
        title = names[0] if names else "Pedido"
        if len(names) > 1: 
            title += f" (+ {len(names)-1} itens)"
        
        # Insere a data manual do input no banco
        cursor.execute('''
            INSERT INTO acompanhamento_compras 
            (data_registro, data_abertura, numero_solicitacao, numero_orcamento, numero_pedido, item_comprado, categoria, 
             fornecedor, data_compra, nota_fiscal, serie_nota, observacao, codi_empresa, 
             id_responsavel_chamado, id_comprador_responsavel, prazo_entrega, status_compra, solicitante_real) 
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ''', (
            f.get('data_registro'), 
            f.get('requisicao'), f.get('solicitacao'), f.get('orcamento'), f.get('pedido'), title, f.get('categoria'), 
            f.get('fornecedor'), f.get('data_compra') or None, f.get('nota'), f.get('serie'), 
            f.get('observacao'), f.get('empresa'), f.get('resp_chamado') or None, 
            f.get('resp_comprador') or None, f.get('prazo') or None, f.get('status'), f.get('solicitante_real')
        ))
        
        pedido_id = cursor.lastrowid
        
        nomes = f.getlist('nome_item[]')
        qtds = f.getlist('qtd[]')
        unids = f.getlist('unidade[]')
        valores = f.getlist('valor[]') 
        
        for i in range(len(nomes)):
            if nomes[i].strip():
                val = safe_float(valores[i]) if i < len(valores) else 0.0
                cursor.execute('''
                    INSERT INTO pedidos_itens (pedido_id, nome_item, quantidade, unidade_medida, valor_unitario) 
                    VALUES (%s, %s, %s, %s, %s)
                ''', (pedido_id, nomes[i], qtds[i], unids[i], val))
        
        salvar_anexos_multiplos(conn, pedido_id, request.files.getlist('arquivo'))
        
        cursor.close()
        conn.close()
        flash('✅ Pedido registado com sucesso!')
        return redirect(url_for('dashboard'))

    cursor.close()
    conn.close()
    return render_template('nova_compra.html', empresas=empresas, usuarios=usuarios, dados_form={})

@app.route('/editar_pedido/<int:id>', methods=['GET', 'POST'])
def editar_pedido(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM acompanhamento_compras WHERE id = %s', (id,))
    pedido = cursor.fetchone()
    cursor.execute('SELECT * FROM usuarios WHERE aprovado = 1 ORDER BY nome_completo')
    usuarios = cursor.fetchall()
    
    if request.method == 'POST':
        f = request.form
        
        names = f.getlist('nome_item[]')
        title = names[0] if names else "Pedido"
        if len(names) > 1: 
            title += f" (+ {len(names)-1} itens)"
        
        ent_conf = f.get('entrega_conforme')
        if ent_conf == '1': ent_conf = 1
        elif ent_conf == '0': ent_conf = 0
        else: ent_conf = None

        cursor.execute('''
            UPDATE acompanhamento_compras SET 
            data_registro=%s, data_abertura=%s, numero_solicitacao=%s, numero_orcamento=%s, numero_pedido=%s, item_comprado=%s, 
            categoria=%s, fornecedor=%s, data_compra=%s, prazo_entrega=%s, data_entrega_reprogramada=%s, 
            nota_fiscal=%s, serie_nota=%s, status_compra=%s, observacao=%s, 
            id_responsavel_chamado=%s, id_comprador_responsavel=%s, solicitante_real=%s, 
            data_entrega_real=%s, entrega_conforme=%s, detalhes_entrega=%s 
            WHERE id=%s
        ''', (
            f.get('data_registro'), 
            f.get('requisicao'), f['solicitacao'], f.get('orcamento'), f.get('pedido'), title, 
            f.get('categoria'), f['fornecedor'], f.get('data_compra') or None, 
            f.get('prazo') or None, f.get('reprogramada') or None, 
            f.get('nota'), f.get('serie'), f['status'], f.get('observacao'), 
            f.get('resp_chamado') or None, f.get('resp_comprador') or None, 
            f.get('solicitante_real'), 
            f.get('data_entrega_real') or None, ent_conf, f.get('detalhes_entrega'), 
            id
        ))
        
        ids = f.getlist('item_id[]')
        nomes = f.getlist('nome_item[]')
        qtds = f.getlist('qtd[]')
        unids = f.getlist('unidade[]')
        vals = f.getlist('valor[]')

        if f.get('itens_para_remover'):
            for rem_id in f.get('itens_para_remover').split(','):
                if rem_id: cursor.execute('DELETE FROM pedidos_itens WHERE id=%s', (rem_id,))
        
        for i in range(len(nomes)):
            if nomes[i].strip():
                val = safe_float(vals[i]) if i < len(vals) else 0.0
                if ids[i]: 
                    cursor.execute('''UPDATE pedidos_itens 
                        SET nome_item=%s, quantidade=%s, unidade_medida=%s, valor_unitario=%s 
                        WHERE id=%s''', (nomes[i], qtds[i], unids[i], val, ids[i]))
                else: 
                    cursor.execute('''INSERT INTO pedidos_itens 
                        (pedido_id, nome_item, quantidade, unidade_medida, valor_unitario) 
                        VALUES (%s, %s, %s, %s, %s)''', (id, nomes[i], qtds[i], unids[i], val))
        
        salvar_anexos_multiplos(conn, id, request.files.getlist('arquivo'))
        cursor.close()
        conn.close()
        flash('✅ Atualizado com sucesso!')
        return redirect(url_for('dashboard'))

    cursor.execute('SELECT * FROM pedidos_itens WHERE pedido_id = %s', (id,))
    itens = cursor.fetchall()
    cursor.execute('SELECT * FROM pedidos_anexos WHERE pedido_id = %s', (id,))
    anexos = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template('editar_pedido.html', pedido=pedido, usuarios=usuarios, anexos=anexos, itens=itens)

@app.route('/excluir_pedido/<int:id>')
def excluir_pedido(id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    if not conn: return "Erro Base de Dados"
    cursor = conn.cursor()
    
    cursor.execute('SELECT nome_arquivo FROM pedidos_anexos WHERE pedido_id=%s',(id,))
    anexos = cursor.fetchall()
    for anexo in anexos:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], anexo['nome_arquivo']))
        except:
            pass
        
    cursor.execute('DELETE FROM acompanhamento_compras WHERE id=%s',(id,))
    cursor.close()
    conn.close()
    flash('Excluído!')
    return redirect(url_for('dashboard'))

@app.route('/excluir_anexo/<int:anexo_id>')
def excluir_anexo(anexo_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT pedido_id, nome_arquivo FROM pedidos_anexos WHERE id=%s',(anexo_id,))
    anexo = cursor.fetchone()
    
    if anexo:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], anexo['nome_arquivo']))
        except:
            pass
        cursor.execute('DELETE FROM pedidos_anexos WHERE id=%s',(anexo_id,))
        cursor.close()
        conn.close()
        flash('Anexo removido!')
        return redirect(url_for('editar_pedido', id=anexo['pedido_id']))
    
    cursor.close()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/ver_pedido/<int:id>')
def ver_pedido(id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor()
    
    sql = '''
        SELECT c.*, e.nome_empresa, u1.nome_completo as nome_solicitante, u2.nome_completo as nome_comprador 
        FROM acompanhamento_compras c 
        LEFT JOIN empresas_compras e ON c.codi_empresa = e.codi_empresa 
        LEFT JOIN usuarios u1 ON c.id_responsavel_chamado = u1.id 
        LEFT JOIN usuarios u2 ON c.id_comprador_responsavel = u2.id 
        WHERE c.id = %s
    '''
    cursor.execute(sql, (id,))
    pedido = cursor.fetchone()
    
    cursor.execute('SELECT * FROM pedidos_itens WHERE pedido_id = %s', (id,))
    itens = cursor.fetchall()
    
    cursor.execute('SELECT * FROM pedidos_anexos WHERE pedido_id = %s', (id,))
    anexos = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('ver_pedido.html', pedido=pedido, itens=itens, anexos=anexos)

@app.route('/importar_solicitacao', methods=['POST'])
def importar_solicitacao():
    if 'arquivo_pdf' not in request.files or request.files['arquivo_pdf'].filename == '':
        flash('Erro no ficheiro.')
        return redirect(url_for('nova_compra'))
    
    file = request.files['arquivo_pdf']
    dados_pdf = {}
    itens_pdf = []
    lista_obs = [] 
    unidades_conhecidas = ['UN', 'PC', 'CX', 'KG', 'M', 'L', 'LITRO', 'METRO', 'PAR', 'UN GERAL']

    try:
        with pdfplumber.open(file) as pdf:
            text = pdf.pages[0].extract_text() or ""
            
            if m := re.search(r'Solicitação de Compra:\s*(\d+)', text):
                dados_pdf['solicitacao'] = m.group(1)
            
            if m := re.search(r'Data:\s*(\d{2}/\d{2}/\d{4})', text): 
                data_br = m.group(1)
                try:
                    dados_pdf['data_registro'] = datetime.strptime(data_br, '%d/%m/%Y').strftime('%Y-%m-%d')
                except:
                    dados_pdf['data_registro'] = None
            
            if m := re.search(r'Empresa:\s*(\d+)', text):
                dados_pdf['empresa'] = m.group(1)
            
            texto_layout = pdf.pages[0].extract_text(layout=True) or ""
            if "Requerente" in texto_layout:
                linhas_layout = texto_layout.split('\n')
                for i, linha in enumerate(linhas_layout):
                    if "Requerente" in linha:
                        for offset in range(1, 4):
                            if i + offset < len(linhas_layout):
                                linha_alvo = linhas_layout[i+offset].strip()
                                if linha_alvo: 
                                    partes = re.split(r'\s{2,}', linha_alvo)
                                    dados_pdf['solicitante_real'] = partes[0]
                                    break
                        break

            lines = text.split('\n')
            for i, line in enumerate(lines):
                if "Observação:" in line:
                    obs_texto = line.split("Observação:", 1)[1].strip()
                    obs_texto = obs_texto.replace('"', '').replace("'", "")
                    if obs_texto:
                        lista_obs.append(obs_texto)
                
                if m := re.search(r'^(\d{2}\.\d{2}\.\d{4})\s+(.+)', line):
                    codigo = m.group(1)
                    resto = m.group(2)
                    
                    tokens = resto.split()
                    qtd = "1"
                    unid = "UN"
                    desc_parts = []
                    encontrou_unidade = False
                    
                    for token in tokens:
                        token_upper = token.upper()
                        if re.match(r'^\d+,\d+$', token):
                            qtd = token.split(',')[0]
                            break 
                        elif token_upper in unidades_conhecidas or (token_upper == 'UN' and 'UN' in token_upper):
                            encontrou_unidade = True
                            if "UN" in token_upper: unid = "UN"
                            elif token_upper == "PC": unid = "PCT"
                            else: unid = token_upper
                            continue 
                        if encontrou_unidade:
                            continue 
                        if not re.match(r'\d+,\d+', token): 
                            desc_parts.append(token)
                    
                    nome_final = f"{codigo} - {' '.join(desc_parts)}"
                    itens_pdf.append({'nome_item': nome_final, 'quantidade': qtd, 'unidade_medida': unid})

    except Exception as e:
        # LOG ADICIONADO AQUI
        app.logger.error(f"Erro ao processar PDF de importação: {e}", exc_info=True)
        print(f"Erro PDF: {e}")
        flash('Erro ao processar PDF.')
    
    if lista_obs:
        dados_pdf['observacao'] = "\n".join(lista_obs)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM empresas_compras')
    empresas = cursor.fetchall()
    cursor.execute('SELECT * FROM usuarios WHERE aprovado = 1')
    usuarios = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return render_template('nova_compra.html', empresas=empresas, usuarios=usuarios, dados_form=dados_pdf, itens_preenchidos=itens_pdf)

@app.route('/admin/usuarios', methods=['GET', 'POST'])
def admin_usuarios():
    if session.get('user_nivel') != 'admin': 
        return redirect(url_for('dashboard'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        acao = request.form.get('acao') # aprovar, excluir, promover, rebaixar
        target_id = request.form.get('user_id')
        
        if str(target_id) == str(session.get('user_id')) and acao in ['excluir', 'rebaixar']:
            flash('⚠️ Você não pode excluir ou rebaixar sua própria conta!')
        else:
            if acao == 'aprovar':
                cursor.execute('UPDATE usuarios SET aprovado=1 WHERE id=%s', (target_id,))
                flash('✅ Usuário aprovado com sucesso!')
            elif acao == 'excluir':
                try:
                    cursor.execute('DELETE FROM usuarios WHERE id=%s', (target_id,))
                    flash('🗑️ Usuário excluído permanentemente.')
                except Exception as e:
                    flash('Erro ao excluir: Usuário possui registos vinculados.')
            elif acao == 'promover':
                cursor.execute("UPDATE usuarios SET nivel_acesso='admin' WHERE id=%s", (target_id,))
                flash('👮 Usuário promovido a ADMIN!')
            elif acao == 'rebaixar':
                cursor.execute("UPDATE usuarios SET nivel_acesso='comprador' WHERE id=%s", (target_id,))
                flash('⬇️ Usuário rebaixado para Comprador.')

            conn.commit()
            return redirect(url_for('admin_usuarios'))
    
    cursor.execute('SELECT * FROM usuarios WHERE aprovado=0')
    pendentes = cursor.fetchall()

    cursor.execute('SELECT * FROM usuarios WHERE aprovado=1 ORDER BY nome_completo')
    ativos = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('admin_usuarios.html', pendentes=pendentes, ativos=ativos)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)