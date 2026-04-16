import streamlit as st
import pandas as pd
import numpy as np
from prophet import Prophet
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

# ========================================
# CONFIG
# ========================================
SHEET_ID = "1DNmM76FfZRtucCMEB-If0t1EEV-lPRn70pl9yP2ooeM"
st.set_page_config(page_title="MRP Pro Dashboard V4.4", layout="wide", page_icon="🤖")

# ========================================
# FONCTIONS UTILITAIRES
# ========================================
def trouver_colonne(df, noms_possibles):
    for nom in noms_possibles:
        if nom in df.columns:
            return nom
    for nom in noms_possibles:
        for col in df.columns:
            if nom.lower() in col.lower():
                return col
    return None

def to_numeric_safe(series):
    return pd.to_numeric(series, errors='coerce').fillna(0)

@st.cache_data(ttl=300)
def charger_donnees_google():
    base_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet="
    try:
        param = pd.read_csv(base_url + "Param")
        conso = pd.read_csv(base_url + "Conso")
        mrp = pd.read_csv(base_url + "MRP")
        fournis = pd.read_csv(base_url + "Fournisseurs")

        for df in [param, conso, mrp, fournis]:
            df.columns = df.columns.str.strip()
            for col in df.columns:
                if any(x in col.lower() for x in ['qte', 'stock', 'cout', 'moq', 'lead', 'taux', 'fiabilite', 'note']):
                    df[col] = to_numeric_safe(df[col])

        conso['date'] = pd.to_datetime(conso[trouver_colonne(conso, ['date'])], errors='coerce')
        mrp['date_besoin'] = pd.to_datetime(mrp[trouver_colonne(mrp, ['date_besoin'])], errors='coerce')
        return param, conso, mrp, fournis
    except Exception as e:
        st.error(f"❌ Erreur: {e}")
        return None, None, None

def calcul_eoq(demande_annuelle, cout_commande, cout_stockage_unit, cout_unitaire):
    if cout_stockage_unit <= 0 or demande_annuelle <= 0:
        return 0
    eoq = np.sqrt((2 * demande_annuelle * cout_commande) / cout_stockage_unit)
    return eoq

def classification_abc(df):
    df = df.sort_values('Valeur_Risque', ascending=False).reset_index(drop=True)
    df['Cumul'] = df['Valeur_Risque'].cumsum()
    total = df['Valeur_Risque'].sum()
    df['Cumul_%'] = df['Cumul'] / total * 100 if total > 0 else 0
    df['Classe'] = df['Cumul_%'].apply(lambda x: 'A' if x <= 80 else ('B' if x <= 95 else 'C'))
    return df

