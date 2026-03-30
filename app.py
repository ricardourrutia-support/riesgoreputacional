import pandas as pd
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

# 1. Preparar datos del gráfico (basado en el volumen compartido anteriormente)
# Cabify - [CL] Riesgo Reputacional Soporte: 9, 263, 169, 12, 104, 10, 2
dias = ['Dom 22', 'Lun 23', 'Mar 24', 'Mie 25', 'Jue 26', 'Vie 27', 'Sab 28']
volumen = [9, 263, 169, 12, 104, 10, 2]

plt.figure(figsize=(10, 4))
plt.bar(dias, volumen, color='#7350FF')
plt.title('Volumen Diario de Menciones de Riesgo', color='#7350FF', fontsize=14, fontweight='bold')
plt.xlabel('Día')
plt.ylabel('Cantidad de Menciones')
plt.grid(axis='y', linestyle='--', alpha=0.7)
plt.savefig('grafico_volumen.png', bbox_inches='tight', dpi=150)
plt.close()

# 2. Generar PDF Horizontal
pdf_name = "Resumen_Ejecutivo_Riesgo_Support.pdf"
doc = SimpleDocTemplate(pdf_name, pagesize=landscape(A4))
styles = getSampleStyleSheet()
story = []

# Estilos personalizados
title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], color=colors.HexColor("#7350FF"), alignment=1, fontSize=24, spaceAfter=20)
sub_style = ParagraphStyle('SubStyle', parent=styles['Normal'], alignment=1, fontSize=12, textColor=colors.grey, spaceAfter=20)
heading_style = ParagraphStyle('HeadingStyle', parent=styles['Heading2'], color=colors.HexColor("#7350FF"), fontSize=16, spaceBefore=15, spaceAfter=10)
body_style = ParagraphStyle('BodyStyle', parent=styles['Normal'], fontSize=10, leading=14)

# Contenido
story.append(Paragraph("Resumen Ejecutivo Riesgo Reputacional Support", title_style))
story.append(Paragraph("Análisis Semanal: 23 al 29 de Marzo de 2026 - Cabify Chile", sub_style))

# Agregar Imagen del Gráfico
story.append(Image('grafico_volumen.png', width=7*inch, height=2.8*inch))
story.append(Spacer(1, 12))

# Tabla de Resumen
data = [
    ['Categoría', 'Volumen Estimado', 'Severidad', 'Acción Recomendada'],
    ['Cobros y Tarifas', '35%', 'Alta', 'Revisar motor de promociones'],
    ['Actitud Conductor', '30%', 'Media-Alta', 'Reforzar protocolos de confort (Aire)'],
    ['Disponibilidad', '25%', 'Media', 'Ajustar incentivos en zonas críticas'],
    ['Otros / Genérico', '10%', 'Baja', 'Monitoreo preventivo']
]

table = Table(data, colWidths=[2*inch, 2*inch, 1.5*inch, 3*inch])
table.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#7350FF")),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('FONTSIZE', (0, 0), (-1, 0), 12),
    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
]))
story.append(table)

doc.build(story)

# 3. Generar Excel de Datos Crudos (con los datos que tenemos disponibles)
# Nota: Usamos los datos crudos del último CSV procesado
excel_name = "Datos_Crudos_Menciones_Riesgo.xlsx"
raw_data = {
    'Fecha': ['2026-03-29', '2026-03-29'],
    'Autor': ['SantibanezBaez', 'Cafe_a_la_Vena'],
    'Snippet': [
        "RT @SantibanezBaez @PilarOpazoL @freddyaraneda No sólo las canillas..! Y sin ninguna vergüenza...! O a lo mejor hacen Uber/Cabify para complementar renta..! @Camara_cl @Senado_Chile",
        "RT @Cafe_a_la_Vena @danakotyta @Oh_Viajero Tienes que pagar $5.000 mensuales, para tener la membres prime, por compras mínimo de 22 mil despacho gratis, descuentos prime en estacionamiento, bencina, cabify, excelente servicio!!!"
    ],
    'Sentimiento': ['Neutral/Sarcasmo', 'Positivo/Beneficios'],
    'Categorización': ['Ruido Político', 'Beneficios Alianzas']
}
df_excel = pd.DataFrame(raw_data)
df_excel.to_excel(excel_name, index=False)
