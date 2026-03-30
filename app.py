import streamlit as st
import pandas as pd

# 1. Configuración de la página (Estilo Cabify)
st.set_page_config(page_title="Cabify - Radar de Riesgo", page_icon="🚗", layout="wide")

st.markdown("""
    <style>
    .main {background-color: #f8f9fa;}
    h1, h2, h3 {color: #7350FF;} /* Morado Cabify */
    </style>
""", unsafe_allow_html=True)

st.title("🚗 Radar de Riesgo Reputacional y Soporte")
st.markdown("**Sube tu exportación de Brandwatch (Excel o CSV) para analizar fricciones, categorizar quejas y generar alertas operativas.**")

# 2. Motor de Clasificación (Simulación de IA)
def clasificar_mencion(texto):
    if not isinstance(texto, str):
        return "Desconocido"
    
    texto = texto.lower()
    
    if any(palabra in texto for palabra in ["ley uber", "bencina", "combustible", "gobierno", "ministro", "noticia"]):
        return "Ruido Mediático (Descartado)"
    
    if any(palabra in texto for palabra in ["cobro", "tarifa", "cobraron", "estafa", "robo", "promoción", "condiciones"]):
        return "Cobros y Tarifas"
    
    if any(palabra in texto for palabra in ["aire", "calor", "conductor", "auto", "rasca", "pésimo", "grosero", "maneja"]):
        return "Actitud del Conductor / Calidad"
    
    if any(palabra in texto for palabra in ["espera", "toman", "cancel", "demora", "no llega", "app", "falla"]):
        return "Disponibilidad y Tiempos"
    
    if any(palabra in texto for palabra in ["penca", "callampa", "ctm", "hoyo", "weas"]):
        return "Queja Genérica / Frustración"
    
    return "Neutral / Positivo"

# 3. Carga del archivo (AHORA ACEPTA EXCEL Y CSV)
archivo_subido = st.file_uploader("Sube el archivo de Brandwatch (Excel o CSV)", type=["xlsx", "csv"])

if archivo_subido is not None:
    try:
        # Detectar el tipo de archivo y leerlo
        if archivo_subido.name.endswith('.csv'):
            df = pd.read_csv(archivo_subido)
        else:
            df = pd.read_excel(archivo_subido)
    except Exception as e:
        st.error(f"Error al leer el archivo. Asegúrate de que no esté dañado. Detalle: {e}")
        st.stop()
    
    # 4. Buscar la columna de texto dinámicamente
    columna_texto = None
    for col in df.columns:
        if col.lower() in ['snippet', 'full text', 'text', 'texto', 'mention']:
            columna_texto = col
            break
            
    if not columna_texto:
        st.error("No se encontró la columna de texto. El archivo debe tener una columna llamada 'Snippet', 'Full Text', 'Mention' o 'Text'.")
        st.stop()

    # 5. Procesamiento de los datos
    df['Categoría de Riesgo'] = df[columna_texto].apply(clasificar_mencion)
    df_quejas = df[~df['Categoría de Riesgo'].isin(["Ruido Mediático (Descartado)", "Neutral / Positivo", "Desconocido"])]
    
    # 6. Dashboard / Interfaz Visual
    st.divider()
    st.header("📊 Resumen Ejecutivo Semanal")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Menciones Analizadas", len(df))
    col2.metric("Quejas Reales (Riesgo)", len(df_quejas))
    
    tasa_riesgo = (len(df_quejas) / len(df)) * 100 if len(df) > 0 else 0
    col3.metric("Tasa de Riesgo Reputacional", f"{tasa_riesgo:.1f}%")
    
    if not df_quejas.empty:
        st.subheader("Distribución de Dolores (Pain Points)")
        conteo_categorias = df_quejas['Categoría de Riesgo'].value_counts()
        st.bar_chart(conteo_categorias)
        
        st.subheader("💡 Alertas para Support y Operaciones")
        categoria_top = conteo_categorias.idxmax()
        
        if categoria_top == "Cobros y Tarifas":
            st.warning("**ALERTA ROJA - COBROS:** El volumen principal apunta a problemas de facturación o promociones.")
        elif categoria_top == "Actitud del Conductor / Calidad":
            st.warning("**ALERTA AMARILLA - CALIDAD:** Los usuarios reportan fricciones a bordo (ej. aire acondicionado, trato).")
        elif categoria_top == "Disponibilidad y Tiempos":
            st.warning("**ALERTA AMARILLA - DISPONIBILIDAD:** Dificultad para encontrar autos o cancelaciones frecuentes.")
        else:
            st.info("Revisar el listado de quejas genéricas para identificar nuevos focos de fricción.")

        st.subheader("📝 Detalle de Menciones Críticas")
        columnas_mostrar = [col for col in ['Date', 'Author', columna_texto, 'Categoría de Riesgo'] if col in df.columns]
        st.dataframe(df_quejas[columnas_mostrar], use_container_width=True)
        
    else:
        st.success("No se detectaron quejas significativas de riesgo en este archivo.")