def analyser_mrp_appro(param, conso, mrp, fournis):
    col_mp_param = trouver_colonne(param, ['code_mp'])
    col_mp_conso = trouver_colonne(conso, ['code_mp'])
    col_qte_conso = trouver_colonne(conso, ['qte_consommee_kg', 'qte_consommee'])
    col_mp_mrp = trouver_colonne(mrp, ['code_mp'])
    col_qte_mrp = trouver_colonne(mrp, ['qte_besoin_kg', 'qte_besoin'])
    col_mp_fournis = trouver_colonne(fournis, ['code_mp'])

    resultats = []
    forecasts_dict = {}
    previsions_mensuelles = {}

    # Date dyal lyoma
    date_actuelle = datetime.now().date()
    # Khod akhr 12 chehar mn lyoma
    date_12_mois = date_actuelle - relativedelta(months=12)

    for _, mp_row in param.iterrows():
        code = mp_row[col_mp_param]
        stock_secu = mp_row.get('stock_secu_actuel', 0)
        lead_time = mp_row.get('lead_time_j', 14)
        moq = mp_row.get('moq_kg', 1000)
        cout_unit = mp_row.get('cout_unitaire', 0)
        designation = mp_row.get('designation', 'N/A')
        cout_commande = mp_row.get('cout_commande', 500)
        taux_stockage = mp_row.get('taux_stockage', 0.2)

        # 🔥 ROLLING: Khod ghir akhr 12 chehar
        hist = conso[(conso[col_mp_conso] == code) & (conso['date'].dt.date >= date_12_mois)].copy()
        hist = hist.dropna(subset=['date', col_qte_conso])

        conso_prevue_30j = 0
        conso_moy_j = 0
        demande_annuelle = 0
        has_forecast = False
        date_rupture = None
        risque_pct = 0
        prevision_m1 = 0
        prevision_m2 = 0
        prevision_m3 = 0

        if len(hist) >= 10:
            df_prophet = hist.groupby('date')[col_qte_conso].sum().reset_index()
            df_prophet.columns = ['ds', 'y']
            df_prophet = df_prophet.dropna()

            if len(df_prophet) >= 10:
                try:
                    m = Prophet(yearly_seasonality=True, weekly_seasonality=True, daily_seasonality=False)
                    m.fit(df_prophet)
                    # Forecast 90 jours = 3 chhour
                    future = m.make_future_dataframe(periods=90)
                    forecast = m.predict(future)

                    # Prévisions mensuelles
                    fc_future = forecast[forecast['ds'].dt.date > date_actuelle].copy()
                    if len(fc_future) >= 90:
                        prevision_m1 = fc_future.head(30)['yhat'].sum()
                        prevision_m2 = fc_future.iloc[30:60]['yhat'].sum()
                        prevision_m3 = fc_future.iloc[60:90]['yhat'].sum()
                        conso_prevue_30j = prevision_m1
                    else:
                        conso_prevue_30j = fc_future['yhat'].sum()

                    conso_prevue_30j = max(0, conso_prevue_30j)
                    conso_moy_j = df_prophet['y'].mean()
                    demande_annuelle = conso_moy_j * 365
                    forecasts_dict[code] = forecast
                    has_forecast = True

                    # 🔥 IA: Calcul Date Rupture - MHM: Ila stock négatif ra rupture daba
                    if stock_secu <= 0:
                        date_rupture = datetime.now().date()
                        risque_pct = 100
                    else:
                        stock_simule = stock_secu
                        for idx, row in forecast.iterrows():
                            if row['ds'].date() <= date_actuelle:
                                continue
                            stock_simule -= max(0, row['yhat'])
                            if stock_simule <= 0:
                                date_rupture = row['ds'].date()
                                jours_restants = (date_rupture - date_actuelle).days
                                risque_pct = max(0, min(100, 100 - (jours_restants / lead_time * 100)))
                                break
                except:
                    conso_moy_j = df_prophet['y'].mean() if len(df_prophet) > 0 else 0
                    conso_prevue_30j = conso_moy_j * 30
                    prevision_m1 = conso_prevue_30j
                    prevision_m2 = conso_prevue_30j
                    prevision_m3 = conso_prevue_30j
                    demande_annuelle = conso_moy_j * 365

        besoin_mrp = mrp[mrp[col_mp_mrp] == code][col_qte_mrp].sum()
        besoin_mrp = 0 if pd.isna(besoin_mrp) else besoin_mrp

        couverture_j = stock_secu / conso_moy_j if conso_moy_j > 0 else 999
        besoin_total = besoin_mrp + conso_prevue_30j
        ecart = stock_secu - besoin_total
        valeur_risque = abs(ecart) * cout_unit if ecart < 0 else 0

        cout_stockage_unit = cout_unit * taux_stockage
        eoq = calcul_eoq(demande_annuelle, cout_commande, cout_stockage_unit, cout_unit)
        point_commande = conso_moy_j * lead_time

        # 🔥 FIX: Statut IA - Ila Écart négatif DIMA Urgent
        date_cmd_optimale = None
        qte_suggeree_ia = 0
        statut_ia = "✅ Sécurisé"

        if ecart < 0:
            # Ila négatif = DIMA urgent
            risque_pct = 100
            date_rupture = date_actuelle
            date_cmd_optimale = date_actuelle # Commandi daba
            qte_suggeree_ia = max(abs(ecart), eoq, moq)
            statut_ia = "🔴 Urgent"
        elif date_rupture:
            date_cmd_optimale = date_rupture - timedelta(days=lead_time)
            jours_avant_cmd = (date_cmd_optimale - date_actuelle).days
            qte_suggeree_ia = max(eoq, moq)

            if jours_avant_cmd <= 0:
                statut_ia = "🔴 Urgent"
            elif jours_avant_cmd <= 7:
                statut_ia = "🟠 À Planifier"
            else:
                statut_ia = "🟡 Surveiller"

        # Statut Normal
        if len(hist) == 0:
            statut = "⚪ PAS DE DONNÉES"
            action = "Vérifier historique conso"
        elif ecart < -moq:
            statut = "🔴 CRITIQUE"
            action = f"Commander {max(abs(ecart), eoq):,.0f} kg"
        elif ecart < 0:
            statut = "🟠 TENSION"
            action = f"Commander {max(moq, eoq):,.0f} kg"
        else:
            statut = "🟢 ALIGNÉ"
            action = "Pas d'action"

        fournis_mp = fournis[fournis[col_mp_fournis] == code].copy()
        if len(fournis_mp) > 0:
            fournis_mp['score'] = (
                fournis_mp['taux_service_%'].fillna(0) * 0.4 +
                fournis_mp['fiabilite_%'].fillna(0) * 0.3 +
                fournis_mp['note_qualite_5'].fillna(0) * 20 * 0.3
            )
            best = fournis_mp.nlargest(1, 'score').iloc[0]
            fournisseur = best['nom_fournisseur']
            delai = best['lead_time_j']
            score_fourni = best['score']
        else:
            fournisseur = "N/A"
            delai = lead_time
            score_fourni = 0

        resultats.append({
            'Code_MP': code,
            'Désignation': designation,
            'Stock': stock_secu,
            'Besoin_MRP': besoin_mrp,
            'Conso_30j': conso_prevue_30j,
            'Écart': ecart,
            'Couverture_J': couverture_j,
            'Valeur_Risque': valeur_risque,
            'EOQ': eoq,
            'Point_Cmd': point_commande,
            'Statut': statut,
            'Action': action,
            'Fournisseur': fournisseur,
            'Délai': delai,
            'Score_Fourni': score_fourni,
            'Conso_Moy_J': conso_moy_j,
            'Has_Forecast': has_forecast,
            'Cout_Unit': cout_unit,
            'Date_Rupture_Prévue': date_rupture,
            'Date_Cmd_Optimale': date_cmd_optimale,
            'Qté_Suggérée_IA': qte_suggeree_ia,
            'Risque_%': risque_pct,
            'Statut_IA': statut_ia,
            'Prév_M+1': prevision_m1,
            'Prév_M+2': prevision_m2,
            'Prév_M+3': prevision_m3
        })

    df_result = pd.DataFrame(resultats)
    df_result = classification_abc(df_result)
    return df_result, forecasts_dict, fournis

