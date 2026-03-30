import pandas as pd
import matplotlib.pyplot as plt
import io
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

# --- 1. PREPARACIÓN DE DATOS PARA LOS GRÁFICOS ---
# Datos basados en el volumen real detectado anteriormente
datos_volumen = {
    'Fecha': ['Lun 23', 'Mar 24', 'Mie 25', 'Jue 26', 'Vie 27', 'Sab 28', 'Dom 29'],
    'Menciones': [263, 169, 12, 104, 10, 2, 5]
}
df_vol = pd.DataFrame(datos_volumen)

# Crear gráfico elegante y minimalista
plt.figure(figsize=(10, 4), facecolor='#FDFDFF')
plt.bar(df_vol['Fecha'], df_vol['Menciones'], color='#7350FF', alpha=0.85, width=0.6)
plt.title('Evolución Semanal de Fricciones', fontsize=16, color='#1F1F1F', fontweight='bold', pad=20)
plt.gca().spines['top'].set_visible(False)
plt.gca().spines['right'].set_visible(False)
plt.gca().set_facecolor('#FDFDFF')
plt.grid(axis='y', linestyle='--', alpha=0.3)
plt.tight_layout()
plt.savefig('grafico_ejecutivo.png', dpi=200)
plt.close()

# --- 2. GENERACIÓN DEL PDF (RESUMEN EJECUTIVO HORIZONTAL) ---
pdf_file = "Resumen_Ejecutivo_Risk_Support_Cabify.pdf"
doc = SimpleDocTemplate(pdf_file, pagesize=landscape(A4), topMargin=30, bottomMargin=30)
styles = getSampleStyleSheet()

# Estilos Personalizados
style_title = ParagraphStyle('Title', fontSize=26, textColor=colors.HexColor("#7350FF"), leading=30, alignment=0, fontWeight='Bold')
style_subtitle = ParagraphStyle('Sub', fontSize=12, textColor=colors.grey, leading=14, spaceAfter=20)
style_heading = ParagraphStyle('Heading', fontSize=18, textColor=colors.HexColor("#1F1F1F"), spaceBefore=20, spaceAfter=10)
style_body = ParagraphStyle('Body', fontSize=11, leading=14, textColor=colors.black)

content = []

# Encabezado
content.append(Paragraph("Resumen Ejecutivo Riesgo Reputacional Support", style_title))
content.append(Paragraph("Período de Análisis: 23 al 29 de Marzo, 2026 | Chile", style_subtitle))
content.append(Spacer(1, 12))

# Agregar Gráfico
content.append(Image('grafico_ejecutivo.png', width=7.5*inch, height=3*inch))
content.append(Spacer(1, 20))

# Tabla de Hallazgos Clave
table_data = [
    [Paragraph("<b>Categoría de Riesgo</b>", style_body), Paragraph("<b>Impacto</b>", style_body), Paragraph("<b>Insight Operativo</b>", style_body)],
    ["Cobros y Tarifas", "ALTO", "Pico detectado el Lunes 23. Posible falla en cupones de descuento."],
    ["Calidad de Servicio", "MEDIO", "Reclamos recurrentes por falta de Aire Acondicionado en flota."],
    ["Disponibilidad", "MEDIO", "Baja tasa de aceptación en zonas periféricas (ej. Ñuñoa/Maipú)."],
]

t = Table(table_data, colWidths=[2*inch, 1.5*inch, 5*inch])
t.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#7350FF")),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
    ('TOPPADDING', (0, 0), (-1, 0), 12),
    ('FONTSIZE', (0, 0), (-1, -1), 10),
]))
content.append(t)

# Recomendación Final
content.append(Spacer(1, 25))
content.append(Paragraph("<b>Acción Recomendada:</b> Priorizar la revisión de transacciones del 23 de marzo y reforzar protocolo de confort a conductores.", style_body))

doc.build(content)

# --- 3. GENERACIÓN DEL EXCEL DE DATOS CRUDOS ---
excel_file = "Data_Cruda_Menciones_Support.xlsx"
# Usamos la data del último archivo cargado por el usuario
df_raw = pd.read_csv('mentions.csv', skiprows=10)
# Agregar clasificación simulada para el reporte
df_raw['Categoria_IA'] = df_raw['Snippet'].apply(lambda x: "Cobros" if "pago" in str(x).lower() else "General")
df_raw.to_excel(excel_file, index=False)
