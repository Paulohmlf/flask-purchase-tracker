import os
import math
import json
from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, date, timedelta
from collections import defaultdict

app = Flask(__name__)
app.secret_key = 'chave_super_secreta_nutrane'

# Configuração de Uploads
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# --- LOGIN E REGISTRO ---
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        senha = request.form['senha']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM usuarios WHERE email = ?', (email,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['senha'], senha) and user['aprovado'] == 1:
            session['user_id'] = user['id']
            session['user_name'] = user['nome_completo']
            session['user_nivel'] = user['nivel_acesso']
            return redirect(url_for('dashboard'))
        
        flash('Login inválido ou pendente.')
    return render_template('login.html')

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nome = request.form['nome']
        email = request.form['email']
        senha = request.form['senha']
        
        if len(senha) < 6:
            flash('Senha curta.')
            return redirect(url_for('registro'))
        
        try:
            conn = get_db_connection()
            conn.execute('INSERT INTO usuarios (nome_completo, email, senha) VALUES (?, ?, ?)', 
                        (nome, email, generate_password_hash(senha)))
            conn.commit()
            conn.close()
            flash('Aguarde aprovação.')
            return redirect(url_for('login'))
        except:
            flash('Email já existe.')
    return render_template('registro.html')

# --- DASHBOARD TURBINADO (COM LINHA DO TEMPO) ---
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    # 1. Captura dos Filtros da URL
    busca = request.args.get('busca', '')
    f_empresa = request.args.get('f_empresa', '')
    f_comprador = request.args.get('f_comprador', '')
    f_status = request.args.get('f_status', '')
    
    pagina = request.args.get('page', 1, type=int)
    itens_por_pagina = 10
    offset = (pagina - 1) * itens_por_pagina

    # 2. Construção Dinâmica do SQL (WHERE)
    conditions = []
    params = []

    if busca:
        conditions.append("(c.numero_solicitacao LIKE ? OR c.numero_pedido LIKE ? OR c.fornecedor LIKE ? OR c.item_comprado LIKE ?)")
        t = f'%{busca}%'
        params.extend([t, t, t, t])
    
    if f_empresa:
        conditions.append("c.codi_empresa = ?")
        params.append(f_empresa)
    
    if f_comprador:
        conditions.append("c.id_comprador_responsavel = ?")
        params.append(f_comprador)
        
    if f_status:
        conditions.append("c.status_compra = ?")
        params.append(f_status)

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    
    sql_joins = """
        FROM acompanhamento_compras c 
        JOIN empresas_compras e ON c.codi_empresa = e.codi_empresa 
        LEFT JOIN usuarios u1 ON c.id_responsavel_chamado = u1.id 
        LEFT JOIN usuarios u2 ON c.id_comprador_responsavel = u2.id
    """

    # 3. Execução das Queries
    
    # A) Tabela Paginada
    total_registros = conn.execute(f'SELECT count(*) {sql_joins} {where_clause}', params).fetchone()[0]
    total_paginas = math.ceil(total_registros / itens_por_pagina)
    
    sql_tabela = f'''
        SELECT c.*, e.nome_empresa, u2.nome_completo as nome_comprador 
        {sql_joins} {where_clause} 
        ORDER BY c.id DESC LIMIT ? OFFSET ?
    '''
    rows = conn.execute(sql_tabela, params + [itens_por_pagina, offset]).fetchall()

    # B) Gráficos Padrão
    sql_status = f"SELECT c.status_compra, COUNT(*) as qtd {sql_joins} {where_clause} GROUP BY c.status_compra"
    dados_status = conn.execute(sql_status, params).fetchall()
    labels_status = [r['status_compra'] for r in dados_status]
    values_status = [r['qtd'] for r in dados_status]

    where_forn = where_clause + " AND " if where_clause else "WHERE "
    sql_forn = f"""
        SELECT c.fornecedor, COUNT(*) as qtd {sql_joins} 
        {where_forn} c.status_compra NOT LIKE '%Entregue%' 
        GROUP BY c.fornecedor ORDER BY qtd DESC LIMIT 5
    """
    dados_forn = conn.execute(sql_forn, params).fetchall()
    labels_forn = [r['fornecedor'] for r in dados_forn]
    values_forn = [r['qtd'] for r in dados_forn]

    sql_comp = f"""
        SELECT u2.nome_completo, COUNT(*) as qtd {sql_joins} 
        {where_forn} c.status_compra NOT LIKE '%Entregue%' 
        GROUP BY u2.nome_completo
    """
    dados_comp = conn.execute(sql_comp, params).fetchall()
    labels_comp = [r['nome_completo'] if r['nome_completo'] else 'Sem Comprador' for r in dados_comp]
    values_comp = [r['qtd'] for r in dados_comp]

    # C) KPIs e Linha do Tempo
    sql_kpis = f"SELECT c.status_compra, c.prazo_entrega, c.data_entrega_reprogramada {sql_joins} {where_clause}"
    all_orders = conn.execute(sql_kpis, params).fetchall()
    
    kpis = {'total': len(all_orders), 'abertos': 0, 'atrasados': 0}
    timeline_data = defaultdict(int) # Dicionário para agrupar datas
    hoje = date.today()
    
    for r in all_orders:
        # KPI Básico
        if 'Entregue' not in r['status_compra']:
            kpis['abertos'] += 1
            dt_str = r['data_entrega_reprogramada'] or r['prazo_entrega']
            if dt_str:
                try:
                    dt_obj = datetime.strptime(dt_str, '%Y-%m-%d').date()
                    if (dt_obj - hoje).days < 0:
                        kpis['atrasados'] += 1
                    
                    # Lógica da Linha do Tempo (Agrupar por Semana)
                    # Pega a data da Segunda-Feira daquela semana
                    start_week = dt_obj - timedelta(days=dt_obj.weekday())
                    timeline_data[start_week] += 1
                except:
                    pass

    # Preparar dados da Linha do Tempo para o Gráfico
    # Ordena as datas cronologicamente
    sorted_dates = sorted(timeline_data.keys())
    labels_timeline = [d.strftime('%d/%m') for d in sorted_dates]
    values_timeline = [timeline_data[d] for d in sorted_dates]

    # 4. Dropdowns
    lista_empresas = conn.execute("SELECT * FROM empresas_compras ORDER BY nome_empresa").fetchall()
    lista_compradores = conn.execute("SELECT * FROM usuarios WHERE nivel_acesso IN ('comprador', 'admin') ORDER BY nome_completo").fetchall()
    lista_status = [
        "Aguardando Aprovação", "Enviado ao Fornecedor", "Confirmado", 
        "Em Trânsito", "Entregue Parcialmente", "Entregue Totalmente"
    ]

    conn.close()

    # Processamento Visual
    pedidos = [dict(row) for row in rows]
    
    for p in pedidos:
        s = p['status_compra']
        if s == 'Aguardando Aprovação': p.update({'cor_s': '#9b59b6', 'txt_s': 'ORÇAMENTO'})
        elif s in ['Confirmado', 'Enviado ao Fornecedor', 'Em Trânsito']: p.update({'cor_s': '#3498db', 'txt_s': 'COMPRADO'})
        elif 'Entregue' in s: p.update({'cor_s': '#2ecc71', 'txt_s': 'ENTREGUE'})
        else: p.update({'cor_s': '#95a5a6', 'txt_s': s})

        dt_str = p['data_entrega_reprogramada'] or p['prazo_entrega']
        
        if dt_str and 'Entregue' not in s:
            try:
                dias = (datetime.strptime(dt_str, '%Y-%m-%d').date() - hoje).days
                if dias < 0: p.update({'cor_p': '#e74c3c', 'txt_p': 'ATRASADO', 'cor_s': '#e74c3c', 'txt_s': 'ATRASADO'})
                elif dias <= 2: p.update({'cor_p': '#f1c40f', 'txt_p': 'ATENÇÃO'})
                else: p.update({'cor_p': '#2ecc71', 'txt_p': 'NO PRAZO'})
            except: p.update({'cor_p': 'transparent', 'txt_p': '-'})
        else: p.update({'cor_p': 'transparent', 'txt_p': '-'})

        if p['prazo_entrega']:
            p['prazo_entrega'] = datetime.strptime(p['prazo_entrega'], '%Y-%m-%d').strftime('%d/%m/%Y')
        if p['data_entrega_reprogramada']:
            p['data_entrega_reprogramada'] = datetime.strptime(p['data_entrega_reprogramada'], '%Y-%m-%d').strftime('%d/%m/%Y')

    return render_template('dashboard.html', 
                           pedidos=pedidos, pagina=pagina, total_paginas=total_paginas,
                           busca=busca, f_empresa=f_empresa, f_comprador=f_comprador, f_status=f_status,
                           lista_empresas=lista_empresas, lista_compradores=lista_compradores, lista_status=lista_status,
                           kpis=kpis,
                           # Gráficos Antigos
                           graf_status={'labels': labels_status, 'values': values_status},
                           graf_forn={'labels': labels_forn, 'values': values_forn},
                           graf_comp={'labels': labels_comp, 'values': values_comp},
                           # NOVO GRÁFICO DE LINHA DO TEMPO
                           graf_timeline={'labels': labels_timeline, 'values': values_timeline})