# ========================================
# INTERFACE
# ========================================
st.title("🤖 MRP Pro Dashboard V4.4 - Rolling Forecast")
st.caption("Rolling 12 Mois + Prévision Mensuelle Auto + Plan Appro IA")

param, conso, mrp, fournis = charger_donnees_google()

if param is None:
    st.stop()

st.sidebar.header("⚙️ Configuration")
st.sidebar.info(f"📅 Date: {datetime.now().strftime('%d/%m/%Y')}\n\n🔄 Rolling: Akhr 12 chehar")
if st.sidebar.button("🔄 Actualiser Données"):
    st.cache_data.clear()
    st.rerun()

df_result, forecasts, df_fournis_all = analyser_mrp_appro(param, conso, mrp, fournis)

if len(df_result) == 0:
    st.warning("Aucun MP dans Param")
    st.stop()

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 Dashboard", "🤖 Plan Appro IA", "📅 Prévisions Mensuelles", "🏭 Fournisseurs", "🎯 Simulateur", "💬 Chat IA"])

with tab1:
    st.subheader("📊 KPIs Globaux")
    col1, col2, col3, col4, col5, col6 = st.columns(6)

    total_mp = len(df_result)
    critiques = len(df_result[df_result['Statut'].str.contains('CRITIQUE')])
    urgents_ia = len(df_result[df_result['Statut_IA'].str.contains('Urgent')])
    classe_a = len(df_result[df_result['Classe'] == 'A'])
    valeur_risque_tot = df_result['Valeur_Risque'].sum()
    couverture_moy = df_result[df_result['Couverture_J'] < 999]['Couverture_J'].mean()

    col1.metric("📦 Total MPs", total_mp)
    col2.metric("🔴 Critiques", critiques)
    col3.metric("🤖 Urgents IA", urgents_ia)
    col4.metric("💎 Classe A", classe_a)
    col5.metric("💰 Valeur Risque", f"{valeur_risque_tot:,.0f} MAD")
    col6.metric("📅 Couv. Moy", f"{couverture_moy:.0f}j")

    st.divider()
    st.subheader(f"📋 Détail par MP - {total_mp} MPs")

    colf1, colf2, colf3 = st.columns(3)
    statut_filter = colf1.multiselect("Statut", df_result['Statut'].unique(), default=df_result['Statut'].unique())
    classe_filter = colf2.multiselect("Classe ABC", ['A', 'B', 'C'], default=['A', 'B', 'C'])
    df_filtre = df_result[df_result['Statut'].isin(statut_filter) & df_result['Classe'].isin(classe_filter)]

    st.dataframe(
        df_filtre[['Code_MP', 'Désignation', 'Classe', 'Stock', 'Écart', 'Couverture_J', 'Statut_IA', 'Date_Cmd_Optimale', 'Action']],
        use_container_width=True, height=400,
        column_config={
            "Couverture_J": st.column_config.NumberColumn("Couv. J", format="%.0f j"),
            "Écart": st.column_config.NumberColumn(format="%d kg"),
            "Date_Cmd_Optimale": st.column_config.DateColumn("Date Cmd IA", format="DD/MM/YYYY")
        }
    )

    csv = df_filtre.to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 Télécharger CSV", csv, f"MRP_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")

