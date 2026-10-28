from pathlib import Path
import json, os, sqlite3
from flask import Flask, render_template, request
from dotenv import load_dotenv
import pandas as pd
import plotly.express as px
import plotly.io as pio

ROOT=Path(__file__).resolve().parent
load_dotenv(ROOT/'.env')
app=Flask(__name__)
app.secret_key=os.getenv('FLASK_SECRET_KEY','dev-key-change-before-deploy')
DB_PATH=Path(os.getenv('DATABASE_PATH',str(ROOT/'data'/'ev_market.db')))
if not DB_PATH.is_absolute(): DB_PATH=ROOT/DB_PATH
OUT=ROOT/'outputs'
DASHBOARD_URL=os.getenv('TABLEAU_DASHBOARD_URL','').strip()
STORY_URL=os.getenv('TABLEAU_STORY_URL','').strip()

def get_kpis():
    p=OUT/'data_quality_report.json'
    if p.exists(): return json.loads(p.read_text())
    if DB_PATH.exists():
        with sqlite3.connect(DB_PATH) as con:
            row=con.execute('SELECT COUNT(*),COUNT(DISTINCT manufacturer),COUNT(DISTINCT category),AVG(customer_rating),AVG(range_km),AVG(battery_capacity_kwh),SUM(annual_sales_units) FROM ev_market').fetchone()
        return dict(cleaned_rows=row[0],unique_manufacturers=row[1],unique_categories=row[2],avg_customer_rating=row[3],avg_range_km=row[4],avg_battery_capacity_kwh=row[5],total_annual_sales_units=row[6])
    return {}

def read_agg(name):
    p=OUT/f'{name}.csv'
    return pd.read_csv(p) if p.exists() else pd.DataFrame()

def chart_html(name, df, kind, x, y, title, color=None):
    if df.empty: return '<div class="empty">Run <code>python src/build_data.py</code> to generate charts.</div>'
    if kind=='bar': fig=px.bar(df,x=x,y=y,color=color,title=title,template='plotly_white')
    elif kind=='line': fig=px.line(df,x=x,y=y,markers=True,title=title,template='plotly_white')
    elif kind=='pie': fig=px.pie(df,names=x,values=y,title=title,hole=.48,template='plotly_white')
    elif kind=='scatter': fig=px.scatter(df,x=x,y=y,color=color,title=title,template='plotly_white')
    else: return ''
    fig.update_layout(
        autosize=True,
        margin=dict(l=28,r=18,t=48,b=38),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#536779',family='DM Sans, sans-serif',size=11),
        legend_title_text='',
        title=dict(font=dict(size=13,color='#18384c')),
    )
    fig.update_xaxes(gridcolor='#e7eef3',zerolinecolor='#d5e1e9',automargin=True)
    fig.update_yaxes(gridcolor='#e7eef3',zerolinecolor='#d5e1e9',automargin=True)
    if kind in ('bar','scatter'):
        fig.update_traces(marker_color='#159a9c',marker_line_color='#ffffff',marker_line_width=1)
    elif kind=='line':
        fig.update_traces(line_color='#087f91',marker_color='#28a99f')
    return pio.to_html(fig,full_html=False,include_plotlyjs='cdn',config={'displayModeBar':False,'responsive':True},default_width='100%',default_height='310px')

@app.route('/')
def home():
    k=get_kpis()
    charts=[
      ('Category comparison','category_performance','bar','category','model_count','Vehicle records by EV category',None),
      ('Manufacturer portfolios','manufacturer_performance','bar','manufacturer','model_count','Top manufacturers by vehicle records',None),
      ('Battery mix','battery_mix','pie','battery_type','model_count','Battery technology distribution',None),
      ('Model-year profile','sales_by_year','line','model_year','model_records','Vehicle records by model year',None),
      ('Manufacturing footprint','country_footprint','bar','manufacturing_country','model_count','Vehicle records by manufacturing country',None),
      ('Price vs range','price_range_by_category','scatter','avg_price_usd','avg_range_km','Average price vs driving range by category','category'),
    ]
    built=[]
    for title,file,kind,x,y,chart_title,color in charts:
        df=read_agg(file)
        if file=='manufacturer_performance': df=df.head(12)
        built.append({'title':title,'html':chart_html(file,df,kind,x,y,chart_title,color)})
    scatter=read_agg('price_range_by_category')
    if DB_PATH.exists():
        with sqlite3.connect(DB_PATH) as con:
            records=pd.read_sql_query('SELECT vehicle_id, model_name, manufacturer, category, price_usd, range_km FROM ev_market WHERE price_usd IS NOT NULL AND range_km IS NOT NULL',con)
        if not records.empty:
            fig=px.scatter(records,x='price_usd',y='range_km',color='category',custom_data=['vehicle_id','model_name','manufacturer'],opacity=.45,template='plotly_white')
            fig.update_traces(marker=dict(size=5,line=dict(width=0)),hovertemplate='<b>%{customdata[1]}</b><br>Manufacturer: %{customdata[2]}<br>Category: %{fullData.name}<br>Price: $%{x:,.0f}<br>Range: %{y:,.0f} km<br>Vehicle ID: %{customdata[0]}<extra></extra>')
            fig.update_layout(autosize=True,margin=dict(l=28,r=18,t=48,b=38),paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',font=dict(color='#536779',family='DM Sans, sans-serif',size=11),legend_title_text='',title=dict(text='Each mark is one cleaned training record',font=dict(size=13,color='#18384c')))
            fig.update_xaxes(title='Price (USD)',gridcolor='#e7eef3',automargin=True)
            fig.update_yaxes(title='Driving range (km)',gridcolor='#e7eef3',automargin=True)
            built[-1]['html']=pio.to_html(fig,full_html=False,include_plotlyjs='cdn',config={'displayModeBar':False,'responsive':True},default_width='100%',default_height='350px')
    return render_template('index.html',k=k,charts=built,dashboard_url=DASHBOARD_URL,story_url=STORY_URL)

@app.route('/dashboard')
def dashboard():
    return render_template('tableau.html',page_title='Interactive Tableau Dashboard',embed_url=DASHBOARD_URL,kind='dashboard')

@app.route('/story')
def story():
    return render_template('tableau.html',page_title='EV Market Data Story',embed_url=STORY_URL,kind='story')

@app.route('/about')
def about():
    k=get_kpis(); return render_template('about.html',k=k)

@app.route('/health')
def health():
    return {'status':'ok','database_exists':DB_PATH.exists(),'database_path':str(DB_PATH),'tableau_dashboard_configured':bool(DASHBOARD_URL),'tableau_story_configured':bool(STORY_URL)}

if __name__=='__main__':
    app.run(host='127.0.0.1',port=int(os.getenv('PORT','5000')),debug=False)
