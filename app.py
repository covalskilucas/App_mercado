import streamlit as st
import requests
from datetime import datetime
import re
import io
# Importações do ReportLab para o PDF
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Configuração da página Web
st.set_page_config(page_title="Gerenciador de Compras Compartilhado", page_icon="🛒", layout="wide")

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
st.title("🛒 Gerenciador de Compras Compartilhado (Nuvem)")

# Painel de Seleção de Data e Sincronização
col_mes, col_ano, col_sinc = st.columns([2, 1, 2])
with col_mes:
    mes_selecionado = st.selectbox("Mês", MESES, index=datetime.now().month - 1)
with col_ano:
    ano_selecionado = st.selectbox("Ano", ANOS, index=1)

chave_periodo = f"{MESES.index(mes_selecionado)+1:02d}-{ano_selecionado}"

if chave_periodo not in st.session_state.historico:
    st.session_state.historico[chave_periodo] = {"orcamento": 0.0, "itens": []}
    salvar_historico_nuvem(st.session_state.historico)

dados_mes = st.session_state.historico[chave_periodo]
if "itens" not in dados_mes:
    dados_mes["itens"] = []

with col_sinc:
    st.write("") # Alinhamento
    if st.button("🔄 Sincronizar Nuvem", use_container_width=True):
        st.session_state.historico = carregar_historico_nuvem()
        st.rerun()

# --- FORMULÁRIO DE ENTRADA ---
st.subheader("Adicionar Novo Item")
with st.form("novo_item_form", clear_on_submit=True):
    col_nome, col_qtd, col_preco, col_cat = st.columns([3, 1, 2, 2])
    with col_nome:
        nome_prod = st.text_input("Produto (ex: Arroz)")
    with col_qtd:
        qtd_prod = st.number_input("Qtd", min_value=1, value=1, step=1)
    with col_preco:
        preco_prod = st.text_input("Preço Un. (Opcional)", value="0.00")
    with col_cat:
        cat_prod = st.selectbox("Categoria", CATEGORIAS)
    
    btn_inserir = st.form_submit_button("Inserir Item")
    
    if btn_inserir and nome_prod:
        try:
            preco_float = float(preco_prod.replace(",", "."))
            novo_item = {"nome": nome_prod.capitalize(), "quantidade": int(qtd_prod), "preco": preco_float, "categoria": cat_prod, "carrinho": False}
            dados_mes["itens"].append(novo_item)
            salvar_historico_nuvem(st.session_state.historico)
            st.success(f"'{nome_prod}' adicionado!")
            st.rerun()
        except ValueError:
            st.error("Preço inválido.")

# --- ORÇAMENTO E RESUMO ---
st.subheader("Resumo Financeiro")
orcamento_atual = dados_mes.get("orcamento", 0.0)
novo_orcamento = st.number_input("Definir Orçamento (R$)", min_value=0.0, value=float(orcamento_atual), step=50.0)
if novo_orcamento != orcamento_atual:
    dados_mes["orcamento"] = novo_orcamento
    salvar_historico_nuvem(st.session_state.historico)
    st.rerun()

total_gasto = sum(item['quantidade'] * item['preco'] for item in dados_mes["itens"])
saldo = novo_orcamento - total_gasto

col_orc, col_gast, col_sal = st.columns(3)
col_orc.metric("Orçamento", f"R$ {novo_orcamento:.2f}")
col_gast.metric("Total Gasto", f"R$ {total_gasto:.2f}")
if saldo < 0:
    col_sal.metric("Saldo", f"R$ {saldo:.2f}", delta=f"Estourado em R$ {abs(saldo):.2f}", delta_color="inverse")
else:
    col_sal.metric("Saldo", f"R$ {saldo:.2f}")

# --- TABELA DE ITENS COM INTERAÇÃO ---
st.subheader("Lista de Compras")
if dados_mes["itens"]:
    for idx, item in enumerate(dados_mes["itens"]):
        col_status, col_desc, col_p, col_del = st.columns([2, 4, 2, 1])
        
        with col_status:
            # Checkbox para marcar se já está no carrinho
            status_check = st.checkbox("🛒 Pego" if item.get("carrinho") else "⏳ Pendente", value=item.get("carrinho"), key=f"check_{idx}")
            if status_check != item.get("carrinho"):
                item["carrinho"] = status_check
                salvar_historico_nuvem(st.session_state.historico)
                st.rerun()
                
        with col_desc:
            st.markdown(f"**{item['nome']}** ({item['categoria']}) — Qtd: {item['quantidade']}")
            
        with col_p:
            # Inputs diretos na tela para ajustar preço
            novo_p = st.number_input(f"Preço Un.", min_value=0.0, value=float(item['preco']), key=f"preco_{idx}", step=0.1)
            if novo_p != item['preco']:
                item['preco'] = novo_p
                salvar_historico_nuvem(st.session_state.historico)
                st.rerun()
                
        with col_del:
            if st.button("❌", key=f"del_{idx}"):
                dados_mes["itens"].pop(idx)
                salvar_historico_nuvem(st.session_state.historico)
                st.rerun()
else:
    st.info("Nenhum item adicionado para este período.")

# --- EXPORTAR PDF (DOWNLOAD DIRETO NO NAVEGADOR) ---
def gerar_pdf_bytes():
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=54)
    elementos = []
    estilos = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle('T', parent=estilos['Heading1'], fontSize=20, spaceAfter=15)
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
    st.download_button(
        label="📄 Baixar Lista em PDF",
        data=gerar_pdf_bytes(),
        file_name=f"Lista_Compras_{chave_periodo}.pdf",
        mime="application/pdf",
        use_container_width=True
    )