# --- ROTAS DE CRIAÇÃO/EDIÇÃO ---
@app.route('/nova_compra', methods=['GET', 'POST'])
def nova_compra():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    empresas = conn.execute('SELECT * FROM empresas_compras').fetchall()
    usuarios = conn.execute('SELECT * FROM usuarios WHERE aprovado = 1').fetchall()
    
    # Dicionário para manter os dados no formulário em caso de erro
    dados_form = {}
    
    if request.method == 'POST':
        f = request.form
        dados_form = f # Salva o formulário para passar de volta
        
        # --- VALIDAÇÃO DE ACESSIBILIDADE E PREVENÇÃO DE ERROS ---
        erros = []
        
        # 1. Campos obrigatórios (item, fornecedor, solicitacao, empresa)
        # Note: Estamos usando f.get() aqui, mas validando que o valor não seja None/Vazio.
        if not f.get('item'): erros.append("O item a ser comprado (O que é?) é obrigatório.")
        if not f.get('fornecedor'): erros.append("O Fornecedor (Quem vende?) é obrigatório.")
        if not f.get('solicitacao'): erros.append("O Número da Solicitação é obrigatório.")
        if not f.get('empresa'): erros.append("A Unidade (Loja) solicitante é obrigatória. Por favor, selecione uma.")
        
        # 2. Validação de Datas
        data_compra_str = f.get('data_compra')
        prazo_str = f.get('prazo')
        
        data_compra_obj = None
        prazo_obj = None
        hoje = date.today()
        
        # Tenta converter e validar a Data da Compra
        if data_compra_str:
            try:
                data_compra_obj = datetime.strptime(data_compra_str, '%Y-%m-%d').date()
                if data_compra_obj > hoje:
                    erros.append("A Data da Compra não pode ser uma data futura. Corrija este campo.")
            except ValueError:
                erros.append("Formato da Data da Compra é inválido. Tente novamente.")

        # Tenta converter o Prazo de Entrega
        if prazo_str:
            try:
                prazo_obj = datetime.strptime(prazo_str, '%Y-%m-%d').date()
            except ValueError:
                erros.append("Formato do Prazo de Entrega é inválido. Tente novamente.")
            
        # 3. Validação de Lógica Temporal
        if data_compra_obj and prazo_obj:
            if prazo_obj < data_compra_obj:
                erros.append("O Prazo de Entrega não pode ser anterior à Data da Compra. Por favor, ajuste as datas.")
        
        # --- SE HOUVER ERROS, RETORNA E MANTÉM OS DADOS ---
        if erros:
            for erro in erros:
                flash(f'🚨 ATENÇÃO: {erro}')
            
            # Recarrega a página passando os dados atuais do formulário
            conn.close()
            return render_template('nova_compra.html', 
                                   empresas=empresas, 
                                   usuarios=usuarios, 
                                   dados_form=dados_form) # Passa os dados preenchidos

        # --- SE NÃO HOUVER ERROS, PROSSEGUE COM UPLOAD E DB ---
        
        # Lógica de Upload de Arquivo
        arq = request.files.get('arquivo')
        nome_arq = None
        if arq and allowed_file(arq.filename):
            nome_arq = secure_filename(f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{arq.filename}")
            arq.save(os.path.join(app.config['UPLOAD_FOLDER'], nome_arq))
            
        # Inserção no Banco de Dados: Usando f.get() para todos os campos opcionais.
        conn.execute('''
            INSERT INTO acompanhamento_compras (
                numero_solicitacao, numero_orcamento, numero_pedido, item_comprado, categoria, 
                fornecedor, data_compra, nota_fiscal, serie_nota, arquivo_anexo, 
                observacao, codi_empresa, id_responsavel_chamado, id_comprador_responsavel, 
                prazo_entrega, status_compra
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''', (
            f.get('solicitacao'), f.get('orcamento'), f.get('pedido'), f.get('item'), f.get('categoria'), 
            f.get('fornecedor'), f.get('data_compra') or None, f.get('nota'), f.get('serie'), nome_arq, 
            f.get('observacao'), f.get('empresa'), f.get('resp_chamado') or None, f.get('resp_comprador') or None, 
            f.get('prazo') or None, f.get('status')
        ))
        conn.commit()
        conn.close()
        flash('✅ Pedido de Compra registrado com sucesso!')
        return redirect(url_for('dashboard'))

    # Caso GET (Primeira entrada na página)
    conn.close()
    # Passa um dict vazio para que o template não quebre ao tentar acessar 'dados_form'
    return render_template('nova_compra.html', empresas=empresas, usuarios=usuarios, dados_form={})

@app.route('/editar_pedido/<int:id>', methods=['GET', 'POST'])
def editar_pedido(id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    
    pedido = conn.execute('SELECT * FROM acompanhamento_compras WHERE id = ?', (id,)).fetchone()
    usuarios = conn.execute('SELECT * FROM usuarios WHERE aprovado = 1 ORDER BY nome_completo').fetchall()
    
    if request.method == 'POST':
        f = request.form; arq = request.files.get('arquivo'); nome_arq = pedido['arquivo_anexo']
        if arq and allowed_file(arq.filename):
            nome_arq = secure_filename(f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{arq.filename}")
            arq.save(os.path.join(app.config['UPLOAD_FOLDER'], nome_arq))
        
        conn.execute('''UPDATE acompanhamento_compras SET numero_solicitacao=?, numero_orcamento=?, numero_pedido=?, item_comprado=?, categoria=?, fornecedor=?, data_compra=?, prazo_entrega=?, data_entrega_reprogramada=?, nota_fiscal=?, serie_nota=?, status_compra=?, arquivo_anexo=?, observacao=?, id_responsavel_chamado=?, id_comprador_responsavel=? WHERE id=?''', 
                     (f['solicitacao'], f.get('orcamento'), f.get('pedido'), f['item'], f.get('categoria'), f['fornecedor'], f.get('data_compra') or None, f.get('prazo') or None, f.get('reprogramada') or None, f.get('nota'), f.get('serie'), f['status'], nome_arq, f.get('observacao'), 
                      f.get('resp_chamado') or None, f.get('resp_comprador') or None, 
                      id))
        
        conn.commit(); conn.close(); return redirect(url_for('dashboard'))
    
    conn.close()
    return render_template('editar_pedido.html', pedido=pedido, usuarios=usuarios)

@app.route('/excluir_pedido/<int:id>')
def excluir_pedido(id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection(); p = conn.execute('SELECT arquivo_anexo FROM acompanhamento_compras WHERE id=?',(id,)).fetchone()
    if p and p['arquivo_anexo']: 
        try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], p['arquivo_anexo']))
        except: pass
    conn.execute('DELETE FROM acompanhamento_compras WHERE id=?',(id,)); conn.commit(); conn.close()
    flash('Excluído!'); return redirect(url_for('dashboard'))

@app.route('/excluir_anexo/<int:id>')
def excluir_anexo(id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection(); p = conn.execute('SELECT arquivo_anexo FROM acompanhamento_compras WHERE id=?',(id,)).fetchone()
    if p and p['arquivo_anexo']:
        try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], p['arquivo_anexo']))
        except: pass
        conn.execute('UPDATE acompanhamento_compras SET arquivo_anexo=NULL WHERE id=?',(id,)); conn.commit()
    conn.close(); return redirect(url_for('editar_pedido', id=id))

@app.route('/admin/usuarios', methods=['GET', 'POST'])
def admin_usuarios():
    if session.get('user_nivel') != 'admin': return redirect(url_for('dashboard'))
    conn = get_db_connection()
    if request.method == 'POST': conn.execute('UPDATE usuarios SET aprovado=1 WHERE id=?',(request.form['user_id'],)); conn.commit()
    pendentes = conn.execute('SELECT * FROM usuarios WHERE aprovado=0').fetchall(); conn.close()
    return render_template('admin_usuarios.html', pendentes=pendentes)

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))

if __name__ == '__main__': app.run(debug=True)