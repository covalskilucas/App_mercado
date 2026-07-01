import streamlit as st
import requests
from datetime import datetime
import pandas as pd
import io
# Importações do ReportLab para o PDF
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Configuração da página Web
st.set_page_config(page_title="Gerenciador de Compras", page_icon="🛒", layout="wide")

URL_BASE_FIREBASE = "https://app-compras-mercado-default-rtdb.firebaseio.com/"

CATEGORIAS = ["Mercearia", "Hortifrúti", "Açougue", "Laticínios / Frios", "Limpeza", "Higiene", "Bebidas", "Padaria", "Outros"]
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
ANO_ATUAL = datetime.now().year
ANOS = [str(ano) for ano in range(ANO_ATUAL - 1, ANO_ATUAL + 4)]

# --- FUNÇÕES DE BANCO DE DADOS (FIREBASE) ---
def carregar_historico_nuvem():
    try:
        resposta = requests.get(f"{URL_BASE_FIREBASE}historico.json", timeout=10)
        if resposta.status_code == 200 and resposta.json() is not None:
            return resposta.json()
    except:
        st.error("Erro ao conectar com o Firebase. Carregando dados locais vazios.")
    return {}

def salvar_historico_nuvem(historico):
    try:
        requests.put(f"{URL_BASE_FIREBASE}historico.json", json=historico, timeout=10)
    except:
        st.error("Não foi possível sincronizar os dados na Nuvem.")

# --- INICIALIZAÇÃO DE ESTADO ---
if "historico" not in st.session_state:
    st.session_state.historico = carregar_historico_nuvem()

# --- INTERFACE WEB ---
st.title("🛒 Gerenciador de Compras Compartilhado")

# Painel de Seleção de Data e Sincronização
col_mes, col_ano, col_sinc = st.columns([2, 1, 2])
with col_mes:
    mes_selecionado = st.selectbox("Mês", MESES, index=datetime.now().month - 1)
with col_ano:
    ano_selecionado = st.selectbox("Ano", ANOS, index=1)

chave_periodo = f"{MESES.index(mes_selecionado)+1:02d}-{ano_selecionado}"

# Garante que a estrutura exista
if chave_periodo not in st.session_state.historico:
    st.session_state.historico[chave_periodo] = {"orcamento": 0.0, "itens": []}
    salvar_historico_nuvem(st.session_state.historico)

dados_mes = st.session_state.historico[chave_periodo]
if "itens" not in dados_mes:
    dados_mes["itens"] = []

with col_sinc:
    st.write("") # Alinhamento visual
    if st.button("🔄 Sincronizar Nuvem", use_container_width=True):
        st.session_state.historico = carregar_historico_nuvem()
        st.success("Sincronizado com sucesso!")
        st.rerun()

# --- ORÇAMENTO E RESUMO FINANCEIRO ---
st.subheader("📊 Painel Financeiro")
orcamento_atual = dados_mes.get("orcamento", 0.0)
novo_orcamento = st.number_input("Definir Orçamento (R$)", min_value=0.0, value=float(orcamento_atual), step=50.0)

if novo_orcamento != orcamento_atual:
    dados_mes["orcamento"] = novo_orcamento
    salvar_historico_nuvem(st.session_state.historico)
    st.rerun()

# Cálculo dos totais baseados nos itens atuais
total_gasto = sum(item['quantidade'] * item['preco'] for item in dados_mes["itens"])
saldo = novo_orcamento - total_gasto

col_orc, col_gast, col_sal = st.columns(3)
col_orc.metric("Orçamento", f"R$ {novo_orcamento:.2f}")
col_gast.metric("Total Gasto", f"R$ {total_gasto:.2f}")
if saldo < 0:
    col_sal.metric("Saldo", f"R$ {saldo:.2f}", delta=f"Estourado em R$ {abs(saldo):.2f}", delta_color="inverse")
else:
    col_sal.metric("Saldo", f"R$ {saldo:.2f}")

# --- TABELA DE EXIBIÇÃO E EDIÇÃO EM MASSA ---
st.subheader("📝 Lista de Compras Atual")

