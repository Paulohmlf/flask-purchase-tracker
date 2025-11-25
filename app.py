import os
import math
import json
from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, date

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

# --- DASHBOARD COMPLETO ---
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    # 1. Filtros e Paginação
    busca = request.args.get('busca', '')
    pagina = request.args.get('page', 1, type=int)
    itens_por_pagina = 10
    offset = (pagina - 1) * itens_por_pagina
    
    sql_base = ''' FROM acompanhamento_compras c 
                   JOIN empresas_compras e ON c.codi_empresa = e.codi_empresa '''
    where_clause = ''
    params = []
    
    if busca:
        where_clause = ''' WHERE c.numero_solicitacao LIKE ? OR c.numero_pedido LIKE ? 
                           OR c.fornecedor LIKE ? OR c.item_comprado LIKE ? 
                           OR c.status_compra LIKE ? '''
        t = f'%{busca}%'
        params = [t, t, t, t, t]
    
    total_registros = conn.execute(f'SELECT count(*) {sql_base} {where_clause}', params).fetchone()[0]
    total_paginas = math.ceil(total_registros / itens_por_pagina)
    
    sql_final = f''' SELECT c.*, e.nome_empresa {sql_base} {where_clause} 
                     ORDER BY c.id DESC LIMIT ? OFFSET ? '''
    rows = conn.execute(sql_final, params + [itens_por_pagina, offset]).fetchall()
    
    # 2. Dados para Gráficos (Aba Gerencial)
    # Status
    dados_status = conn.execute(
        'SELECT status_compra, COUNT(*) as qtd FROM acompanhamento_compras GROUP BY status_compra'
    ).fetchall()
    labels_status = [row['status_compra'] for row in dados_status]
    values_status = [row['qtd'] for row in dados_status]
    
    # Top Fornecedores
    dados_forn = conn.execute(
        """SELECT fornecedor, COUNT(*) as qtd FROM acompanhamento_compras 
           WHERE status_compra NOT LIKE '%Entregue%' 
           GROUP BY fornecedor ORDER BY qtd DESC LIMIT 5"""
    ).fetchall()
    labels_forn = [row['fornecedor'] for row in dados_forn]
    values_forn = [row['qtd'] for row in dados_forn]
    
    # Compradores
    dados_comp = conn.execute(
        """SELECT u.nome_completo, COUNT(*) as qtd 
           FROM acompanhamento_compras c 
           JOIN usuarios u ON c.id_comprador_responsavel = u.id 
           WHERE c.status_compra NOT LIKE '%Entregue%' 
           GROUP BY u.nome_completo"""
    ).fetchall()
    labels_comp = [row['nome_completo'] for row in dados_comp]
    values_comp = [row['qtd'] for row in dados_comp]
    
    # 3. KPIs Gerais
    kpis = {'total': 0, 'abertos': 0, 'atrasados': 0}
    hoje = date.today()
    all_orders = conn.execute(
        'SELECT status_compra, prazo_entrega, data_entrega_reprogramada FROM acompanhamento_compras'
    ).fetchall()
    
    kpis['total'] = len(all_orders)
    
    for row in all_orders:
        if 'Entregue' not in row['status_compra']:
            kpis['abertos'] += 1
            dt_str = row['data_entrega_reprogramada'] or row['prazo_entrega']
            if dt_str:
                try:
                    if (datetime.strptime(dt_str, '%Y-%m-%d').date() - hoje).days < 0:
                        kpis['atrasados'] += 1
                except:
                    pass
    
    conn.close()
    
    # 4. Processamento Visual da Tabela
    pedidos = [dict(row) for row in rows]
    
    for p in pedidos:
        s = p['status_compra']
        
        if s == 'Aguardando Aprovação':
            p.update({'cor_s': '#9b59b6', 'txt_s': 'ORÇAMENTO'})
        elif s in ['Confirmado', 'Enviado ao Fornecedor', 'Em Trânsito']:
            p.update({'cor_s': '#3498db', 'txt_s': 'COMPRADO'})
        elif 'Entregue' in s:
            p.update({'cor_s': '#2ecc71', 'txt_s': 'ENTREGUE'})
        else:
            p.update({'cor_s': '#95a5a6', 'txt_s': s})
        
        dt_str = p['data_entrega_reprogramada'] or p['prazo_entrega']
        
        if dt_str and 'Entregue' not in s:
            try:
                dias = (datetime.strptime(dt_str, '%Y-%m-%d').date() - hoje).days
                if dias < 0:
                    p.update({'cor_p': '#e74c3c', 'txt_p': 'ATRASADO', 
                             'cor_s': '#e74c3c', 'txt_s': 'ATRASADO'})
                elif dias <= 2:
                    p.update({'cor_p': '#f1c40f', 'txt_p': 'ATENÇÃO'})
                else:
                    p.update({'cor_p': '#2ecc71', 'txt_p': 'NO PRAZO'})
            except:
                p.update({'cor_p': 'transparent', 'txt_p': '-'})
        else:
            p.update({'cor_p': 'transparent', 'txt_p': '-'})
        
        if p['prazo_entrega']:
            p['prazo_entrega'] = datetime.strptime(p['prazo_entrega'], '%Y-%m-%d').strftime('%d/%m/%Y')
        if p['data_entrega_reprogramada']:
            p['data_entrega_reprogramada'] = datetime.strptime(
                p['data_entrega_reprogramada'], '%Y-%m-%d'
            ).strftime('%d/%m/%Y')
    
    # RETORNO CORRIGIDO: enviamos os dicionários completos para o HTML
    return render_template('dashboard.html', 
                         pedidos=pedidos, 
                         pagina=pagina, 
                         total_paginas=total_paginas, 
                         busca=busca, 
                         kpis=kpis,
                         graf_status={'labels': labels_status, 'values': values_status},
                         graf_forn={'labels': labels_forn, 'values': values_forn},
                         graf_comp={'labels': labels_comp, 'values': values_comp})

