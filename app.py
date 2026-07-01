import streamlit as st
import requests
from datetime import datetime
import pandas as pd
import io
import time
import re
import cv2
import numpy as np
import easyocr  # Nova biblioteca para ler o texto da imagem

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

# Inicializa o leitor de OCR (Carrega em cache para ficar rápido)
@st.cache_resource
def inicializar_ocr():
    return easyocr.Reader(['pt']) # Configurado para ler português e números

leitor_ocr = inicializar_ocr()

# --- FUNÇÕES DE BANCO DE DADOS (FIREBASE) ---
def carregar_historico_nuvem():
    try:
        resposta = requests.get(f"{URL_BASE_FIREBASE}historico.json", timeout=5)
        if resposta.status_code == 200 and resposta.json() is not None:
            return resposta.json()
    except:
        pass
    return {}

def salvar_historico_nuvem(historico):
    try:
        requests.put(f"{URL_BASE_FIREBASE}historico.json", json=historico, timeout=5)
    except:
        st.error("Não foi possível sincronizar os dados na Nuvem.")

# --- FUNÇÃO DE SALVAMENTO AUTOMÁTICO ---
def salvar_mudancas_automatico():
    if "tabela_compras" in st.session_state and st.session_state.tabela_compras:
        mudancas = st.session_state.tabela_compras
        itens_finais = list(st.session_state.historico[chave_periodo]["itens"])
        
        if mudancas.get("edited_rows"):
            for idx_exibicao, colunas_alteradas in mudancas["edited_rows"].items():
                id_orig = st.session_state.df_atual_exibicao.iloc[int(idx_exibicao)]['id_original']
                mapeamento = {"Pego (Carrinho)": "carrinho", "Categoria": "categoria", "Produto": "nome", "Quantidade": "quantidade", "Preço Unitário (R$)": "preco"}
                for col_pt, col_en in mapeamento.items():
                    if col_pt in colunas_alteradas:
                        valor = colunas_alteradas[col_pt]
                        if col_en == "nome" and valor:
                            valor = str(valor).capitalize()
                        itens_finais[int(id_orig)][col_en] = valor

        if mudancas.get("added_rows"):
            for linha_nova in mudancas["added_rows"]:
                if linha_nova.get("Produto"):
                    itens_finais.append({
                        "carrinho": bool(linha_nova.get("Pego (Carrinho)", False)),
                        "categoria": str(linha_nova.get("Categoria", "Mercearia")),
                        "nome": str(linha_nova.get("Produto")).capitalize(),
                        "quantidade": int(linha_nova.get("Quantidade", 1)),
                        "preco": float(linha_nova.get("Preço Unitário (R$)", 0.0))
                    })

        if mudancas.get("deleted_rows"):
            ids_deletar = [st.session_state.df_atual_exibicao.iloc[int(idx)]['id_original'] for idx in mudancas["deleted_rows"]]
            for id_del in sorted(ids_deletar, reverse=True):
                itens_finais.pop(int(id_del))

        st.session_state.historico[chave_periodo]["itens"] = itens_finais
        salvar_historico_nuvem(st.session_state.historico)

# --- INICIALIZAÇÃO DE ESTADO ---
if "historico" not in st.session_state:
    st.session_state.historico = carregar_historico_nuvem()

# --- INTERFACE WEB ---
st.title("🛒 Gerenciador de Compras Compartilhado")

# Painel de Seleção de Data
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
    st.write("") 
    if st.button("🔄 Forçar Sincronização", use_container_width=True):
        st.session_state.historico = carregar_historico_nuvem()
        st.success("Dados atualizados da Nuvem!")
        st.rerun()

# --- ORÇAMENTO E RESUMO FINANCEIRO ---
st.subheader("📊 Painel Financeiro")
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

