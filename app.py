import streamlit as st
import pandas as pd
import plotly.express as px
import io
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

# 1. CONFIGURACIÓN DE MARCA Y ESTILO
st.set_page_config(page_title="Cabify Risk Intelligence", page_icon="🚗", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .main { background-color: #FDFDFF; }
    .stMetric { background-color: #ffffff; border-radius: 10px; padding: 15px; border: 1px solid #E0E0E0; }
    div[data-testid="stMetricValue"] { color: #7350FF; font-weight: 700; }
    h1, h2, h3 { color: #1F1F1F; letter-spacing: -0.5px; }
    </style>
""", unsafe_allow_html=True)

# 2. LÓGICA DE CLASIFICACIÓN
def clasificar_mencion(texto):
    if not isinstance(texto, str): return "Desconocido"
    t = texto.lower()
    if any(p in t for p in ["ley uber", "bencina", "gobierno", "ministro", "noticia"]): return "Ruido Mediático"
    if any(p in t for p in ["cobro", "tarifa", "cobraron", "estafa", "robo", "promoción"]): return "Cobros y Tarifas"
    if any(p in t for p in ["aire", "calor", "conductor", "rasca", "pésimo", "grosero"]): return "Calidad de Servicio"
    if any(p in t for p in ["espera", "toman", "cancel", "demora", "no llega", "app"]): return "Disponibilidad / App"
    if any(p in t for p in ["penca", "callampa", "ctm", "hoyo", "weas", "qlo"]): return "Frustración Crítica"
    return "Otros / Consulta"

# 3. LECTURA BLINDADA
def load_data(file):
    try:
        content = file.read()
        if file.name.endswith(('.xlsx', '.xls')) or content.startswith(b'PK\x03\x04'):
            df = pd.read_excel(io.BytesIO(content), engine='openpyxl')
            if 'Snippet' not in df.columns:
                for i in range(1, 20):
                    df = pd.read_excel(io.BytesIO(content), skiprows=i, engine='openpyxl')
                    if any(c in [str(x).lower() for x in df.columns] for c in ['snippet', 'full text']): break
            return df
        else:
            for enc in ['utf-8', 'utf-8-sig', 'latin1']:
                try:
                    text = content.decode(enc)
                    lines = text.split('\n')
                    skip = 0
                    for i, line in enumerate(lines[:25]):
                        if 'Snippet' in line or 'Full Text' in line:
                            skip = i
                            break
                    return pd.read_csv(io.StringIO(text), skiprows=skip, sep=None, engine='python')
                except: continue
    except Exception as e:
        st.error(f"Error al cargar: {e}")
    return None

# 4. FUNCIONES DE EXPORTACIÓN (PDF Y EXCEL FILTRADO)
def generar_excel_negativos(df_completo):
    # Filtramos para que solo incluya las categorías de riesgo (negativas)
    categorias_riesgo = ["Cobros y Tarifas", "Calidad de Servicio", "Disponibilidad / App", "Frustración Crítica"]
    df_negativos = df_completo[df_completo['Categoría'].isin(categorias_riesgo)].copy()
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_negativos.to_excel(writer, index=False, sheet_name='Casos_Criticos_Support')
    return output.getvalue()

def generar_pdf(df_risk):
    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=landscape(A4), topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    
    style_title = ParagraphStyle('Title', fontSize=24, textColor=colors.HexColor("#7350FF"), leading=30, fontWeight='Bold')
    style_sub = ParagraphStyle('Sub', fontSize=12, textColor=colors.grey, spaceAfter=20)
    style_body = ParagraphStyle('Body', fontSize=10, leading=14)

    content = []
    content.append(Paragraph("Resumen Ejecutivo: Riesgo Reputacional Support", style_title))
    content.append(Paragraph("Reporte Automatizado - Cabify Chile", style_sub))
    content.append(Spacer(1, 10))

    if not df_risk.empty and 'Date' in df_risk.columns:
        df_risk['Date'] = pd.to_datetime(df_risk['Date']).dt.date
        evol = df_risk.groupby('Date').size().reset_index(name='Menciones')
        
        img_buffer = io.BytesIO()
        plt.figure(figsize=(8, 3.5), facecolor='#FDFDFF')
        plt.bar(evol['Date'].astype(str), evol['Menciones'], color='#7350FF', alpha=0.85, width=0.5)
        plt.title('Evolución de Quejas Críticas', fontsize=14, color='#1F1F1F', fontweight='bold')
        plt.gca().spines['top'].set_visible(False)
        plt.gca().spines['right'].set_visible(False)
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(img_buffer, format='png', dpi=150)
        plt.close()
        img_buffer.seek(0)
        
        content.append(Image(img_buffer, width=6*inch, height=2.6*inch))
        content.append(Spacer(1, 20))

    conteo = df_risk['Categoría'].value_counts().reset_index()
    conteo.columns = ['Categoría', 'Volumen']
    
    table_data = [[Paragraph("<b>Categoría</b>", style_body), Paragraph("<b>Casos para Análisis</b>", style_body)]]
    for _, row in conteo.iterrows():
        table_data.append([row['Categoría'], str(row['Volumen'])])

    t = Table(table_data, colWidths=[3*inch, 2*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#7350FF")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
    ]))
    content.append(t)
    doc.build(content)
    return pdf_buffer.getvalue()

# 5. INTERFAZ DE USUARIO
st.title("🚗 Risk Intelligence Support")
uploaded_file = st.file_uploader("Sube el archivo de Brandwatch", type=["csv", "xlsx", "xls"])

if uploaded_file:
    df = load_data(uploaded_file)
    if df is not None:
        df.columns = [str(c).replace('"', '').strip() for c in df.columns]
        txt_col = next((c for c in df.columns if c.lower() in ['snippet', 'full text', 'text']), None)
        
        if txt_col:
            df['Categoría'] = df[txt_col].apply(clasificar_mencion)
            df_risk = df[~df['Categoría'].isin(['Ruido Mediático', 'Otros / Consulta', 'Desconocido'])].copy()
            
            st.divider()
            # Botones de exportación
            st.markdown("### 📥 Descargar Entregables")
            c1, c2 = st.columns(2)
            with c1:
                pdf_data = generar_pdf(df_risk)
                st.download_button("📄 PDF Resumen Ejecutivo", data=pdf_data, file_name="Resumen_Riesgo_Cabify.pdf")
            with c2:
                # AQUÍ ESTÁ EL CAMBIO: El Excel ahora solo lleva los negativos
                excel_data = generar_excel_negativos(df)
                st.download_button("📊 Excel Casos Críticos (Solo Negativos)", data=excel_data, file_name="Tickets_Riesgo_Support.xlsx")
            
            st.divider()
            st.markdown("### 📝 Vista Previa de Menciones Negativas")
            st.dataframe(df_risk[[txt_col, 'Categoría']], use_container_width=True)
