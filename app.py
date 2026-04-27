import streamlit as st
import pandas as pd
import plotly.express as px

# ==================================================
# CONFIG
# ==================================================
st.set_page_config(
    page_title="MRP Pro V4",
    page_icon="🏭",
    layout="wide"
)

# ==================================================
# PASSWORD LOGIN
# ==================================================
PASSWORD = "1234"   # بدلها بالباسوورد لي بغيتي

if "logged" not in st.session_state:
    st.session_state.logged = False

if not st.session_state.logged:
    st.markdown(
        """
        <h1 style='text-align:center;margin-top:80px;'>🏭 MRP PRO LOGIN</h1>
        <p style='text-align:center;color:gray;'>Plateforme Approvisionnement Intelligente</p>
        """,
        unsafe_allow_html=True
    )

    p = st.text_input("Mot de passe", type="password")

    if st.button("Connexion"):
        if p == PASSWORD:
            st.session_state.logged = True
            st.rerun()
        else:
            st.error("Mot de passe incorrect")

    st.stop()

# ==================================================
# GOOGLE SHEET
# ==================================================
SHEET_ID = "1DNmM76FfZRtucCMEB-If0t1EEV-lPRn70pl9yP2ooeM"

def load_sheet(sheet):
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={sheet}"
    return pd.read_csv(url)

@st.cache_data(ttl=60)
def load_all():
    return {
        "param": load_sheet("Param"),
        "conso": load_sheet("Conso"),
        "fournisseurs": load_sheet("Fournisseurs"),
        "mrp": load_sheet("MRP")
    }

# ==================================================
# CSS
# ==================================================
st.markdown("""
<style>
.main {background:#f6f8fb;}

.kpi-card{
border-radius:22px;
padding:22px;
min-height:165px;
color:white;
box-shadow:0 12px 24px rgba(0,0,0,.10);
margin-bottom:18px;
}

.kpi-title{
font-size:21px;
font-weight:700;
opacity:.95;
}

.kpi-value{
font-size:42px;
font-weight:900;
margin-top:25px;
line-height:1.1;
word-break:break-word;
}

.block{
background:white;
padding:18px;
border-radius:20px;
box-shadow:0 8px 18px rgba(0,0,0,.06);
margin-top:15px;
}
</style>
""", unsafe_allow_html=True)

# ==================================================
# KPI CARD
# ==================================================
def card(title, value, color):
    st.markdown(f"""
    <div class='kpi-card' style='background:{color};'>
        <div class='kpi-title'>{title}</div>
        <div class='kpi-value'>{value}</div>
    </div>
    """, unsafe_allow_html=True)

# ==================================================
# DATA
# ==================================================
data = load_all()

param = data["param"]
conso = data["conso"]

conso = conso.rename(columns={
    "CODE matière":"code_mp",
    "conso journaliere MP en KG":"conso_jour_kg"
})

resume = conso.groupby("code_mp", as_index=False)["conso_jour_kg"].sum()

plan = param.merge(resume, on="code_mp", how="left")
plan["conso_jour_kg"] = plan["conso_jour_kg"].fillna(0)

plan["couverture_j"] = plan.apply(
    lambda x: 999999 if x["conso_jour_kg"] == 0 else x["stock_actuel"] / x["conso_jour_kg"],
    axis=1
)

plan["qte_commande"] = ((plan["conso_jour_kg"] * 30) - plan["stock_actuel"]).clip(lower=0)

def statut(x):
    if x <= 7:
        return "URGENT"
    elif x <= 15:
        return "CRITIQUE"
    else:
        return "OK"

plan["statut"] = plan["couverture_j"].apply(statut)

# ==================================================
# HEADER
# ==================================================
st.title("🏭 MRP Pro V4 - Dashboard Intelligent")
st.caption("Approvisionnement • Stock • Fournisseurs • Pilotage temps réel")

# ==================================================
# KPI (3 فوق + 3 تحت)
# ==================================================
cov = round(plan["couverture_j"].replace(999999, pd.NA).dropna().mean(),1)

r1c1,r1c2,r1c3 = st.columns(3)

with r1c1:
    card("Total MP", len(plan), "linear-gradient(135deg,#2563eb,#1e3a8a)")
with r1c2:
    card("À commander", int((plan["qte_commande"]>0).sum()), "linear-gradient(135deg,#7c3aed,#581c87)")
with r1c3:
    card("Critiques", int(plan["statut"].isin(["URGENT","CRITIQUE"]).sum()), "linear-gradient(135deg,#dc2626,#991b1b)")

r2c1,r2c2,r2c3 = st.columns(3)

with r2c1:
    card("Commande kg", f"{plan['qte_commande'].sum():,.0f}", "linear-gradient(135deg,#ea580c,#9a3412)")
with r2c2:
    card("Stock kg", f"{plan['stock_actuel'].sum():,.0f}", "linear-gradient(135deg,#0891b2,#155e75)")
with r2c3:
    card("Couverture j", cov, "linear-gradient(135deg,#16a34a,#166534)")

# ==================================================
# CHARTS
# ==================================================
c1,c2 = st.columns(2)

with c1:
    st.subheader("📊 Pareto commandes")

    pareto = plan.sort_values("qte_commande", ascending=False)

    fig = px.bar(
        pareto,
        x="code_mp",
        y="qte_commande",
        color="qte_commande",
        color_continuous_scale="Blues"
    )
    fig.update_layout(height=420)
    st.plotly_chart(fig, use_container_width=True)

with c2:
    st.subheader("🧭 Statuts")

    stat = plan["statut"].value_counts().reset_index()
    stat.columns = ["statut","nb"]

    fig2 = px.pie(
        stat,
        names="statut",
        values="nb",
        color="statut",
        color_discrete_map={
            "URGENT":"#dc2626",
            "CRITIQUE":"#f59e0b",
            "OK":"#16a34a"
        },
        hole=0.45
    )
    fig2.update_layout(height=420)
    st.plotly_chart(fig2, use_container_width=True)

# ==================================================
# TABLEAU
# ==================================================
st.subheader("📦 Plan Approvisionnement")

show = plan[[
    "code_mp",
    "designation",
    "stock_actuel",
    "conso_jour_kg",
    "couverture_j",
    "qte_commande",
    "statut"
]]

st.dataframe(show, use_container_width=True, height=450)

# ==================================================
# IA CHAT SIMPLE
# ==================================================
st.subheader("🤖 Chat IA")

question = st.text_input("Pose une question")

if question:
    q = question.lower()

    if "urgent" in q:
        st.write(plan[plan["statut"]=="URGENT"][["code_mp","qte_commande"]])

    elif "stock" in q:
        st.success(f"Stock total = {plan['stock_actuel'].sum():,.0f} kg")

    elif "commande" in q:
        st.success(f"Commande totale = {plan['qte_commande'].sum():,.0f} kg")

    else:
        st.info("Essaye: urgent / stock / commande")

# ==================================================
# REFRESH
# ==================================================
if st.button("🔄 Actualiser"):
    st.cache_data.clear()
    st.rerun()
