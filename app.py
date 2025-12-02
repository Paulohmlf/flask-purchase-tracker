import os
import math
import json
from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, date, timedelta
from collections import defaultdict
import pdfplumber
import re

app = Flask(__name__)
app.secret_key = 'chave_super_secreta_nutrane'

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

def salvar_anexos_multiplos(conn, pedido_id, files):
    for arq in files:
        if arq and allowed_file(arq.filename) and arq.filename != '':
            nome_original = arq.filename
            nome_seguro = secure_filename(f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{nome_original}")
            arq.save(os.path.join(app.config['UPLOAD_FOLDER'], nome_seguro))
            
            conn.execute('''
                INSERT INTO pedidos_anexos (pedido_id, nome_arquivo, nome_original) 
                VALUES (?, ?, ?)
            ''', (pedido_id, nome_seguro, nome_original))
    conn.commit()

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

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    if request.args.get('limpar'):
        session.pop('filtros_memoria', None)
        return redirect(url_for('dashboard'))

    if request.args:
        filtros_atuais = request.args.to_dict()
        session['filtros_memoria'] = filtros_atuais
        

    elif 'filtros_memoria' in session:
        return redirect(url_for('dashboard', **session['filtros_memoria']))


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
        conditions.append("(c.numero_solicitacao LIKE ? OR c.numero_pedido LIKE ? OR c.fornecedor LIKE ? OR c.item_comprado LIKE ?)")
        t = f'%{busca}%'
        params.extend([t, t, t, t])
    
    if f_solicitacao:
        conditions.append("c.numero_solicitacao LIKE ?")
        params.append(f'%{f_solicitacao}%')

    if f_empresa:
        conditions.append("c.codi_empresa = ?")
        params.append(f_empresa)
    
    if f_comprador:
        conditions.append("c.id_comprador_responsavel = ?")
        params.append(f_comprador)
        
    if f_status:
        conditions.append("c.status_compra = ?")
        params.append(f_status)
    
    if f_data_inicio:
        conditions.append("c.data_registro >= ?")
        params.append(f_data_inicio + ' 00:00:00')
    
    if f_data_fim:
        conditions.append("c.data_registro <= ?")
        params.append(f_data_fim + ' 23:59:59')

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    
    sql_joins = """
        FROM acompanhamento_compras c 
        JOIN empresas_compras e ON c.codi_empresa = e.codi_empresa 
        LEFT JOIN usuarios u1 ON c.id_responsavel_chamado = u1.id 
        LEFT JOIN usuarios u2 ON c.id_comprador_responsavel = u2.id
    """

    total_registros = conn.execute(f'SELECT count(*) {sql_joins} {where_clause}', params).fetchone()[0]
    total_paginas = math.ceil(total_registros / itens_por_pagina)
    
    sql_tabela = f'''
        SELECT c.*, e.nome_empresa, u2.nome_completo as nome_comprador 
        {sql_joins} {where_clause} 
        ORDER BY c.id DESC LIMIT ? OFFSET ?
    '''
    rows = conn.execute(sql_tabela, params + [itens_por_pagina, offset]).fetchall()


    sql_status = f"SELECT c.status_compra, COUNT(*) as qtd {sql_joins} {where_clause} GROUP BY c.status_compra"
    dados_status = conn.execute(sql_status, params).fetchall()
    labels_status = [r['status_compra'] for r in dados_status]
    values_status = [r['qtd'] for r in dados_status]

    where_forn = where_clause + " AND " if where_clause else "WHERE "
    sql_forn = f"SELECT c.fornecedor, COUNT(*) as qtd {sql_joins} {where_forn} c.status_compra NOT LIKE '%Entregue%' GROUP BY c.fornecedor ORDER BY qtd DESC LIMIT 5"
    dados_forn = conn.execute(sql_forn, params).fetchall()
    labels_forn = [r['fornecedor'] for r in dados_forn]
    values_forn = [r['qtd'] for r in dados_forn]

    sql_comp = f"SELECT u2.nome_completo, COUNT(*) as qtd {sql_joins} {where_forn} c.status_compra NOT LIKE '%Entregue%' GROUP BY u2.nome_completo"
    dados_comp = conn.execute(sql_comp, params).fetchall()
    labels_comp = [r['nome_completo'] if r['nome_completo'] else 'Sem Comprador' for r in dados_comp]
    values_comp = [r['qtd'] for r in dados_comp]

    sql_kpis = f"SELECT c.status_compra, c.prazo_entrega, c.data_entrega_reprogramada {sql_joins} {where_clause}"
    all_orders = conn.execute(sql_kpis, params).fetchall()
    
    kpis = {'total': len(all_orders), 'abertos': 0, 'atrasados': 0}
    timeline_data = defaultdict(int)
    hoje = date.today()
    
    for r in all_orders:
        if 'Entregue' not in r['status_compra']:
            kpis['abertos'] += 1
            dt_str = r['data_entrega_reprogramada'] or r['prazo_entrega']
            if dt_str:
                try:
                    dt_obj = datetime.strptime(dt_str, '%Y-%m-%d').date()
                    if (dt_obj - hoje).days <= 0:
                        kpis['atrasados'] += 1
                    start_week = dt_obj - timedelta(days=dt_obj.weekday())
                    timeline_data[start_week] += 1
                except: pass

    sorted_dates = sorted(timeline_data.keys())
    labels_timeline = [d.strftime('%d/%m') for d in sorted_dates]
    values_timeline = [timeline_data[d] for d in sorted_dates]

    lista_empresas = conn.execute("SELECT * FROM empresas_compras ORDER BY nome_empresa").fetchall()
    lista_compradores = conn.execute("SELECT * FROM usuarios WHERE nivel_acesso IN ('comprador', 'admin') ORDER BY nome_completo").fetchall()
    lista_status = ["Aguardando Aprovação", "Orçamento", "Confirmado", "Em Trânsito", "Entregue Parcialmente", "Entregue Totalmente"]

    conn.close()

    pedidos = [dict(row) for row in rows]
    for p in pedidos:
        s = p['status_compra']
        if s == 'Aguardando Aprovação': p.update({'cor_s': '#9b59b6', 'txt_s': 'ORÇAMENTO'})
        elif s in ['Confirmado', 'Orçamento', 'Em Trânsito']: p.update({'cor_s': '#3498db', 'txt_s': 'COMPRADO'})
        elif 'Entregue' in s: p.update({'cor_s': '#2ecc71', 'txt_s': 'ENTREGUE'})
        else: p.update({'cor_s': '#95a5a6', 'txt_s': s})

        dt_str = p['data_entrega_reprogramada'] or p['prazo_entrega']
        if dt_str and 'Entregue' not in s:
            try:
                dias = (datetime.strptime(dt_str, '%Y-%m-%d').date() - hoje).days
                if dias <= 0: p.update({'cor_p': '#e74c3c', 'txt_p': 'ATRASADO', 'cor_s': '#e74c3c', 'txt_s': 'ATRASADO'})
                elif dias <= 2: p.update({'cor_p': '#f1c40f', 'txt_p': 'ATENÇÃO'})
                else: p.update({'cor_p': '#2ecc71', 'txt_p': 'NO PRAZO'})
            except: p.update({'cor_p': 'transparent', 'txt_p': '-'})
        else: p.update({'cor_p': 'transparent', 'txt_p': '-'})
        
        if p['prazo_entrega']: p['prazo_entrega'] = datetime.strptime(p['prazo_entrega'], '%Y-%m-%d').strftime('%d/%m/%Y')
        if p['data_entrega_reprogramada']: p['data_entrega_reprogramada'] = datetime.strptime(p['data_entrega_reprogramada'], '%Y-%m-%d').strftime('%d/%m/%Y')

    return render_template('dashboard.html', pedidos=pedidos, pagina=pagina, total_paginas=total_paginas,
                           busca=busca, f_solicitacao=f_solicitacao, f_empresa=f_empresa, f_comprador=f_comprador, f_status=f_status,
                           f_data_inicio=f_data_inicio, f_data_fim=f_data_fim,
                           lista_empresas=lista_empresas, lista_compradores=lista_compradores, lista_status=lista_status,
                           kpis=kpis,
                           graf_status={'labels': labels_status, 'values': values_status},
                           graf_forn={'labels': labels_forn, 'values': values_forn},
                           graf_comp={'labels': labels_comp, 'values': values_comp},
                           graf_timeline={'labels': labels_timeline, 'values': values_timeline})


@app.route('/nova_compra', methods=['GET', 'POST'])
def nova_compra():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    conn = get_db_connection()
    empresas = conn.execute('SELECT * FROM empresas_compras').fetchall()
    usuarios = conn.execute('SELECT * FROM usuarios WHERE aprovado = 1').fetchall()
    
    dados_form = {}
    
    if request.method == 'POST':
        f = request.form
        dados_form = f
        erros = []
        
        nomes_itens = f.getlist('nome_item[]')
        qtds_itens = f.getlist('qtd[]')
        
        if not nomes_itens or not nomes_itens[0]:
            erros.append("O item a ser comprado é obrigatório.")
        if not f.get('fornecedor'): erros.append("O Fornecedor é obrigatório.")
        if not f.get('solicitacao'): erros.append("O Número da Solicitação é obrigatório.")
        if not f.get('empresa'): erros.append("A Unidade solicitante é obrigatória.")
        
        data_compra_str = f.get('data_compra')
        prazo_str = f.get('prazo')
        hoje = date.today()
        
        if data_compra_str:
            try:
                dt_obj = datetime.strptime(data_compra_str, '%Y-%m-%d').date()
                if dt_obj > hoje: erros.append("Data da Compra não pode ser futura.")
            except: erros.append("Data da Compra inválida.")
            
        if erros:
            for erro in erros: flash(f'🚨 {erro}')
            conn.close()
            return render_template('nova_compra.html', empresas=empresas, usuarios=usuarios, dados_form=dados_form)

        item_titulo = nomes_itens[0]
        if len(nomes_itens) > 1:
            item_titulo += f" (+ {len(nomes_itens)-1} itens)"

        cursor = conn.execute('''
            INSERT INTO acompanhamento_compras (
                numero_solicitacao, numero_orcamento, numero_pedido, item_comprado, categoria, 
                fornecedor, data_compra, nota_fiscal, serie_nota, 
                observacao, codi_empresa, id_responsavel_chamado, id_comprador_responsavel, 
                prazo_entrega, status_compra, solicitante_real
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''', (
            f.get('solicitacao'), f.get('orcamento'), f.get('pedido'), item_titulo, f.get('categoria'), 
            f.get('fornecedor'), f.get('data_compra') or None, f.get('nota'), f.get('serie'), 
            f.get('observacao'), f.get('empresa'), f.get('resp_chamado') or None, f.get('resp_comprador') or None, 
            f.get('prazo') or None, f.get('status'), f.get('solicitante_real')
        ))

        pedido_id = cursor.lastrowid
        
        unidades = f.getlist('unidade[]')
        for i in range(len(nomes_itens)):
            nome = nomes_itens[i]
            qtd = qtds_itens[i] if i < len(qtds_itens) else 1
            unid = unidades[i] if i < len(unidades) else 'UN'
            if nome.strip():
                conn.execute('INSERT INTO pedidos_itens (pedido_id, nome_item, quantidade, unidade_medida) VALUES (?, ?, ?, ?)', (pedido_id, nome, qtd, unid))

        files = request.files.getlist('arquivo')
        salvar_anexos_multiplos(conn, pedido_id, files)
        
        conn.close()
        flash('✅ Pedido registrado com sucesso!')
        return redirect(url_for('dashboard'))

    conn.close()
    return render_template('nova_compra.html', empresas=empresas, usuarios=usuarios, dados_form={})


@app.route('/editar_pedido/<int:id>', methods=['GET', 'POST'])
def editar_pedido(id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    
    pedido = conn.execute('SELECT * FROM acompanhamento_compras WHERE id = ?', (id,)).fetchone()
    usuarios = conn.execute('SELECT * FROM usuarios WHERE aprovado = 1 ORDER BY nome_completo').fetchall()
    
    if request.method == 'POST':
        f = request.form
        
        nomes_itens = f.getlist('nome_item[]')
        novo_titulo = pedido['item_comprado']
        if nomes_itens:
            novo_titulo = nomes_itens[0]
            if len(nomes_itens) > 1:
                novo_titulo += f" (+ {len(nomes_itens)-1} itens)"
        
        conn.execute('''UPDATE acompanhamento_compras SET 
            numero_solicitacao=?, numero_orcamento=?, numero_pedido=?, item_comprado=?, categoria=?, 
            fornecedor=?, data_compra=?, prazo_entrega=?, data_entrega_reprogramada=?, 
            nota_fiscal=?, serie_nota=?, status_compra=?, observacao=?, 
            id_responsavel_chamado=?, id_comprador_responsavel=?, solicitante_real=? 
            WHERE id=?''', 
            (f['solicitacao'], f.get('orcamento'), f.get('pedido'), novo_titulo, f.get('categoria'), 
             f['fornecedor'], f.get('data_compra') or None, f.get('prazo') or None, f.get('reprogramada') or None, 
             f.get('nota'), f.get('serie'), f['status'], f.get('observacao'), 
             f.get('resp_chamado') or None, f.get('resp_comprador') or None, 
             f.get('solicitante_real'),
             id))
        
        ids_itens = f.getlist('item_id[]')
        qtds_itens = f.getlist('qtd[]')
        unidades = f.getlist('unidade[]')
        itens_para_remover = f.get('itens_para_remover')
        if itens_para_remover:
            lista_ids = itens_para_remover.split(',')
            for id_rem in lista_ids:
                if id_rem: conn.execute('DELETE FROM pedidos_itens WHERE id = ?', (id_rem,))
        
        for i in range(len(nomes_itens)):
            item_id = ids_itens[i]
            nome = nomes_itens[i]
            qtd = qtds_itens[i]
            unid = unidades[i]
            if nome.strip():
                if item_id: conn.execute('UPDATE pedidos_itens SET nome_item=?, quantidade=?, unidade_medida=? WHERE id=?', (nome, qtd, unid, item_id))
                else: conn.execute('INSERT INTO pedidos_itens (pedido_id, nome_item, quantidade, unidade_medida) VALUES (?, ?, ?, ?)', (id, nome, qtd, unid))

        files = request.files.getlist('arquivo')
        salvar_anexos_multiplos(conn, id, files)
        
        conn.close()
        flash('✅ Pedido alterado com sucesso!')
        return redirect(url_for('dashboard'))

    itens = conn.execute('SELECT * FROM pedidos_itens WHERE pedido_id = ?', (id,)).fetchall()
    anexos = conn.execute('SELECT * FROM pedidos_anexos WHERE pedido_id = ?', (id,)).fetchall()
    conn.close()
    return render_template('editar_pedido.html', pedido=pedido, usuarios=usuarios, anexos=anexos, itens=itens)


@app.route('/excluir_pedido/<int:id>')
def excluir_pedido(id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    
    anexos = conn.execute('SELECT nome_arquivo FROM pedidos_anexos WHERE pedido_id=?',(id,)).fetchall()
    for anexo in anexos:
        try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], anexo['nome_arquivo']))
        except: pass
        
    conn.execute('DELETE FROM acompanhamento_compras WHERE id=?',(id,)); 
    conn.commit()
    conn.close()
    flash('Excluído!'); return redirect(url_for('dashboard'))