with tab2:
    st.subheader("🤖 Plan d'Approvisionnement IA - Zéro Rupture")
    st.caption("L'IA kat 7sseb lik automatiquement mn Prophet + Rolling 12 mois")

    df_ia = df_result[df_result['Date_Cmd_Optimale'].notna()].copy()
    df_ia = df_ia.sort_values('Date_Cmd_Optimale')

    if len(df_ia) == 0:
        st.success("✅ Aucune commande à planifier. Kolchi sécurisé!")
    else:
        col1, col2, col3, col4 = st.columns(4)
        urgents = len(df_ia[df_ia['Statut_IA'].str.contains('Urgent')])
        a_planifier = len(df_ia[df_ia['Statut_IA'].str.contains('À Planifier')])
        surveiller = len(df_ia[df_ia['Statut_IA'].str.contains('Surveiller')])
        valeur_cmd_tot = (df_ia['Qté_Suggérée_IA'] * df_ia['Cout_Unit']).sum()

        col1.metric("🔴 Urgents", urgents)
        col2.metric("🟠 À Planifier", a_planifier)
        col3.metric("🟡 Surveiller", surveiller)
        col4.metric("💰 Valeur Cmd Total", f"{valeur_cmd_tot:,.0f} MAD")

        st.divider()

        st.dataframe(
            df_ia[['Code_MP', 'Désignation', 'Statut_IA', 'Date_Rupture_Prévue', 'Date_Cmd_Optimale', 'Qté_Suggérée_IA', 'Fournisseur', 'Risque_%']],
            use_container_width=True,
            height=400,
            column_config={
                "Date_Rupture_Prévue": st.column_config.DateColumn("Rupture Prévue", format="DD/MM/YYYY"),
                "Date_Cmd_Optimale": st.column_config.DateColumn("Commander Avant", format="DD/MM/YYYY"),
                "Qté_Suggérée_IA": st.column_config.NumberColumn("Qté IA (kg)", format="%.0f"),
                "Risque_%": st.column_config.ProgressColumn("Risque", min_value=0, max_value=100, format="%.0f%%")
            }
        )

        # Timeline
        st.subheader("📅 Timeline Commandes - 90 prochains jours")
        df_timeline = df_ia[df_ia['Date_Cmd_Optimale'] <= datetime.now().date() + timedelta(days=90)].copy()

        if len(df_timeline) > 0:
            fig = go.Figure()
            for _, row in df_timeline.iterrows():
                color = '#FF6B6B' if 'Urgent' in row['Statut_IA'] else '#FFA500' if 'Planifier' in row['Statut_IA'] else '#4ECDC4'
                fig.add_trace(go.Scatter(
                    x=[row['Date_Cmd_Optimale']],
                    y=[row['Code_MP']],
                    mode='markers+text',
                    marker=dict(size=row['Risque_%']/2 + 10, color=color),
                    text=[f"{row['Qté_Suggérée_IA']:,.0f} kg"],
                    textposition="middle right",
                    name=row['Code_MP'],
                    hovertext=f"Commander {row['Qté_Suggérée_IA']:,.0f} kg<br>Chez {row['Fournisseur']}<br>Risque: {row['Risque_%']:.0f}%"
                ))

            fig.update_layout(
                title="Calendrier Commandes Optimales",
                xaxis_title="Date Commande",
                yaxis_title="MP",
                height=400,
                showlegend=False
            )
            st.plotly_chart(fig, use_container_width=True)

        csv_ia = df_ia.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 Télécharger Plan Appro IA", csv_ia, f"Plan_Appro_IA_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")

