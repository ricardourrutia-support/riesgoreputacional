import streamlit as st
import pandas as pd

# 1. Configuración de la página (Estilo Cabify)
st.set_page_config(page_title="Cabify - Radar de Riesgo", page_icon="🚗", layout="wide")

# Colores y estilos
st.markdown("""
    <style>
    .main {background-color: #f8f9fa;}
    h1, h2, h3 {color: #7350FF;} /* Morado Cabify */
    </style>
""", unsafe_allow_html=True)

st.title("🚗 Radar de Riesgo Reputacional y Soporte")
st.markdown("**Sube tu exportación de Brandwatch (CSV) para analizar fricciones, categorizar quejas y generar alertas operativas.**")

# 2. Motor de Clasificación (Simulación de IA basada en reglas)
def clasificar_mencion(texto):
    if not isinstance(texto, str):
        return "Desconocido"
    
    texto = texto.lower()
    
    # Excluir ruido mediático (Noticias, política)
    if any(palabra in texto for palabra in ["ley uber", "bencina", "combustible", "gobierno", "ministro", "noticia"]):
        return "Ruido Mediático (Descartado)"
    
    # Categoría 1: Cobros y Tarifas
    if any(palabra in texto for palabra in ["cobro", "tarifa", "cobraron", "estafa", "robo", "promoción", "condiciones"]):
        return "Cobros y Tarifas"
    
    # Categoría 2: Calidad y Conductor
    if any(palabra in texto for palabra in ["aire", "calor", "conductor", "auto", "rasca", "pésimo", "grosero", "maneja"]):
        return "Actitud del Conductor / Calidad"
    
    # Categoría 3: Disponibilidad y App
    if any(palabra in texto for palabra in ["espera", "toman", "cancel", "demora", "no llega", "app", "falla"]):
        return "Disponibilidad y Tiempos"
    
    # Detectar insultos genéricos sin categoría clara
    if any(palabra in texto for palabra in ["penca", "callampa", "ctm", "hoyo", "weas"]):
        return "Queja Genérica / Frustración"
    
    return "Neutral / Positivo"

# 3. Carga del archivo
archivo_subido = st.file_uploader("Sube el archivo CSV de Brandwatch", type=["csv"])

if archivo_subido is not None:
    # Leer datos
    try:
        df = pd.read_csv(archivo_subido)
    except Exception as e:
        st.error(f"Error al leer el archivo. Asegúrate de que sea un CSV válido. Detalle: {e}")
        st.stop()
    
    # Buscar la columna que contiene el texto (Brandwatch suele usar 'Snippet' o 'Full Text')
    columna_texto = None
    for col in df.columns:
        if col.lower() in ['snippet', 'full text', 'text', 'texto']:
            columna_texto = col
            break
            
    if not columna_texto:
        st.error("No se encontró la columna de texto. El archivo debe tener una columna llamada 'Snippet', 'Full Text' o 'Text'.")
        st.stop()

    # 4. Procesamiento de los datos
    df['Categoría de Riesgo'] = df[columna_texto].apply(clasificar_mencion)
    
    # Filtrar solo las quejas reales (excluir ruido y neutrales)
    df_quejas = df[~df['Categoría de Riesgo'].isin(["Ruido Mediático (Descartado)", "Neutral / Positivo"])]
    
    # 5. Dashboard / Interfaz Visual
    st.divider()
    st.header("📊 Resumen Ejecutivo Semanal")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Menciones Analizadas", len(df))
    col2.metric("Quejas Reales (Riesgo)", len(df_quejas))
    
    tasa_riesgo = (len(df_quejas) / len(df)) * 100 if len(df) > 0 else 0
    col3.metric("Tasa de Riesgo Reputacional", f"{tasa_riesgo:.1f}%")
    
    # Gráfico de Categorías
    if not df_quejas.empty:
        st.subheader("Distribución de Dolores (Pain Points)")
        conteo_categorias = df_quejas['Categoría de Riesgo'].value_counts()
        st.bar_chart(conteo_categorias)
        
        # 6. Alertas y Recomendaciones Dinámicas
        st.subheader("💡 Alertas para Support y Operaciones")
        categoria_top = conteo_categorias.idxmax()
        
        if categoria_top == "Cobros y Tarifas":
            st.warning("**ALERTA ROJA - COBROS:** El volumen principal de quejas apunta a problemas de facturación. **Acción:** Revisar SLAs de tickets financieros y verificar si hubo un bug reciente en el motor de promociones.")
        elif categoria_top == "Actitud del Conductor / Calidad":
            st.warning("**ALERTA AMARILLA - CALIDAD:** Los usuarios reportan fricciones a bordo (ej. aire acondicionado, trato). **Acción:** Enviar comunicación de refuerzo a la base de socios conductores sobre estándares de calidad Cabify.")
        elif categoria_top == "Disponibilidad y Tiempos":
            st.warning("**ALERTA AMARILLA - DISPONIBILIDAD:** Dificultad para encontrar autos o cancelaciones frecuentes. **Acción:** Alertar al equipo de Pricing/Marketplace para revisar multiplicadores en zonas de alta demanda no cubierta.")
        else:
            st.info("Revisar el listado de quejas genéricas para identificar nuevos focos de fricción.")

        # 7. Tabla de Datos Crudos para el Equipo
        st.subheader("📝 Detalle de Menciones Críticas (Verbatims)")
        columnas_mostrar = [col for col in ['Date', 'Author', columna_texto, 'Categoría de Riesgo'] if col in df.columns]
        st.dataframe(df_quejas[columnas_mostrar], use_container_width=True)
        
    else:
        st.success("No se detectaron quejas significativas de riesgo en este archivo. ¡Excelente semana!")
