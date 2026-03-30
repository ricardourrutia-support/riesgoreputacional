import streamlit as st
import pandas as pd
import io

# 1. Configuración de la página
st.set_page_config(page_title="Cabify - Radar de Riesgo", page_icon="🚗", layout="wide")

st.markdown("""
    <style>
    .main {background-color: #f8f9fa;}
    h1, h2, h3 {color: #7350FF;} /* Morado Cabify */
    </style>
""", unsafe_allow_html=True)

st.title("🚗 Radar de Riesgo Reputacional y Soporte")
st.markdown("**Sube tu exportación de Brandwatch para analizar fricciones y generar alertas operativas.**")

# 2. Motor de Clasificación
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

# 3. Función detectora de memoria RAM (Especial para la nube)
def cargar_datos_robustos(archivo):
    # Leer el archivo completo en la memoria de la nube para evitar problemas de lectura
    file_bytes = archivo.read()
    
    # Si los primeros bytes son PK, es 100% un archivo de Excel
    if file_bytes.startswith(b'PK\x03\x04'):
        try:
            buffer = io.BytesIO(file_bytes)
            df = pd.read_excel(buffer, engine='openpyxl')
            
            # Buscar dónde empiezan los datos reales si hay metadatos
            columnas_minusculas = [str(c).lower() for c in df.columns]
            if not any(col in columnas_minusculas for col in ['snippet', 'full text', 'text', 'texto', 'mention']):
                for i in range(1, 25):
                    buffer.seek(0)
                    temp_df = pd.read_excel(buffer, skiprows=i, engine='openpyxl')
                    temp_cols = [str(c).lower() for c in temp_df.columns]
                    if any(col in temp_cols for col in ['snippet', 'full text', 'texto', 'mention', 'text']):
                        return temp_df
            return df
        except ImportError:
            st.error("❌ ERROR CRÍTICO EN LA NUBE: Streamlit Cloud no tiene instalado 'openpyxl'. Por favor, revisa tu archivo requirements.txt en GitHub.")
            st.stop()
        except Exception as e:
            st.error(f"❌ ERROR AL LEER EL EXCEL: {e}. Te recomendamos exportar el archivo desde Brandwatch en formato CSV.")
            st.stop()
            
    else:
        # Si NO es Excel, intentar como texto plano / CSV
        codificaciones = ['utf-8', 'utf-8-sig', 'latin1', 'cp1252', 'iso-8859-1']
        for cod in codificaciones:
            try:
                contenido = file_bytes.decode(cod)
                lineas = contenido.split('\n')
                skip_idx = 0
                for i, linea in enumerate(lineas[:20]):
                    if any(k in linea for k in ['Snippet', 'Full Text', 'Date', 'Mention', 'Text']):
                        skip_idx = i
                        break
                buffer = io.StringIO(contenido)
                df = pd.read_csv(buffer, skiprows=skip_idx, on_bad_lines='skip', sep=None, engine='python')
                if not df.empty:
                    return df
            except Exception:
                continue
    return None

# 4. Carga del archivo 
archivo_subido = st.file_uploader("Sube el archivo de Brandwatch (Excel o CSV)", type=["xlsx", "xls", "csv"])

if archivo_subido is not None:
    df = cargar_datos_robustos(archivo_subido)
    
    if df is None or df.empty:
        st.error("❌ No se pudo extraer información válida del archivo.")
        st.stop()
    
    columna_texto = None
    for col in df.columns:
        if str(col).lower() in ['snippet', 'full text', 'text', 'texto', 'mention']:
            columna_texto = col
            break
            
    if not columna_texto:
        st.error(f"❌ Archivo leído, pero no encontré la columna de mensajes. Columnas: {list(df.columns)}")
        st.stop()

    # 5. Procesamiento
    df['Categoría de Riesgo'] = df[columna_texto].astype(str).apply(clasificar_mencion)
    df_quejas = df[~df['Categoría de Riesgo'].isin(["Ruido Mediático (Descartado)", "Neutral / Positivo", "Desconocido"])]
    
    # 6. Dashboard
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
            st.warning("**ALERTA ROJA - COBROS:** Revisar SLAs de facturación o fallos en promociones.")
        elif categoria_top == "Actitud del Conductor / Calidad":
            st.warning("**ALERTA AMARILLA - CALIDAD:** Fricciones a bordo (ej. aire acondicionado, trato).")
        elif categoria_top == "Disponibilidad y Tiempos":
            st.warning("**ALERTA AMARILLA - DISPONIBILIDAD:** Cancelaciones o demoras excesivas.")
            
        st.subheader("📝 Detalle de Menciones Críticas")
        columnas_mostrar = [col for col in ['Date', 'Author', columna_texto, 'Categoría de Riesgo'] if col in df.columns]
        st.dataframe(df_quejas[columnas_mostrar], use_container_width=True)
    else:
        st.success("✅ No se detectaron quejas de riesgo en este archivo.")