with tab3:
    st.subheader("📅 Prévisions Mensuelles - Rolling 12 Mois")
    st.caption("Kola chehar kay t'actualisa wa7do. Kay akhd akhr 12 chehar w y forecast 3 chhour l9ddam.")

    df_prev = df_result[['Code_MP', 'Désignation', 'Prév_M+1', 'Prév_M+2', 'Prév_M+3', 'Conso_Moy_J']].copy()

    # Calculer nom dyal chhoura
    mois1 = (datetime.now() + relativedelta(months=1)).strftime('%b %Y')
    mois2 = (datetime.now() + relativedelta(months=2)).strftime('%b %Y')
    mois3 = (datetime.now() + relativedelta(months=3)).strftime('%b %Y')

    df_prev = df_prev.rename(columns={
        'Prév_M+1': f'Prév {mois1}',
        'Prév_M+2': f'Prév {mois2}',
        'Prév_M+3': f'Prév {mois3}',
        'Conso_Moy_J': 'Moy/J (kg)'
    })

    st.dataframe(
        df_prev,
        use_container_width=True,
        height=400,
        column_config={
            f'Prév {mois1}': st.column_config.NumberColumn(format="%.0f kg"),
            f'Prév {mois2}': st.column_config.NumberColumn(format="%.0f kg"),
            f'Prév {mois3}': st.column_config.NumberColumn(format="%.0f kg"),
            'Moy/J (kg)': st.column_config.NumberColumn(format="%.0f")
        }
    )

    # Graphique évolution
    mp_select_prev = st.selectbox("Choisir MP pour voir évolution", df_result['Code_MP'].unique())
    mp_data_prev = df_result[df_result['Code_MP'] == mp_select_prev].iloc[0]

    fig_prev = go.Figure()
    fig_prev.add_trace(go.Bar(
        x=[mois1, mois2, mois3],
        y=[mp_data_prev['Prév_M+1'], mp_data_prev['Prév_M+2'], mp_data_prev['Prév_M+3']],
        marker_color=['#4ECDC4', '#FFA500', '#FF6B'],
        text=[f"{mp_data_prev['Prév_M+1']:,.0f}", f"{mp_data_prev['Prév_M+2']:,.0f}", f"{mp_data_prev['Prév_M+3']:,.0f}"],
        textposition='auto'
    ))
    fig_prev.update_layout(
        title=f"Prévision Conso {mp_select_prev} - 3 Mois Prochains",
        yaxis_title="Kg",
        height=350
    )
    st.plotly_chart(fig_prev, use_container_width=True)