# --- ROTAS DE CADASTRO E EDIÇÃO ---
@app.route('/nova_compra', methods=['GET', 'POST'])
def nova_compra():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    if request.method == 'POST':
        f = request.form
        arq = request.files.get('arquivo')
        nome_arq = None
        
        if arq and allowed_file(arq.filename):
            nome_arq = secure_filename(f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{arq.filename}")
            arq.save(os.path.join(app.config['UPLOAD_FOLDER'], nome_arq))
        
        conn.execute('''INSERT INTO acompanhamento_compras 
                       (numero_solicitacao, numero_orcamento, numero_pedido, item_comprado, 
                        categoria, fornecedor, data_compra, nota_fiscal, serie_nota, 
                        arquivo_anexo, observacao, codi_empresa, id_responsavel_chamado, 
                        id_comprador_responsavel, prazo_entrega, status_compra) 
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (f['solicitacao'], f['orcamento'], f['pedido'], f['item'], 
                     f.get('categoria'), f['fornecedor'], f['data_compra'] or None, 
                     f['nota'], f['serie'], nome_arq, f.get('observacao'), f['empresa'], 
                     f['resp_chamado'], f['resp_comprador'], f['prazo'] or None, f['status']))
        
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))
    
    empresas = conn.execute('SELECT * FROM empresas_compras').fetchall()
    usuarios = conn.execute('SELECT * FROM usuarios WHERE aprovado = 1').fetchall()
    conn.close()
    
    return render_template('nova_compra.html', empresas=empresas, usuarios=usuarios)

@app.route('/editar_pedido/<int:id>', methods=['GET', 'POST'])
def editar_pedido(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    pedido = conn.execute('SELECT * FROM acompanhamento_compras WHERE id = ?', (id,)).fetchone()
    
    if request.method == 'POST':
        f = request.form
        arq = request.files.get('arquivo')
        nome_arq = pedido['arquivo_anexo']
        
        if arq and allowed_file(arq.filename):
            nome_arq = secure_filename(f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{arq.filename}")
            arq.save(os.path.join(app.config['UPLOAD_FOLDER'], nome_arq))
        
        conn.execute('''UPDATE acompanhamento_compras 
                       SET numero_solicitacao=?, numero_orcamento=?, numero_pedido=?, 
                           item_comprado=?, categoria=?, fornecedor=?, data_compra=?, 
                           prazo_entrega=?, data_entrega_reprogramada=?, nota_fiscal=?, 
                           serie_nota=?, status_compra=?, arquivo_anexo=?, observacao=? 
                       WHERE id=?''',
                    (f['solicitacao'], f['orcamento'], f['pedido'], f['item'], 
                     f.get('categoria'), f['fornecedor'], f['data_compra'] or None, 
                     f['prazo'] or None, f['reprogramada'] or None, f['nota'], 
                     f['serie'], f['status'], nome_arq, f.get('observacao'), id))
        
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))
    
    return render_template('editar_pedido.html', pedido=pedido)

@app.route('/excluir_pedido/<int:id>')
def excluir_pedido(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    p = conn.execute('SELECT arquivo_anexo FROM acompanhamento_compras WHERE id=?', (id,)).fetchone()
    
    if p and p['arquivo_anexo']:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], p['arquivo_anexo']))
        except:
            pass
    
    conn.execute('DELETE FROM acompanhamento_compras WHERE id=?', (id,))
    conn.commit()
    conn.close()
    
    flash('Excluído!')
    return redirect(url_for('dashboard'))

@app.route('/excluir_anexo/<int:id>')
def excluir_anexo(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    p = conn.execute('SELECT arquivo_anexo FROM acompanhamento_compras WHERE id=?', (id,)).fetchone()
    
    if p and p['arquivo_anexo']:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], p['arquivo_anexo']))
        except:
            pass
    
    conn.execute('UPDATE acompanhamento_compras SET arquivo_anexo=NULL WHERE id=?', (id,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('editar_pedido', id=id))

@app.route('/admin/usuarios', methods=['GET', 'POST'])
def admin_usuarios():
    if session.get('user_nivel') != 'admin':
        return redirect(url_for('dashboard'))
    
    conn = get_db_connection()
    
    if request.method == 'POST':
        conn.execute('UPDATE usuarios SET aprovado=1 WHERE id=?', (request.form['user_id'],))
        conn.commit()
    
    pendentes = conn.execute('SELECT * FROM usuarios WHERE aprovado=0').fetchall()
    conn.close()
    
    return render_template('admin_usuarios.html', pendentes=pendentes)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
