import streamlit as st
import pandas as pd
import io

# 1. Configuración de la página (Estilo Cabify)
st.set_page_config(page_title="Cabify - Radar de Riesgo", page_icon="🚗", layout="wide")

st.markdown("""
    <style>
    .main {background-color: #f8f9fa;}
    h1, h2, h3 {color: #7350FF;} /* Morado Cabify */
    </style>
""", unsafe_allow_html=True)

st.title("🚗 Radar de Riesgo Reputacional y Soporte")
st.markdown("**Sube tu exportación de Brandwatch para analizar fricciones, categorizar quejas y generar alertas operativas.**")

# 2. Motor de Clasificación (Simulación de IA)
def clasificar_mencion(texto):
    if not isinstance(texto, str):
        return "Desconocido"
    
    texto = texto.lower()
    
    if any(palabra in texto for palabra in ["ley uber", "bencina", "combustible", "gobierno", "ministro", "noticia"]):
        return "Ruido Mediático (Descartado)"
    
    if any(palabra in texto for palabra in ["cobro", "tarifa", "cobraron", "estafa", "robo", "promoción", "condiciones", "plata"]):
        return "Cobros y Tarifas"
    
    if any(palabra in texto for palabra in ["aire", "calor", "conductor", "auto", "rasca", "pésimo", "grosero", "maneja"]):
        return "Actitud del Conductor / Calidad"
    
    if any(palabra in texto for palabra in ["espera", "toman", "cancel", "demora", "no llega", "app", "falla"]):
        return "Disponibilidad y Tiempos"
    
    if any(palabra in texto for palabra in ["penca", "callampa", "ctm", "hoyo", "weas", "qlo"]):
        return "Queja Genérica / Frustración"
    
    return "Neutral / Positivo"

# 3. Función blindada para leer el archivo sin errores de formato
def cargar_datos_robustos(archivo):
    # Intentar como Excel nativo primero
    if archivo.name.endswith(('.xls', '.xlsx')):
        try:
            df = pd.read_excel(archivo)
            # Buscar dónde empiezan los datos reales si hay metadatos de Brandwatch
            if not any(col.lower() in ['snippet', 'full text', 'text', 'texto', 'mention'] for col in df.columns):
                for i in range(1, 15):
                    archivo.seek(0)
                    temp_df = pd.read_excel(archivo, skiprows=i)
                    if any(col.lower() in ['snippet', 'full text', 'texto', 'mention', 'text'] for col in temp_df.columns):
                        return temp_df
            return df
        except Exception:
            pass # Si falla, es un CSV disfrazado de Excel, pasamos a la siguiente prueba

    # Intentar como CSV con distintas codificaciones (UTF-8, Latin-1, etc.)
    codificaciones = ['utf-8', 'utf-8-sig', 'latin1', 'cp1252', 'iso-8859-1']
    
    for cod en codificaciones:
        try:
            archivo.seek(0)
            contenido = archivo.read().decode(cod)
            lineas = contenido.split('\n')
            
            # Buscar en qué línea están los encabezados típicos de Brandwatch
            skip_idx = 0
            for i, linea in enumerate(lineas[:20]):
                if any(k in linea for k in ['Snippet', 'Full Text', 'Date', 'Mention', 'Text']):
                    skip_idx = i
                    break
            
            archivo.seek(0)
            df = pd.read_csv(archivo, encoding=cod, skiprows=skip_idx, on_bad_lines='skip', sep=None, engine='python')
            
            if not df.empty:
                return df
                
        except Exception:
            continue # Si esta codificación falla, intenta con la siguiente
            
    return None

# 4. Carga del archivo 
archivo_subido = st.file_uploader("Sube el archivo de Brandwatch (Excel o CSV)", type=["xlsx", "xls", "csv"])

if archivo_subido is not None:
    df = cargar_datos_robustos(archivo_subido)
    
    if df is None or df.empty:
        st.error("❌ No se pudo extraer información válida del archivo. Revisa que no esté en blanco.")
        st.stop()
    
    # Buscar la columna de texto dinámicamente
    columna_texto = None
    for col in df.columns:
        if str(col).lower() in ['snippet', 'full text', 'text', 'texto', 'mention']:
            columna_texto = col
            break
            
    if not columna_texto:
        st.error(f"❌ El archivo se leyó bien, pero no encontré la columna de los mensajes. Columnas detectadas: {list(df.columns)}")
        st.stop()

    # 5. Procesamiento de los datos
    df['Categoría de Riesgo'] = df[columna_texto].astype(str).apply(clasificar_mencion)
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
        # Mostrar solo las columnas relevantes
        columnas_mostrar = [col for col in ['Date', 'Author', columna_texto, 'Categoría de Riesgo'] if col in df.columns]
        st.dataframe(df_quejas[columnas_mostrar], use_container_width=True)
        
    else:
        st.success("✅ No se detectaron quejas significativas de riesgo en este archivo.")