with tab4:
    st.subheader("🏭 Analyse Fournisseurs")
    st.write(f"**Total fournisseurs:** {len(df_fournis_all)}")

    df_fourni_score = df_result[df_result['Fournisseur']!= 'N/A'].groupby('Fournisseur').agg({
        'Score_Fourni': 'mean',
        'Code_MP': 'count',
        'Valeur_Risque': 'sum'
    }).reset_index().rename(columns={'Code_MP': 'Nb_MPs'}).sort_values('Score_Fourni', ascending=False)

    col1, col2 = st.columns(2)
    with col1:
        if len(df_fourni_score) > 0:
            fig = px.bar(df_fourni_score, x='Fournisseur', y='Score_Fourni', title="Score Moyen",
                         color='Score_Fourni', color_continuous_scale='RdYlGn', text='Nb_MPs')
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        if df_fourni_score['Valeur_Risque'].sum() > 0:
            fig2 = px.pie(df_fourni_score, values='Valeur_Risque', names='Fournisseur', title="Valeur à Risque")
            st.plotly_chart(fig2, use_container_width=True)

    st.dataframe(df_fournis_all, use_container_width=True)

with tab5:
    st.subheader("🎯 Simulateur What-If - VERSION VISUELLE")
    st.caption("Chouf l'impact dyal commande 9bl ma dirha 📊")

    col1, col2, col3 = st.columns(3)
    mp_sim = col1.selectbox("MP à simuler", df_result['Code_MP'].unique(), key="sim_mp_v4")
    qte_sim = col2.number_input("Quantité à commander (kg)", min_value=0, value=10000, step=1000, key="sim_qte_v4")

    mp_data_sim = df_result[df_result['Code_MP'] == mp_sim].iloc[0]
    nouveau_stock = mp_data_sim['Stock'] + qte_sim
    nouveau_ecart = nouveau_stock - (mp_data_sim['Besoin_MRP'] + mp_data_sim['Conso_30j'])
    nouvelle_couv = nouveau_stock / mp_data_sim['Conso_Moy_J'] if mp_data_sim['Conso_Moy_J'] > 0 else 999

    st.divider()
    st.subheader(f"📊 Impact Visuel - {mp_sim}")

    col_g1, col_g2, col_g3 = st.columns(3)

    with col_g1:
        fig_stock = go.Figure()
        fig_stock.add_trace(go.Bar(
            x=['Stock Actuel', 'Après Commande'],
            y=[mp_data_sim['Stock'], nouveau_stock],
            marker_color=['#FF6B', '#4ECDC4'],
            text=[f"{mp_data_sim['Stock']:,.0f}", f"{nouveau_stock:,.0f}"],
            textposition='auto',
        ))
        fig_stock.update_layout(title="📦 Stock (kg)", yaxis_title="Kg", showlegend=False, height=300)
        st.plotly_chart(fig_stock, use_container_width=True)

    with col_g2:
        color_avant = '#FF6B6B' if mp_data_sim['Écart'] < 0 else '#4ECDC4'
        color_apres = '#FF6B6B' if nouveau_ecart < 0 else '#4ECDC4'
        fig_ecart = go.Figure()
        fig_ecart.add_trace(go.Bar(
            x=['Écart Actuel', 'Après Commande'],
            y=[mp_data_sim['Écart'], nouveau_ecart],
            marker_color=[color_avant, color_apres],
            text=[f"{mp_data_sim['Écart']:,.0f}", f"{nouveau_ecart:,.0f}"],
            textposition='auto',
        ))
        fig_ecart.add_hline(y=0, line_dash="dash", line_color="black", annotation_text="Seuil 0")
        fig_ecart.update_layout(title="⚖️ Écart (kg)", yaxis_title="Kg", showlegend=False, height=300)
        st.plotly_chart(fig_ecart, use_container_width=True)

    with col_g3:
        color_couv_avant = '#FF6B6B' if mp_data_sim['Couverture_J'] < 7 else '#FFA500' if mp_data_sim['Couverture_J'] < 14 else '#4ECDC4'
        color_couv_apres = '#FF6B6B' if nouvelle_couv < 7 else '#FFA500' if nouvelle_couv < 14 else '#4ECDC4'
        fig_couv = go.Figure()
        fig_couv.add_trace(go.Bar(
            x=['Couv. Actuelle', 'Après Commande'],
            y=[mp_data_sim['Couverture_J'], nouvelle_couv],
            marker_color=[color_couv_avant, color_couv_apres],
            text=[f"{mp_data_sim['Couverture_J']:.0f}j", f"{nouvelle_couv:.0f}j"],
            textposition='auto',
        ))
        fig_couv.add_hline(y=7, line_dash="dash", line_color="red", annotation_text="Critique")
        fig_couv.add_hline(y=14, line_dash="dash", line_color="orange", annotation_text="Tension")
        fig_couv.update_layout(title="📅 Couverture (jours)", yaxis_title="Jours", showlegend=False, height=300)
        st.plotly_chart(fig_couv, use_container_width=True)

    st.divider()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Nouveau Stock", f"{nouveau_stock:,.0f} kg", f"+{qte_sim:,.0f}")
    col2.metric("Nouvel Écart", f"{nouveau_ecart:,.0f} kg", f"{nouveau_ecart - mp_data_sim['Écart']:,.0f}")
    col3.metric("Nouvelle Couverture", f"{nouvelle_couv:.0f} jours", f"{nouvelle_couv - mp_data_sim['Couverture_J']:.0f}")
    col4.metric("Coût Commande", f"{qte_sim * mp_data_sim['Cout_Unit']:,.0f} MAD")

    if nouveau_ecart >= 0:
        st.success(f"✅ **VERDICT: ALIGNÉ** → Avec {qte_sim:,.0f} kg, **{mp_sim} ywlli VERT**! Couverture {nouvelle_couv:.0f} jours. Plus de risque! 🎉")
    elif nouveau_ecart >= -mp_data_sim['EOQ']:
        st.warning(f"🟠 **VERDICT: TENSION** → Avec {qte_sim:,.0f} kg, **{mp_sim} ba9i ORANGE**. Khass {abs(nouveau_ecart):,.0f} kg zayda.")
    else:
        st.error(f"🔴 **VERDICT: CRITIQUE** → Avec {qte_sim:,.0f} kg, **{mp_sim} ba9i ROUGE**. Khass {abs(nouveau_ecart):,.0f} kg zayda!")