# --- NOVO: CAPTURA DE PREÇO PELA CÂMERA DO CELULAR ---
st.write("---")
with st.expander("📷 Capturar Preço pela Câmera do Celular", expanded=False):
    st.write("Tire uma foto nítida e de perto da etiqueta de preço na prateleira do mercado.")
    
    # Ativa o componente de câmera nativa do smartphone
    foto_camera = st.camera_input("Apontar câmera para o preço")
    
    if foto_camera is not None:
        # Converte o arquivo de imagem enviado para o formato OpenCV
        bytes_imagem = foto_camera.getvalue()
        cv_img = cv2.imdecode(np.frombuffer(bytes_imagem, np.uint8), cv2.IMREAD_COLOR)
        
        # Executa a leitura OCR na imagem capturada
        with st.spinner("Processando e identificando valores..."):
            resultados_texto = leitor_ocr.readtext(cv_img, detail=0)
            
            # Filtro por Expressão Regular para extrair padrões numéricos de preço (ex: 5,99, 12.50, R$ 4,50)
            precos_encontrados = []
            for texto in resultados_texto:
                # Limpa espaços e caracteres comuns de cifrão
                texto_limpo = texto.replace("R$", "").replace(" ", "").strip()
                # Procura padrões de números decimais com vírgula ou ponto
                padrao = re.findall(r'\d+[\.,]\d{2}', texto_limpo)
                for preco in padrao:
                    preco_float = float(preco.replace(",", "."))
                    if preco_float > 0 and preco_float not in precos_encontrados:
                        precos_encontrados.append(preco_float)
            
            if precos_encontrados:
                st.success(f"Valores detectados na imagem: {['R$ '+str(p) for p in precos_encontrados]}")
                
                # Permite associar o preço lido a um item existente ou criar um novo
                st.write("**O que deseja fazer com o valor detectado?**")
                preco_selecionado = st.selectbox("Selecione o preço correto:", precos_encontrados)
                
                nome_novo_produto = st.text_input("Nome do Produto (Para adicionar novo ou atualizar):", placeholder="Ex: Arroz 5kg")
                categoria_novo_produto = st.selectbox("Categoria:", CATEGORIAS)
                
                if st.button("➕ Inserir/Atualizar Produto com este Preço", type="primary"):
                    if nome_novo_produto:
                        nome_formatado = nome_novo_produto.strip().capitalize()
                        itens_finais = list(dados_mes["itens"])
                        
                        # Verifica se o item já existe para atualizar o preço, senão cria um novo
                        encontrado = False
                        for item in itens_finais:
                            if item["nome"].lower() == nome_formatado.lower():
                                item["preco"] = preco_selecionado
                                encontrado = True
                                break
                        
                        if not encontrado:
                            itens_finais.append({
                                "carrinho": False,
                                "categoria": categoria_novo_produto,
                                "nome": nome_formatado,
                                "quantidade": 1,
                                "preco": preco_selecionado
                            })
                        
                        dados_mes["itens"] = itens_finais
                        salvar_historico_nuvem(st.session_state.historico)
                        st.toast("Preço salvo com sucesso!", icon="✅")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.warning("Por favor, digite o nome do produto antes de salvar.")
            else:
                st.error("Nenhum preço nítido foi detectado. Tente aproximar mais a câmera ou melhorar a iluminação.")

# --- TABELA DE EXIBIÇÃO E EDIÇÃO EM MASSA ---
st.subheader("📝 Lista de Compras Atual")

if dados_mes["itens"]:
    df_completo = pd.DataFrame(dados_mes["itens"])
    df_completo['id_original'] = df_completo.index
    df_completo = df_completo[['id_original', 'carrinho', 'categoria', 'nome', 'quantidade', 'preco']]
    df_completo.columns = ['id_original', 'Pego (Carrinho)', 'Categoria', 'Produto', 'Quantidade', 'Preço Unitário (R$)']
    
    categorias_selecionadas = st.multiselect("🔍 Filtrar Lista por Categoria:", options=CATEGORIAS, default=CATEGORIAS)
    
    df_exibicao = df_completo[df_completo['Categoria'].isin(categorias_selecionadas)].copy()
    df_exibicao['Total Item (R$)'] = df_exibicao['Quantidade'] * df_exibicao['Preço Unitário (R$)']
    
    st.session_state.df_atual_exibicao = df_exibicao

    st.data_editor(
        df_exibicao,
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic",
        key="tabela_compras",
        on_change=salvar_mudancas_automatico,
        column_config={
            "id_original": None,
            "Pego (Carrinho)": st.column_config.CheckboxColumn(),
            "Categoria": st.column_config.SelectboxColumn(options=CATEGORIAS, required=True),
            "Produto": st.column_config.TextColumn(required=True),
            "Quantidade": st.column_config.NumberColumn(min_value=1, step=1, required=True),
            "Preço Unitário (R$)": st.column_config.NumberColumn(min_value=0.0, format="R$ %.2f"),
            "Total Item (R$)": st.column_config.NumberColumn(format="R$ %.2f", disabled=True)
        }
    )
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
            Paragraph(status_pdf, estilo_celula), Paragraph(item["categoria"], estilo_celula),
            Paragraph(item["nome"], estilo_celula), Paragraph(str(item["quantidade"]), estilo_celula),
            Paragraph(f"R$ {item['preco']:.2f}", estilo_celula), Paragraph(f"R$ {total_item:.2f}", estilo_celula)
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

# --- AUTO-REFRESH DE LEITURA (2 SEGUNDOS) ---
time.sleep(2)
dados_nuvem = carregar_historico_nuvem()
if dados_nuvem and dados_nuvem != st.session_state.historico:
    st.session_state.historico = dados_nuvem
    st.rerun()