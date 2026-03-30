import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import io

# 1. CONFIGURACIÓN DE MARCA Y ESTILO (CABIFY)
st.set_page_config(page_title="Cabify Risk Intelligence", page_icon="🚗", layout="wide")

# CSS para un look limpio, tipografía sans-serif y colores corporativos
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .main { background-color: #FDFDFF; }
    .stMetric { background-color: #ffffff; border-radius: 10px; padding: 15px; border: 1px solid #E0E0E0; }
    div[data-testid="stMetricValue"] { color: #7350FF; font-weight: 700; }
    h1, h2, h3 { color: #1F1F1F; letter-spacing: -0.5px; }
    .cabify-purple { color: #7350FF; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# 2. LOGICA DE CLASIFICACIÓN
def clasificar_mencion(texto):
    if not isinstance(texto, str): return "Desconocido"
    t = texto.lower()
    if any(p in t for p in ["ley uber", "bencina", "gobierno", "ministro", "noticia", "ley"]): return "Ruido Mediático"
    if any(p in t for p in ["cobro", "tarifa", "cobraron", "estafa", "robo", "promoción", "plata"]): return "Cobros y Tarifas"
    if any(p in t for p in ["aire", "calor", "conductor", "rasca", "pésimo", "grosero", "maneja"]): return "Calidad de Servicio"
    if any(p in t for p in ["espera", "toman", "cancel", "demora", "no llega", "app"]): return "Disponibilidad / App"
    if any(p in t for p in ["penca", "callampa", "ctm", "hoyo", "weas", "qlo", "ladrón"]): return "Frustración Crítica"
    return "Otros / Consulta"

# 3. LECTURA BLINDADA DE ARCHIVOS
def load_data(file):
    try:
        content = file.read()
        # Caso Excel
        if file.name.endswith(('.xlsx', '.xls')) or content.startswith(b'PK\x03\x04'):
            df = pd.read_excel(io.BytesIO(content), engine='openpyxl')
            if 'Snippet' not in df.columns:
                for i in range(1, 20):
                    df = pd.read_excel(io.BytesIO(content), skiprows=i, engine='openpyxl')
                    if any(c in [str(x).lower() for x in df.columns] for c in ['snippet', 'full text']): break
            return df
        # Caso CSV
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

# 4. INTERFAZ DE USUARIO
st.title("🚗 Risk Intelligence Support")
st.subheader("Análisis Reputacional de Menciones Semanales")

uploaded_file = st.file_uploader("Arrastra aquí el CSV o Excel de Brandwatch", type=["csv", "xlsx", "xls"])

if uploaded_file:
    df = load_data(uploaded_file)
    
    if df is not None:
        # Limpieza de columnas
        df.columns = [str(c).replace('"', '').strip() for c in df.columns]
        txt_col = next((c for c in df.columns if c.lower() in ['snippet', 'full text', 'text']), None)
        
        if txt_col:
            # Procesamiento
            df['Categoría'] = df[txt_col].apply(clasificar_mencion)
            # Filtramos para el reporte de riesgo (quitando ruido mediático y otros)
            df_risk = df[~df['Categoría'].isin(['Ruido Mediático', 'Otros / Consulta'])].copy()
            
            # --- KPIs SUPERIORES ---
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Analizados", len(df))
            m2.metric("Menciones Riesgo", len(df_risk))
            risk_pct = (len(df_risk)/len(df)*100) if len(df)>0 else 0
            m3.metric("% Impacto Negativo", f"{risk_pct:.1f}%")
            m4.metric("Sentimiento Prom.", "Negativo" if risk_pct > 20 else "Neutral")

            st.divider()

            # --- GRÁFICOS ELEGANTES ---
            col_left, col_right = st.columns([1, 1])

            with col_left:
                st.markdown("### 📊 Distribución de Fricciones")
                conteo = df_risk['Categoría'].value_counts().reset_index()
                conteo.columns = ['Categoría', 'Casos']
                
                # Gráfico de Dona Minimalista
                fig_donut = px.pie(
                    conteo, values='Casos', names='Categoría',
                    hole=0.6,
                    color_discrete_sequence=['#7350FF', '#9E85FF', '#C8BAFF', '#E4DFFF', '#2E1A73']
                )
                fig_donut.update_traces(textposition='inside', textinfo='percent+label')
                fig_donut.update_layout(
                    showlegend=False, 
                    margin=dict(t=0, b=0, l=0, r=0),
                    height=350,
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig_donut, use_container_width=True)

            with col_right:
                st.markdown("### 📅 Evolución del Riesgo")
                if 'Date' in df.columns:
                    df['Date'] = pd.to_datetime(df['Date']).dt.date
                    evol = df_risk.groupby('Date').size().reset_index(name='Quejas')
                    
                    # Gráfico de Línea Suave
                    fig_line = px.line(evol, x='Date', y='Quejas', markers=True)
                    fig_line.update_traces(line_color='#7350FF', line_width=4, marker=dict(size=10, color='white', line=dict(width=2, color='#7350FF')))
                    fig_line.update_layout(
                        xaxis_title="", yaxis_title="",
                        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                        height=350, margin=dict(t=20, b=0, l=0, r=0)
                    )
                    fig_line.update_yaxes(showgrid=True, gridcolor='#F0F0F0')
                    st.plotly_chart(fig_line, use_container_width=True)
                else:
                    st.info("No hay datos de fecha disponibles para el gráfico de evolución.")

            # --- ALERTAS ESTRATÉGICAS ---
            st.markdown("### 💡 Alertas para el Equipo de Support")
            if not df_risk.empty:
                top_cat = df_risk['Categoría'].value_counts().idxmax()
                
                c1, c2 = st.columns(2)
                with c1:
                    st.error(f"**Foco Crítico:** {top_cat}")
                    st.write("Esta categoría representa el mayor dolor del usuario esta semana. Se recomienda priorizar estos tickets en Zendesk.")
                with c2:
                    st.info("**Recomendación Operativa**")
                    if top_cat == "Cobros y Tarifas":
                        st.write("Verificar errores en el motor de cupones. Posible falla masiva en promociones.")
                    elif top_cat == "Calidad de Servicio":
                        st.write("Reforzar campaña de aire acondicionado a la base de conductores.")
                    else:
                        st.write("Ajustar tiempos de respuesta en redes sociales para contener el escalamiento.")

            # --- TABLA DE VERBATIMS ---
            st.markdown("### 📝 Listado de Menciones Críticas (Auditoría)")
            st.dataframe(
                df_risk[[txt_col, 'Categoría']].sort_index(ascending=False),
                use_container_width=True,
                height=400
            )
        else:
            st.error("No se encontró la columna de mensajes (Snippet).")
    else:
        st.info("Sube el archivo de Brandwatch para generar el reporte.")