with tab6:
    st.subheader("💬 Chat IA Pro")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Ex: 'Plan commande?' 'Prévision MP_PP?' 'Risque rupture?'"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        prompt_lower = prompt.lower()
        response = ""

        if "plan" in prompt_lower or "commande" in prompt_lower:
            df_cmd = df_result[df_result['Date_Cmd_Optimale'].notna()].sort_values('Date_Cmd_Optimale')
            if len(df_cmd) > 0:
                response = f"📅 **Plan Commande IA - {len(df_cmd)} MPs:**\n\n"
                for _, row in df_cmd.head(10).iterrows():
                    response += f"**{row['Date_Cmd_Optimale'].strftime('%d/%m')}**: {row['Code_MP']} - {row['Qté_Suggérée_IA']:,.0f} kg chez {row['Fournisseur']} ({row['Statut_IA']})\n"
            else:
                response = "✅ Aucune commande à planifier. Kolchi sécurisé!"

        elif "prévision" in prompt_lower or "prevision" in prompt_lower:
            for mp in df_result['Code_MP'].unique():
                if mp.lower() in prompt_lower:
                    row = df_result[df_result['Code_MP'] == mp].iloc[0]
                    mois1 = (datetime.now() + relativedelta(months=1)).strftime('%b %Y')
                    mois2 = (datetime.now() + relativedelta(months=2)).strftime('%b %Y')
                    mois3 = (datetime.now() + relativedelta(months=3)).strftime('%b %Y')
                    response = f"**Prévisions {mp}:**\n- {mois1}: {row['Prév_M+1']:,.0f} kg\n- {mois2}: {row['Prév_M+2']:,.0f} kg\n- {mois3}: {row['Prév_M+3']:,.0f} kg\n\n💡 Basé 3la akhr 12 chehar"
                    break
            if not response:
                response = "**Prévisions 3 Mois:**\n" + "\n".join([f"- {r['Code_MP']}: {r['Prév_M+1']:,.0f} kg" for _, r in df_result.nlargest(5, 'Prév_M+1').iterrows()])

        elif "risque" in prompt_lower or "rupture" in prompt_lower:
            df_risk = df_result[df_result['Risque_%'] > 0].sort_values('Risque_%', ascending=False)
            if len(df_risk) > 0:
                response = f"⚠️ **{len(df_risk)} MPs avec
