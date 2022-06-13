from bs4 import BeautifulSoup
import requests
import pandas as pd
import streamlit as st
import json
from shapely.geometry import Polygon, MultiPolygon
import folium
import geopandas as gpd
from streamlit_folium import folium_static
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import altair as alt
import sqlite3

with st.echo(code_location='below'):
    def get_top20_death_rate(url): ##веб-скрэппинг, пандас
        df=dict()
        page = requests.get(url)
        page = BeautifulSoup(page.text, features="html.parser")
        for td in page.find_all(class_='content-table-standard-weight'):
            if int(td.text)<21:
                df[int(td.text)]=[td.next_sibling.find(class_='text-button content-table-link').text, td.next_sibling.next_sibling.text]
            else:
                break
        df=pd.DataFrame.from_dict(df, orient='index', columns=['country', 'death rate'])
        df.index.set_names('rank', inplace=True)
        return df
    def map_top20(data): ##геоданные, пандас
        # with open('countries.geojson', encoding='utf-8') as f:
        #     a = json.load(f)
        r = requests.get('https://raw.githubusercontent.com/smthsmthsmthing/countries_map/main/countries.geojson')
        a = r.json()
        coordinates=[]
        for i in data['country']:
            for country in a['features']:
                if country['properties']["ADMIN"].find(i)!=-1:
                    if type(country['geometry']['coordinates'][0][0][0])==list:
                        parts = []
                        for part in country['geometry']['coordinates']:
                            parts.append(Polygon(part[0]))
                        coordinates.append(MultiPolygon(parts))
                    else:
                        coordinates.append(Polygon(country['geometry']['coordinates'][0]))
        topgeo=data
        topgeo['poly']=coordinates
        topgeo=gpd.GeoDataFrame(topgeo, geometry='poly')
        m = folium.Map(location=[0, 0], zoom_start=2)
        for _, r in topgeo.iterrows():
            geo_j = gpd.GeoSeries(r['poly']).to_json()
            geo_j = folium.GeoJson(data=geo_j,
                                   style_function=lambda x: {'fillColor': 'orange'})
            folium.Popup(f'<p>Country: <\p>{r["country"]}<p>Death rate: </p>{r["death rate"]}').add_to(geo_j)
            geo_j.add_to(m)
        folium_static(m)
        return(topgeo)
    def get_ISO(top):#сложный веб-скреппинг с selenium, регулярные выражения
        ISO=[]
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
        for _, i in top.iterrows():
            url = 'https://en.wikipedia.org/wiki/'+i['country']
            driver.get(url)
            ISO.append(driver.find_element_by_css_selector("[href*=ISO_3166-2]").text)
            #ISO.append((find_element(by=By.CSS_SELECTOR, value="[href*=ISO_3166-2]")).text)
        top['ISO']=ISO
        return top

    def economy(top_with_ec):#API
        GDP=[]
        Gini=[]
        for _, i in top_with_ec.iterrows():
            entrypoint1="http://api.worldbank.org/countries/" + i['ISO'] + "/indicators/NY.GDP.PCAP.CD?format=json&date=2017"
            entrypoint2 = "http://api.worldbank.org/countries/" + i['ISO'] + "/indicators/SI.POV.GINI?format=json&date=2017"
            r1=requests.get(entrypoint1).json()
            r2 = requests.get(entrypoint2).json()
            GDP.append(r1[1][0]['value'])
            Gini.append(r2[1][0]['value'])
        top_with_ec['GDP']=GDP
        top_with_ec['Gini'] =Gini
        return top_with_ec
    def plot_ec(data): ## advanced plotting
        data_select = st.selectbox("Какие данные вы хотите увидеть?", ['GDP per capita', 'Gini'])
        if data_select=='GDP per capita':
            chart = (
                alt.Chart(data.drop(['poly'], axis=1)).mark_circle().encode(x='death rate', y='GDP', tooltip=['death rate', 'GDP', 'country'],
                                                                )
            )
            st.altair_chart(
                (
                        chart+chart.transform_loess('death rate', 'GDP').mark_line()
                ).interactive(), True
            )
        else:
            chart = (
                alt.Chart(data.drop(['poly'], axis=1)).mark_circle().encode(x='death rate', y='Gini',
                                                                            tooltip=['death rate', 'Gini', 'country'],
                                                                            )
            )
            st.altair_chart(
                (
                    chart+chart.transform_loess('death rate', 'Gini').mark_line()
                ).interactive(), True
            )


    def covid_cases(): #sql
        conn = sqlite3.connect("data")
        c = conn.cursor()
        df = pd.read_csv('COVID-19 Coronavirus.csv')
        st.dataframe(df)

        #df=pd.read_csv('https://www.dropbox.com/s/rknfrrtoukzpc01/owid-covid-data.csv?dl=1')
        # df = pd.read_csv('owid-covid-data.csv')
        #df = pd.read_csv("../input/covid19-dataset/owid-covid-data.csv")
        df.to_sql(name='data', con=conn, if_exists='replace')
        get_data=f'SELECT Country,Population, "Total Cases","Total Deaths" FROM data'
        return pd.read_sql(get_data,conn)
    def plot_covid(covid_data, top20): #pandas
        for i in covid_data['Сountry']:
            i=str(i)
            if i not in (top20['country'].tolist()):
                covid_data = covid_data.replace({i: float('nan')}).dropna()
        for i in top20['country']:
            i=str(i)
        #covid_data.rename(columns= {'location':'country'}, inplace=True)
        top_with_covid=top20.merge(covid_data, how='left', on='country')
        top_with_covid.drop('poly', axis=1, inplace=True)
        top_with_covid.drop('ISO', axis=1, inplace=True)
        st.write(top_with_covid)
        X_axis = st.selectbox("Какие данные вы хотите увидеть на 0X?", top_with_covid.columns)
        Y_axis= st.selectbox("Какие данные вы хотите увидеть на 0Y?", top_with_covid.columns)
        chart = (alt.Chart(top_with_covid)).mark_circle().encode(x=X_axis, y=Y_axis, tooltip=['country', 'death rate'])
        st.altair_chart(
            (
                    chart + chart.transform_loess(X_axis, Y_axis).mark_line()
            ).interactive(), True
        )

    """
    Attention! Для удобства проверяющего в начале каждой функции кода написано, какие инструменты в ней использовались.
    """
    """
    Этот проект посвящен смертности населения.
    """
    """
    Посмотрим, какие страны входят в топ-20 по смертности на тысячу населения в 2022 году
    """
    top20=get_top20_death_rate("https://www.cia.gov/the-world-factbook/field/death-rate/country-comparison")
    st.dataframe(top20)
    """
    А как они расположены на карте? Нажмите на страну, чтобы узнать информацию о ней
    """
    topgeo=map_top20(top20)
    """
    Теперь попробуем узнать что-нибудь про эти страны. Например, их ВВП и индекс Джини. Здесь мы будем использовать API World Bank, он может не сработать без впн. Или может не сработать с впн.
    Для этого сначала узнаем ISO коды стран с помощью веб-скрэппинга википедии
    """
    top_with_ec=economy(get_ISO(top20))
    plot_ec(top_with_ec)

    """
    Выясняется, что зависимость от экономических показателей если и есть, то слабая. Посмотрим на что-нибудь еще, например - на смерти от ковида-19.
    """
    covid=covid_cases()
    """
    Посмотрим, правда ли, что сейчас, в 2022, ковид составляет существенную долю смертности - для этого посмотрим, есть ли зависимости между смертностью от ковида, заболеваемостью и смертностью от всех причин в 2022 году. Ну и заодно узнаем что-нибудь про ковид - вдруг есть зависимость между ним и экономическими показателями?
    """
    plot_covid(covid,top20)