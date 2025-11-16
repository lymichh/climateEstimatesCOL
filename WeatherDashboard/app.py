from flask import Flask, render_template, jsonify, request
import plotly
import pyodbc
from os import getenv
import pandas as pd
import plotly.express as px
import plotly.io as pio
import json
import urllib.request
import numpy as np
from plotly.subplots import make_subplots
import plotly.graph_objects as go

app = Flask(__name__)

# --- CONFIGURACIÓN DE LA CONEXIÓN ---

#server = getenv('DB_SERVER', 'localhost\\SQLEXPRESS')
server = 'localhost,1433'
database = 'WeatherCOL'
username = 'project'
password = 'project123'

connection_string = (
    f'DRIVER={{ODBC Driver 17 for SQL Server}};'
    f'SERVER={server};'
    f'DATABASE={database};'
    f'UID={username};'
    f'PWD={password}'
)

def lagrange(x_val, equis, ye, n=12):
    suma = 0
    for i in range(n):
        pro = 1
        for j in range(n):
            if i != j:
                pro = pro * (x_val - equis[j]) / (equis[i] - equis[j])
        suma = suma + ye[i] * pro
    return suma

# Función para ejecutar consultas SQL
def run_query(query, params=None):
    try:
        db = pyodbc.connect(connection_string)
        cursor = db.cursor()
        
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        rows = cursor.fetchall()
        columns = [col[0] for col in cursor.description]
        df = pd.DataFrame.from_records(rows, columns=columns)
        db.close()
        return df
    
    except Exception as e:
        print(f"Error al ejecutar consulta: {e}")
        return pd.DataFrame()

@app.route("/home")
def homePage():
    return render_template("home.html")

@app.route('/temperaturas')
def temperaturas():
    # Parámetros de la consulta
    municipio = request.args.get('municipio', 'Barranquilla')
    tipo_temp = request.args.get('tipo_temp', 'max')
    mes_interpolacion = request.args.get('mes', '6.5')
    
    db = pyodbc.connect(connection_string)
    cursor = db.cursor()
    
    cursor.execute("SELECT DISTINCT ciudad FROM Temperaturas_Ciudades ORDER BY ciudad")
    municipios = [row[0] for row in cursor.fetchall()]
    
    # Consulta de datos para el municipio y tipo seleccionado
    query = """
        SELECT tempEnero, tempFebrero, tempMarzo, tempAbril, tempMayo, tempJunio,
               tempJulio, tempAgosto, tempSept, tempOctubre, tempNov, tempDic
        FROM Temperaturas_Ciudades
        WHERE ciudad = ? AND max_min = ?
    """
    
    try:
        cursor.execute(query, (municipio, tipo_temp))
        row = cursor.fetchone()
        
        if not row:
            print(f"⚠️ No se encontraron registros para: {municipio} - {tipo_temp}")
            db.close()
            error_html = '<p class="text-center text-red-500 font-semibold">No hay datos para esta selección.</p>'
            return render_template('temperaturas.html',
                                 municipios=municipios,
                                 municipio_default=municipio,
                                 tipo_temp_default=tipo_temp,
                                 mes_default=mes_interpolacion,
                                 graph_html=error_html,
                                 temp_estimada=None)
        
        temperaturas = list(row) # Convertir las temperaturas a una lista
        meses = list(range(1, 13)) #(1 a 12)
        
        # Calcular interpolación
        try:
            mes_float = float(mes_interpolacion)
            if mes_float < 1 or mes_float > 12:
                mes_float = 6.5
        except:
            mes_float = 6.5
        
        temp_estimada = lagrange(mes_float, meses, temperaturas)
 
        fig = figure_temperaturas(meses, temperaturas, municipio, tipo_temp, mes_float, temp_estimada)
        
        # Si es una petición AJAX, devolver JSON (o sea, actualiza solo el gráfico, no toda la página)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            graph_json = pio.to_json(fig)
            return jsonify({
                'json': graph_json,
                'temp_estimada': round(temp_estimada, 2)
            })
        
        # Si es carga inicial, si se carga el HTML completo
        graph_html = pio.to_html(fig, full_html=False, div_id='temperaturas_graph')
        
        return render_template('temperaturas.html',
                             municipios=municipios,
                             municipio_default=municipio,
                             tipo_temp_default=tipo_temp,
                             mes_default=mes_interpolacion,
                             graph_html=graph_html,
                             temp_estimada=round(temp_estimada, 2))
    
    except Exception as e:
        print(f"❌ Error al consultar datos: {e}")
        error_html = f'<p class="text-center text-red-500 font-semibold">Error al cargar datos: {str(e)}</p>'
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'html': error_html, 'temp_estimada': None})
        
        return render_template('temperaturas.html',
                             municipios=municipios,
                             municipio_default=municipio,
                             tipo_temp_default=tipo_temp,
                             mes_default=mes_interpolacion,
                             graph_html=error_html,
                             temp_estimada=None)
    
    finally:
        db.close()


def figure_temperaturas(meses, temperaturas, municipio, tipo_temp, mes_estimado, temp_estimada):

    tipo_label = "máxima" if tipo_temp == "max" else "mínima"
    fig = go.Figure()
    
    # Línea de temperaturas reales
    fig.add_trace(go.Scatter(
        x=meses,
        y=temperaturas,
        mode='lines+markers',
        name=f'Temperatura {tipo_label}',
        line=dict(color='#25736a', width=3, shape='spline'),
        marker=dict(size=10, color='#25736a', symbol='circle')
    ))
    
    # Punto estimado por Lagrange
    fig.add_trace(go.Scatter(
        x=[mes_estimado],
        y=[temp_estimada],
        mode='markers',
        name=f'Estimado ({temp_estimada:.2f}°C)',
        marker=dict(size=15, color="#2E9FCC", symbol='diamond', line=dict(width=2, color='white'))
    ))
    
    fig.update_layout(
        title=f'Temperatura {tipo_label} en {municipio}',
        title_x=0.5,
        xaxis_title='Mes',
        yaxis_title='Temperatura (°C)',
        template='plotly_white',
        font=dict(family="Inter, sans-serif", size=14, color="#333"),
        height=550,
        margin=dict(l=40, r=40, t=90, b=40),
        hovermode='x unified',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1,
            xanchor="center",
            x=0.5
        ),
        xaxis=dict(
            tickmode='linear',
            tick0=1,
            dtick=1,
            range=[0.5, 12.5]
        )
    )
    return fig

# Ruta principal
@app.route('/')
def home():
    return render_template('home.html')

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    app.run(debug=True, port=5050)