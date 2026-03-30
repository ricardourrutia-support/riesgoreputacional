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

# 4. FUNCIONES DE EXPORTACIÓN (PDF Y EXCEL)
def generar_excel(df_export):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_export.to_excel(writer, index=False, sheet_name='Data_Cruda_Riesgo')
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

    # Generar gráfico estático para el PDF
    if not df_risk.empty and 'Date' in df_risk.columns:
        df_risk['Date'] = pd.to_datetime(df_risk['Date']).dt.date
        evol = df_risk.groupby('Date').size().reset_index(name='Menciones')
        
        img_buffer = io.BytesIO()
        plt.figure(figsize=(8, 3.5), facecolor='#FDFDFF')
        plt.bar(evol['Date'].astype(str), evol['Menciones'], color='#7350FF', alpha=0.85, width=0.5)
        plt.title('Evolución de Quejas', fontsize=14, color='#1F1F1F', fontweight='bold')
        plt.gca().spines['top'].set_visible(False)
        plt.gca().spines['right'].set_visible(False)
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(img_buffer, format='png', dpi=150)
        plt.close()
        img_buffer.seek(0)
        
        content.append(Image(img_buffer, width=6*inch, height=2.6*inch))
        content.append(Spacer(1, 20))

    # Tabla de Hallazgos
    conteo = df_risk['Categoría'].value_counts().reset_index()
    conteo.columns = ['Categoría', 'Volumen']
    
    table_data = [[Paragraph("<b>Categoría</b>", style_body), Paragraph("<b>Volumen de Quejas</b>", style_body)]]
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

# 5. INTERFAZ DE USUARIO PRINCIPAL
st.title("🚗 Risk Intelligence Support")
st.subheader("Análisis Reputacional de Menciones Semanales")

uploaded_file = st.file_uploader("Arrastra aquí el CSV o Excel de Brandwatch", type=["csv", "xlsx", "xls"])

if uploaded_file:
    df = load_data(uploaded_file)
    
    if df is not None:
        df.columns = [str(c).replace('"', '').strip() for c in df.columns]
        txt_col = next((c for c in df.columns if c.lower() in ['snippet', 'full text', 'text']), None)
        
        if txt_col:
            # Procesamiento principal
            df['Categoría'] = df[txt_col].apply(clasificar_mencion)
            df_risk = df[~df['Categoría'].isin(['Ruido Mediático', 'Otros / Consulta'])].copy()
            
            # --- KPIs SUPERIORES ---
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Analizados", len(df))
            m2.metric("Menciones Riesgo", len(df_risk))
            risk_pct = (len(df_risk)/len(df)*100) if len(df)>0 else 0
            m3.metric("% Impacto Negativo", f"{risk_pct:.1f}%")
            m4.metric("Sentimiento Prom.", "Negativo" if risk_pct > 20 else "Neutral")
            st.divider()

            # --- GRÁFICOS WEB ---
            col_left, col_right = st.columns([1, 1])
            with col_left:
                st.markdown("### 📊 Fricciones")
                if not df_risk.empty:
                    conteo = df_risk['Categoría'].value_counts().reset_index()
                    conteo.columns = ['Categoría', 'Casos']
                    fig_donut = px.pie(conteo, values='Casos', names='Categoría', hole=0.6, color_discrete_sequence=['#7350FF', '#9E85FF', '#C8BAFF', '#E4DFFF', '#2E1A73'])
                    fig_donut.update_layout(showlegend=False, margin=dict(t=0, b=0, l=0, r=0), height=300)
                    fig_donut.update_traces(textposition='inside', textinfo='percent+label')
                    st.plotly_chart(fig_donut, use_container_width=True)
            
            with col_right:
                st.markdown("### 📅 Evolución")
                if not df_risk.empty and 'Date' in df_risk.columns:
                    df_risk['Date'] = pd.to_datetime(df_risk['Date']).dt.date
                    evol = df_risk.groupby('Date').size().reset_index(name='Quejas')
                    fig_line = px.line(evol, x='Date', y='Quejas', markers=True)
                    fig_line.update_traces(line_color='#7350FF', line_width=4, marker=dict(size=10))
                    fig_line.update_layout(height=300, margin=dict(t=20, b=0, l=0, r=0))
                    st.plotly_chart(fig_line, use_container_width=True)

            # --- BOTONES DE EXPORTACIÓN ---
            st.divider()
            st.markdown("### 📥 Exportar Reportes (Formatos Ejecutivos)")
            col_btn1, col_btn2 = st.columns(2)
            
            with col_btn1:
                if not df_risk.empty:
                    pdf_data = generar_pdf(df_risk)
                    st.download_button(
                        label="📄 Descargar Resumen en PDF",
                        data=pdf_data,
                        file_name="Resumen_Riesgo_Cabify.pdf",
                        mime="application/pdf"
                    )
            
            with col_btn2:
                excel_data = generar_excel(df)
                st.download_button(
                    label="📊 Descargar Datos Crudos (Excel)",
                    data=excel_data,
                    file_name="Data_Cruda_Cabify.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
        else:
            st.error("No se encontró la columna de mensajes (Snippet o Full Text).")