@app.route('/excluir_anexo/<int:anexo_id>')
def excluir_anexo(anexo_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    
    anexo = conn.execute('SELECT pedido_id, nome_arquivo FROM pedidos_anexos WHERE id=?',(anexo_id,)).fetchone()
    if anexo:
        pedido_id = anexo['pedido_id']
        try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], anexo['nome_arquivo']))
        except: pass
        conn.execute('DELETE FROM pedidos_anexos WHERE id=?',(anexo_id,)); 
        conn.commit()
        conn.close()
        flash('Anexo removido!'); 
        return redirect(url_for('editar_pedido', id=pedido_id))
    
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/ver_pedido/<int:id>')
def ver_pedido(id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    
    sql = '''
        SELECT c.*, 
               e.nome_empresa, 
               u_solic.nome_completo as nome_solicitante,
               u_comp.nome_completo as nome_comprador
        FROM acompanhamento_compras c
        LEFT JOIN empresas_compras e ON c.codi_empresa = e.codi_empresa
        LEFT JOIN usuarios u_solic ON c.id_responsavel_chamado = u_solic.id
        LEFT JOIN usuarios u_comp ON c.id_comprador_responsavel = u_comp.id
        WHERE c.id = ?
    '''
    pedido = conn.execute(sql, (id,)).fetchone()
    itens = conn.execute('SELECT * FROM pedidos_itens WHERE pedido_id = ?', (id,)).fetchall()
    anexos = conn.execute('SELECT * FROM pedidos_anexos WHERE pedido_id = ?', (id,)).fetchall()
    
    conn.close()
    if not pedido:
        flash('Pedido não encontrado.')
        return redirect(url_for('dashboard'))

    return render_template('ver_pedido.html', pedido=pedido, itens=itens, anexos=anexos)

@app.route('/importar_solicitacao', methods=['POST'])
def importar_solicitacao():
    if 'arquivo_pdf' not in request.files:
        flash('Nenhum arquivo enviado.')
        return redirect(url_for('nova_compra'))
    
    file = request.files['arquivo_pdf']
    if file.filename == '':
        flash('Nenhum arquivo selecionado.')
        return redirect(url_for('nova_compra'))

    dados_pdf = {}
    itens_pdf = []
    lista_obs_global = []
    
    unidades_conhecidas = ['UN', 'PC', 'CX', 'KG', 'M', 'L', 'LITRO', 'METRO', 'PAR', 'UN GERAL']

    try:
        with pdfplumber.open(file) as pdf:
            page = pdf.pages[0]
            texto_bruto = page.extract_text() or ""
            

            match_solic = re.search(r'Solicitação de Compra:\s*(\d+)', texto_bruto)
            if match_solic: dados_pdf['solicitacao'] = match_solic.group(1)
            
            match_data = re.search(r'Data:\s*(\d{2}/\d{2}/\d{4})', texto_bruto)
            if match_data:
                try: dados_pdf['data_compra'] = datetime.strptime(match_data.group(1), '%d/%m/%Y').strftime('%Y-%m-%d')
                except: pass
            
            match_emp = re.search(r'Empresa:\s*(\d+)', texto_bruto)
            if match_emp: dados_pdf['empresa'] = match_emp.group(1)


            texto_layout = page.extract_text(layout=True) or ""
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


            linhas = texto_bruto.split('\n')
            for i, linha in enumerate(linhas):
                match_prod = re.search(r'^(\d{2}\.\d{2}\.\d{4})\s+(.+)', linha)
                if match_prod:
                    codigo = match_prod.group(1)
                    resto_linha = match_prod.group(2)
                    
                    obs_texto = ""
                    if i + 1 < len(linhas) and "Observação:" in linhas[i+1]:
                        obs_texto = linhas[i+1].replace("Observação:", "").strip()

                    tokens = resto_linha.split()
                    qtd = "1"
                    unid = "UN"
                    descricao_parts = []
                    
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
                            descricao_parts.append(token)
                    
                    desc_produto = " ".join(descricao_parts).strip()
                    nome_item_formatado = f"{codigo} - {desc_produto}"
                    
                    if obs_texto:
                        lista_obs_global.append(f"{codigo} {desc_produto} - {obs_texto}")
                    else:
                        lista_obs_global.append(f"{codigo} {desc_produto}")

                    itens_pdf.append({'nome_item': nome_item_formatado, 'quantidade': qtd, 'unidade_medida': unid})

    except Exception as e:
        print(f"Erro: {e}")
        flash('Erro ao processar PDF.')

    if lista_obs_global:
        dados_pdf['observacao'] = "\n".join(lista_obs_global)

    conn = get_db_connection()
    empresas = conn.execute('SELECT * FROM empresas_compras').fetchall()
    usuarios = conn.execute('SELECT * FROM usuarios WHERE aprovado = 1').fetchall()
    conn.close()

    if itens_pdf:
        flash(f'✅ Sucesso! {len(itens_pdf)} itens carregados.')
    else:
        flash('⚠️ Nenhum item encontrado no PDF.')
    
    return render_template('nova_compra.html', 
                           empresas=empresas, 
                           usuarios=usuarios, 
                           dados_form=dados_pdf, 
                           itens_preenchidos=itens_pdf)

@app.route('/admin/usuarios', methods=['GET', 'POST'])
def admin_usuarios():
    if session.get('user_nivel') != 'admin': return redirect(url_for('dashboard'))
    conn = get_db_connection()
    if request.method == 'POST': conn.execute('UPDATE usuarios SET aprovado=1 WHERE id=?',(request.form['user_id'],)); conn.commit()
    pendentes = conn.execute('SELECT * FROM usuarios WHERE aprovado=0').fetchall(); conn.close()
    return render_template('admin_usuarios.html', pendentes=pendentes)

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)