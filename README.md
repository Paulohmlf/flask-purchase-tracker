-----

# 🛒 Sistema de Follow Up de Compras (Nutrane)

Este projeto tem como objetivo principal **automatizar e centralizar o monitoramento do ciclo de vida dos pedidos de compra (POs)**, substituindo o acompanhamento manual baseado em planilhas. Ele oferece uma ferramenta de Follow Up em tempo real, facilitando a identificação de gargalos e a tomada de decisões proativas.

-----

## 🌟 Filosofia de Design e Acessibilidade (A11y)

O desenvolvimento deste sistema foi guiado por princípios de **Acessibilidade Digital e Inclusão**, focando em usuários com o mais baixo nível de letramento tecnológico.

  * **Acessibilidade Cognitiva:** Interfaces foram projetadas para serem altamente intuitivas, utilizando:

      * **Design de Cartões (Cards):** Substituímos tabelas complexas por blocos de informação visuais grandes e fáceis de ler, ideal para uso em dispositivos móveis e para reduzir a carga cognitiva.
      * **Fluxo em Passos (Fieldsets):** Formulários longos (e.g., Nova Compra) foram divididos em 2 a 3 blocos temáticos, permitindo que o usuário se concentre em "uma coisa de cada vez".
      * **Microcopy Simples:** Linguagem direta e instruções claras são usadas em rótulos e mensagens de erro (e.g., "Qual é o seu e-mail?", "Data da Compra não pode ser futura").

  * **Prevenção de Erros (Tolerância):**

      * **Modal de Confirmação:** A exclusão de pedidos é protegida por um modal de confirmação em tela cheia, usando cores de alerta (vermelho) e frases que explicitam a consequência ("Esta ação não pode ser desfeita"), eliminando a ambiguidade do `confirm()` nativo.
      * **Retenção de Dados:** Em caso de erro de validação (Back-end), os dados preenchidos são retidos no formulário (Front-end), evitando que o usuário perca o trabalho e tenha que redigitar tudo.

-----

## 📋 Principais Funcionalidades

### Dashboard (Visão Geral)

A tela principal exibe KPIs gerenciais e visuais para acompanhamento:

  * **KPIs:** Pedidos Abertos, Pedidos Totais e Pedidos Atrasados.
  * **Gráficos:** Status dos Pedidos (Distribuição), Top Fornecedores com Pedidos em Aberto, Volume de Pedidos por Comprador e uma Linha do Tempo de Entregas Previstas (semanal).
  * **Filtros Avançados:** Filtro por Comprador, Unidade (Filial), Status e Barra de Pesquisa por número/item.

### Fluxo de Pedidos

  * **Registro:** Permite o cadastro de novos usuários com aprovação pendente, gerenciada pelo Administrador.
  * **Criação/Edição:** Captura todos os dados operacionais cruciais, incluindo Número do Pedido, Número do Orçamento, Item, Fornecedor, Categoria (e.g., ROLAMENTO, SERVIÇO), Notas Fiscais e Observações.
  * **Gestão de Usuários:** Acesso exclusivo para Administradores para aprovar novos usuários pendentes.

-----

## 🛠️ Tecnologias Utilizadas

  * **Back-end:** Python 3.x
  * **Framework:** Flask
  * **Banco de Dados:** SQLite3 (armazenamento local via `database.db`)
  * **Front-end:** HTML5, CSS3 (Acessível), JavaScript
  * **Visualização de Dados:** Chart.js (para geração dos gráficos)

-----

## 🚀 Instalação e Configuração Local

Siga estes passos para configurar e rodar o projeto em sua máquina local.

### 1\. Criar Ambiente Virtual

É recomendado usar um ambiente virtual (`venv`) para isolar as dependências do projeto:

```bash
# Navegue até o diretório do projeto (onde está o app.py)
cd Compras

# Cria o ambiente virtual
python -m venv venv

# Ativa o ambiente virtual
# No Windows:
.\venv\Scripts\activate
# No Linux/macOS:
source venv/bin/activate
```

### 2\. Instalar Dependências

Com o ambiente virtual ativado, instale as bibliotecas Python necessárias listadas no `requirements.txt`:

```bash
pip install -r Compras/requirements.txt
```

### 3\. Inicializar o Banco de Dados

É essencial rodar o script de inicialização para criar o arquivo `database.db` e inserir as tabelas (`usuarios`, `empresas_compras`, `acompanhamento_compras`) e os dados iniciais (Admin e Unidades/Filiais):

```bash
python Compras/init_db.py
```

  * **Nota:** Se o `database.db` já existir, este script apenas atualizará o esquema com as colunas mais recentes (`categoria`, `observacao`, etc.) e garantirá a existência do usuário Admin.

### 4\. Rodar a Aplicação

Inicie o servidor Flask:

```bash
python Compras/app.py
```