if dados_mes["itens"]:
    # Converte os dados do Firebase em um DataFrame do Pandas
    df_completo = pd.DataFrame(dados_mes["itens"])
    
    # Adiciona ID temporário interno para rastrear as linhas mesmo após filtradas
    df_completo['id_original'] = df_completo.index
    
    # Reorganiza e renomeia as colunas para exibição amigável
    df_completo = df_completo[['id_original', 'carrinho', 'categoria', 'nome', 'quantidade', 'preco']]
    df_completo.columns = ['id_original', 'Pego (Carrinho)', 'Categoria', 'Produto', 'Quantidade', 'Preço Unitário (R$)']
    
    # NOVO: Filtro Dinâmico de Categorias inserido na tela
    categorias_selecionadas = st.multiselect(
        "🔍 Filtrar Lista por Categoria:",
        options=CATEGORIAS,
        default=CATEGORIAS,
        help="Remova ou adicione categorias para limpar a visualização abaixo."
    )
    
    # Aplica o filtro de categoria selecionado pelo usuário
    df_exibicao = df_completo[df_completo['Categoria'].isin(categorias_selecionadas)]
    
    # Calcula dinamicamente o Total por Item para exibição em coluna
    df_exibicao['Total Item (R$)'] = df_exibicao['Quantidade'] * df_exibicao['Preço Unitário (R$)']

    # Renderiza a tabela editável com os filtros aplicados
    tabela_editada = st.data_editor(
        df_exibicao,
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic", # Permite adicionar e deletar linhas
        column_config={
            "id_original": None, # Oculta o ID da tela do usuário
            "Pego (Carrinho)": st.column_config.CheckboxColumn(help="Marque se já pegou o item"),
            "Categoria": st.column_config.SelectboxColumn(options=CATEGORIAS, required=True),
            "Produto": st.column_config.TextColumn(required=True),
            "Quantidade": st.column_config.NumberColumn(min_value=1, step=1, required=True),
            "Preço Unitário (R$)": st.column_config.NumberColumn(min_value=0.0, format="R$ %.2f"),
            "Total Item (R$)": st.column_config.NumberColumn(format="R$ %.2f", disabled=True)
        }
    )

    # Botão para salvar todas as alterações feitas diretamente nas colunas filtradas
    if st.button("💾 Salvar Alterações da Lista", type="primary", use_container_width=True):
        # Reconstrói a lista mapeando as edições com base no ID original para não apagar os dados filtrados
        itens_finais = list(dados_mes["itens"])
        
        # Lista para rastrear quais IDs foram mantidos ou adicionados
        ids_atualizados_ou_novos = []

        for _, row in tabela_editada.iterrows():
            if pd.notna(row['Produto']) and str(row['Produto']).strip() != "":
                item_formatado = {
                    "carrinho": bool(row['Pego (Carrinho)']),
                    "categoria": str(row['Categoria']),
                    "nome": str(row['Produto']).capitalize(),
                    "quantidade": int(row['Quantidade']),
                    "preco": float(row['Preço Unitário (R$)'])
                }
                
                id_orig = row['id_original']
                # Se o item já existia, atualiza na sua respectiva posição original
                if pd.notna(id_orig) and int(id_orig) < len(itens_finais):
                    id_orig = int(id_orig)
                    itens_finais[id_orig] = item_formatado
                    ids_atualizados_ou_novos.append(id_orig)
                else:
                    # Se for um item totalmente novo adicionado na tabela, anexa no fim
                    itens_finais.append(item_formatado)
                    ids_atualizados_ou_novos.append(len(itens_finais) - 1)
        
        # Identifica quais itens dentro das categorias visíveis foram deletados pelo usuário
        ids_deletados = []
        for _, row_original in df_completo[df_completo['Categoria'].isin(categorias_selecionadas)].iterrows():
            if int(row_original['id_original']) not in ids_atualizados_ou_novos:
                ids_deletados.append(int(row_original['id_original']))
                
        # Remove os itens deletados de trás para frente para não quebrar os índices do array
        for id_del in sorted(ids_deletados, reverse=True):
            itens_finais.pop(id_del)

        dados_mes["itens"] = itens_finais
        salvar_historico_nuvem(st.session_state.historico)
        st.success("Lista atualizada e sincronizada com sucesso!")
        st.rerun()

else:
    st.info("Nenhum item adicionado para este período.")
    if st.button("➕ Iniciar Nova Lista"):
        dados_mes["itens"] = [{"carrinho": False, "categoria": "Mercearia", "nome": "Exemplo", "quantidade": 1, "preco": 0.0}]
        salvar_historico_nuvem(st.session_state.historico)
        st.rerun()

# --- EXPORTAR PDF ---
def gerar_pdf_bytes():
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elementos = []
    estilos = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle('T', parent=estilos['Heading1'], fontSize=18, spaceAfter=12)
    estilo_celula = ParagraphStyle('C', parent=estilos['Normal'], fontSize=10)
    
    elementos.append(Paragraph(f"Lista de Compras — {mes_selecionado} / {ano_selecionado}", estilo_titulo))
    
    dados_tabela = [[Paragraph("Status", estilo_celula), Paragraph("Categoria", estilo_celula), Paragraph("Produto", estilo_celula), Paragraph("Qtd", estilo_celula), Paragraph("Preço Un.", estilo_celula), Paragraph("Total", estilo_celula)]]
    
    for item in dados_mes["itens"]:
        status_pdf = "Pego" if item.get("carrinho") else "Pendente"
        total_item = item["quantidade"] * item["preco"]
        dados_tabela.append([
            Paragraph(status_pdf, estilo_celula),
            Paragraph(item["categoria"], estilo_celula),
            Paragraph(item["nome"], estilo_celula),
            Paragraph(str(item["quantidade"]), estilo_celula),
            Paragraph(f"R$ {item['preco']:.2f}", estilo_celula),
            Paragraph(f"R$ {total_item:.2f}", estilo_celula)
        ])
        
    tabela_pdf = Table(dados_tabela)
    tabela_pdf.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.grey), ('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey)]))
    elementos.append(tabela_pdf)
    doc.build(elementos)
    return buffer.getvalue()

if dados_mes["itens"]:
    st.write("---")
    st.download_button(
        label="📄 Baixar Lista Completa em PDF",
        data=gerar_pdf_bytes(),
        file_name=f"Lista_Compras_{chave_periodo}.pdf",
        mime="application/pdf",
        use_container_width=True
    )