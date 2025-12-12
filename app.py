import os
from werkzeug.utils import secure_filename
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
import uuid
from datetime import datetime, timedelta
app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = "ma_cle_ultra_secrete"

UPLOAD_FOLDER = "static/vlogs"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DEFAULT_DB = "postgresql+psycopg2://neondb_owner:npg_5kDyFqm3iAwr@ep-dawn-wind-abvkgdcp-pooler.eu-west-2.aws.neon.tech/neondb?sslmode=require"
app.config["SQLALCHEMY_DATABASE_URI"] = DEFAULT_DB
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,      # Vérifie si la connexion est encore vivante
    "pool_recycle": 280,        # Recycle la connexion avant expiration
    "pool_timeout": 20          # Timeout raisonnable
}

db = SQLAlchemy(app)

from sqlalchemy import text
from flask_migrate import Migrate

migrate = Migrate(app, db)
@app.cli.command("add-ref-col")
def add_reference_column():
    """
    Ajoute la colonne `reference` à la table depot si elle n'existe pas.
    Usage: flask --app app.py add-ref-col
    """
    with db.engine.connect() as conn:
        conn.execute(text("""
            ALTER TABLE depot
            ADD COLUMN IF NOT EXISTS reference VARCHAR(200);
        """))
        conn.commit()
    print("✅ Colonne 'reference' ajoutée si elle n'existait pas.")
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(50), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

    phone = db.Column(db.String(30), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

    parrain = db.Column(db.String(30), nullable=True)   # 🔥 colonne correcte
    commission_total = db.Column(db.Float, default=0.0)

    wallet_country = db.Column(db.String(50))
    wallet_operator = db.Column(db.String(50))
    wallet_number = db.Column(db.String(30))

    solde_total = db.Column(db.Float, default=0.0)
    solde_depot = db.Column(db.Float, default=0.0)
    solde_parrainage = db.Column(db.Float, default=0.0)
    solde_revenu = db.Column(db.Float, default=0.0)
    premier_depot = db.Column(db.Boolean, default=False)

    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

class Depot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(30))
    montant = db.Column(db.Float)
    reference = db.Column(db.String(200), nullable=True)
    statut = db.Column(db.String(20), default="en_attente")  #  NEW
    date = db.Column(db.DateTime, default=datetime.utcnow)


class Investissement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(30))
    montant = db.Column(db.Float)
    revenu_journalier = db.Column(db.Float)
    duree = db.Column(db.Integer)
    date_debut = db.Column(db.DateTime, default=datetime.utcnow)
    dernier_paiement = db.Column(db.DateTime, default=datetime.utcnow)   # 🔥 OBLIGATOIRE
    actif = db.Column(db.Boolean, default=True)

class Retrait(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(30))
    montant = db.Column(db.Float)
    statut = db.Column(db.String(20), default="en_attente")
    date = db.Column(db.DateTime, default=datetime.utcnow)

class Staking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(30), nullable=False)
    vip_level = db.Column(db.String(20), nullable=False)
    montant = db.Column(db.Float, nullable=False)
    duree = db.Column(db.Integer, default=15)
    taux_min = db.Column(db.Float, default=1.80)
    taux_max = db.Column(db.Float, default=2.20)
    revenu_total = db.Column(db.Float, nullable=False)
    date_debut = db.Column(db.DateTime, default=datetime.utcnow)
    actif = db.Column(db.Boolean, default=True)

class Commission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    parrain_phone = db.Column(db.String(30))    # celui qui gagne
    filleul_phone = db.Column(db.String(30))    # celui qui a fait l'action
    montant = db.Column(db.Float)
    niveau = db.Column(db.Integer)              # 1, 2 ou 3
    date = db.Column(db.DateTime, default=datetime.utcnow)

class Vlog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(30))
    montant = db.Column(db.Float)
    image = db.Column(db.String(200))
    statut = db.Column(db.String(20), default="en_attente") # en_attente / valide / rejete
    date = db.Column(db.DateTime, default=datetime.utcnow)

def donner_commission(filleul_phone, montant):
    # Niveaux : 30% – 5% – 3%
    COMMISSIONS = {1: 0.20, 2: 0.03, 3: 0.01}

    current_phone = filleul_phone

    for niveau in range(1, 4):
        user = User.query.filter_by(phone=current_phone).first()

        # si pas de parrain → stop
        if not user or not user.parrain:
            break

        parrain = User.query.filter_by(phone=user.parrain).first()
        if not parrain:
            break

        gain = montant * COMMISSIONS[niveau]

        commission = Commission(
            parrain_phone=parrain.phone,
            filleul_phone=filleul_phone,
            montant=gain,
            niveau=niveau
        )
        db.session.add(commission)

        parrain.solde_parrainage += gain
        parrain.commission_total += gain

        db.session.commit()

        current_phone = parrain.phone

def t(key):
    lang = session.get("lang", "fr")
    return TRANSLATIONS.get(lang, TRANSLATIONS["fr"]).get(key, key)

app.jinja_env.globals.update(t=t)

def get_logged_in_user_phone():
    phone = session.get("phone")
    if not phone:
        return None
    return str(phone).strip()

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not get_logged_in_user_phone():
            return redirect(url_for("connexion_page"))
        return f(*args, **kwargs)
    return wrapper


def verifier_investissements(phone):
    """Vérifie si les investissements d'un user sont terminés et crédite les gains."""
    investissements = Investissement.query.filter_by(phone=phone, actif=True).all()

    for inv in investissements:
        date_fin = inv.date_debut + timedelta(days=inv.duree)

        if datetime.utcnow() >= date_fin:
            revenu_total = inv.revenu_journalier * inv.duree

            user = User.query.filter_by(phone=phone).first()
            user.solde_revenu += revenu_total

            user.solde_total += inv.montant

            inv.actif = False

            db.session.commit()

TRANSLATIONS = {
    "fr": {
        "dashboard": "Tableau de bord",
        "deposit": "Dépôt",
        "withdraw": "Retrait",
        "support": "Support",
        "language": "Langue",
        "welcome": "Bienvenue",
        "balance": "Solde total",
        "submit": "Soumettre",
        "confirm": "Confirmer",
        "investment": "Investissements",
        "staking": "Jalonnement",
        "finance": "Finance",
        "logout": "Déconnexion",
    },

    "en": {
        "dashboard": "Dashboard",
        "deposit": "Deposit",
        "withdraw": "Withdraw",
        "support": "Support",
        "language": "Language",
        "welcome": "Welcome",
        "balance": "Total balance",
        "submit": "Submit",
        "confirm": "Confirm",
        "investment": "Investments",
        "staking": "Staking",
        "finance": "Finance",
        "logout": "Logout",
    },

    "es": {
        "dashboard": "Panel",
        "deposit": "Depósito",
        "withdraw": "Retiro",
        "support": "Soporte",
        "language": "Idioma",
        "welcome": "Bienvenido",
        "balance": "Saldo total",
        "submit": "Enviar",
        "confirm": "Confirmar",
        "investment": "Inversiones",
        "staking": "Staking",
        "finance": "Finanzas",
        "logout": "Cerrar sesión",
    },

    "cn": {
        "dashboard": "仪表板",
        "deposit": "充值",
        "withdraw": "提现",
        "support": "客服",
        "language": "语言",
        "welcome": "欢迎",
        "balance": "总余额",
        "submit": "提交",
        "confirm": "确认",
        "investment": "投资产品",
        "staking": "质押",
        "finance": "财务",
        "logout": "退出登录",
    }
}

@app.route("/langue")
@login_required
def langue_page():
    return render_template("langue.html")


@app.route("/set_lang/<lang>")
@login_required
def set_language(lang):
    if lang not in TRANSLATIONS:
        flash("Langue invalide.", "danger")
        return redirect(url_for("langue_page"))

    session["lang"] = lang
    flash("Langue mise à jour.", "success")
    return redirect(url_for("dashboard_page"))

@app.cli.command("init-db")
def init_db():
    db.create_all()
    print("✅ Base de données initialisée avec succès !")

@app.route("/inscription", methods=["GET", "POST"])
def inscription_page():

    # 🔥 Récupère le code ref dans l'URL si présent
    code_ref = request.args.get("ref", "").strip()

    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "").strip()
        confirm = request.form.get("confirm_password", "").strip()
        code_invitation = request.form.get("code_invitation", "").strip()

        if not phone or not password:
            flash("⚠️ Tous les champs obligatoires doivent être remplis.", "danger")
            return redirect(url_for("inscription_page"))

        if password != confirm:
            flash("❌ Les mots de passe ne correspondent pas.", "danger")
            return redirect(url_for("inscription_page"))

        if User.query.filter_by(phone=phone).first():
            flash("⚠️ Ce numéro est déjà enregistré.", "danger")
            return redirect(url_for("inscription_page"))

        parrain_user = None
        if code_invitation:
            parrain_user = User.query.filter_by(phone=code_invitation).first()
            if not parrain_user:
                flash("⚠️ Code d'invitation invalide.", "warning")

        new_user = User(
            phone=phone,
            password=password,
            solde_total=0,
            solde_depot=0,
            solde_revenu=0,
            solde_parrainage=0,
            parrain=parrain_user.phone if parrain_user else None
        )

        db.session.add(new_user)
        db.session.commit()

        flash("🎉 Inscription réussie ! Connectez-vous maintenant.", "success")
        return redirect(url_for("connexion_page"))

    # 🔥 Passe le code au HTML
    return render_template("inscription.html", code_ref=code_ref)

@app.route("/connexion", methods=["GET", "POST"])
def connexion_page():
    if request.method == "POST":

        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "").strip()

        if not phone or not password:
            flash("⚠️ Veuillez remplir tous les champs.", "danger")
            return redirect(url_for("connexion_page"))

        user = User.query.filter_by(phone=phone).first()

        if not user:
            flash("❌ Numéro introuvable.", "danger")
            return redirect(url_for("connexion_page"))

        if user.password != password:
            flash("❌ Mot de passe incorrect.", "danger")
            return redirect(url_for("connexion_page"))

        session["phone"] = user.phone

        flash("Connexion réussie ✅", "success")
        return redirect(url_for("dashboard_page"))

    return render_template("connexion.html")

@app.route("/logout")
def logout_page():
    session.clear()
    flash("Déconnexion effectuée.", "info")
    return redirect(url_for("connexion_page"))



def get_global_stats():
    total_users = db.session.query(func.count(User.id)).scalar() or 0
    total_deposits = db.session.query(func.sum(Depot.montant)).scalar() or 0
    total_invested = db.session.query(func.sum(Investissement.montant)).scalar() or 0
    total_withdrawn = db.session.query(func.sum(Retrait.montant)).scalar() or 0

    return total_users, total_deposits, total_invested, total_withdrawn

@app.route("/dashboard")
@login_required
def dashboard_page():
    phone = get_logged_in_user_phone()
    user = User.query.filter_by(phone=phone).first()

    if not user:
        session.clear()
        flash("Session invalide, veuillez vous reconnecter.", "danger")
        return redirect(url_for("connexion_page"))

    total_users, total_deposits, total_invested, total_withdrawn = get_global_stats()

    # 🔥 Revenu cumulé = commissions + revenus investissements
    revenu_cumule = (user.solde_parrainage or 0) + (user.solde_revenu or 0)

    return render_template(
        "dashboard.html",
        user=user,
        revenu_cumule=revenu_cumule,  # 🔥 envoi au HTML
        total_users=total_users,
        total_invested=total_invested,
    )

@app.route("/investissements")
@login_required
def investissements_page():
    PRODUITS = [
        {
            "id": 1,
            "nom": "VIP 1",
            "prix": 3000,
            "revenu_journalier": 500,
            "revenu_total": 22500,
            "duree": 45,
            "image": "cyber1.jpg"
        },
        {
            "id": 2,
            "nom": "VIP 2",
            "prix": 8000,
            "revenu_journalier": 1350,
            "revenu_total": 60750,
            "duree": 45,
            "image": "cyber2.jpg"
        },
        {
            "id": 3,
            "nom": "VIP 3",
            "prix": 20000,
            "revenu_journalier": 3650,
            "revenu_total": 164250,
            "duree": 45,
            "image": "cyber3.jpg"
        },
        {
            "id": 4,
            "nom": "VIP 4",
            "prix": 40000,
            "revenu_journalier": 8000,
            "revenu_total": 360000,
            "duree": 45,
            "image": "cyber4.jpg"
        },
        {
            "id": 5,
            "nom": "VIP 5",
            "prix": 90000,
            "revenu_journalier": 20000,
            "revenu_total": 900000,
            "duree": 45,
            "image": "cyber5.jpg"
        },
        {
            "id": 6,
            "nom": "VIP 6",
            "prix": 180000,
            "revenu_journalier": 42000,
            "revenu_total": 1890000,
            "duree": 45,
            "image": "cyber6.jpg"
        },
        {
            "id": 7,
            "nom": "VIP 7",
            "prix": 400000,
            "revenu_journalier": 100000,
            "revenu_total": 4500000,
            "duree": 45,
            "image": "cyber7.jpg"
        },
        {
            "id": 8,
            "nom": "VIP 8",
            "prix": 800000,
            "revenu_journalier": 220000,
            "revenu_total": 9900000,
            "duree": 45,
            "image": "cyber8.jpg"
        },
    ]

    return render_template("investissements.html", produits=PRODUITS)

@app.route("/investir/<int:product_id>", methods=["GET", "POST"])
@login_required
def confirmation_investissement(product_id):

    PRODUITS = [
        {"id": 1, "nom": "VIP 1", "prix": 3000, "revenu_journalier": 500, "revenu_total": 22500, "duree": 45, "image": "cyber1.jpg"},
        {"id": 2, "nom": "VIP 2", "prix": 8000, "revenu_journalier": 1350, "revenu_total": 60750, "duree": 45, "image": "cyber2.jpg"},
        {"id": 3, "nom": "VIP 3", "prix": 20000, "revenu_journalier": 3650, "revenu_total": 164250, "duree": 45, "image": "cyber3.jpg"},
        {"id": 4, "nom": "VIP 4", "prix": 40000, "revenu_journalier": 8000, "revenu_total": 360000, "duree": 45, "image": "cyber4.jpg"},
        {"id": 5, "nom": "VIP 5", "prix": 90000, "revenu_journalier": 20000, "revenu_total": 900000, "duree": 45, "image": "cyber5.jpg"},
        {"id": 6, "nom": "VIP 6", "prix": 180000, "revenu_journalier": 42000, "revenu_total": 1890000, "duree": 45, "image": "cyber6.jpg"},
        {"id": 7, "nom": "VIP 7", "prix": 400000, "revenu_journalier": 100000, "revenu_total": 4500000, "duree": 45, "image": "cyber7.jpg"},
        {"id": 8, "nom": "VIP 8", "prix": 800000, "revenu_journalier": 220000, "revenu_total": 9900000, "duree": 45, "image": "cyber8.jpg"},
    ]

    produit = next((p for p in PRODUITS if p["id"] == product_id), None)

    if not produit:
        flash("Produit introuvable.", "danger")
        return redirect(url_for("investissements_page"))

    if request.method == "POST":
        phone = get_logged_in_user_phone()
        user = User.query.filter_by(phone=phone).first()

        if user.solde_total < produit["prix"]:
            flash("Solde insuffisant.", "danger")
            return redirect(url_for("investissements_page"))

        user.solde_total -= produit["prix"]

        nouvel_invest = Investissement(
            phone=phone,
            montant=produit["prix"],
            revenu_journalier=produit["revenu_journalier"],
            duree=produit["duree"],
            actif=True
        )
        db.session.add(nouvel_invest)
        db.session.commit()

        flash("🎉 Investissement lancé avec succès !", "success")
        return redirect(url_for("finance_page"))

    return render_template("confirmation.html", p=produit)

PRODUITS_VIP = [
    {"id": 1, "nom": "VIP 1", "prix": 3000, "revenu_journalier": 500, "image": "cyber1.jpg"},
    {"id": 2, "nom": "VIP 2", "prix": 8000, "revenu_journalier": 1350, "image": "cyber2.jpg"},
    {"id": 3, "nom": "VIP 3", "prix": 20000, "revenu_journalier": 3650, "image": "cyber3.jpg"},
    {"id": 4, "nom": "VIP 4", "prix": 40000, "revenu_journalier": 8000, "image": "cyber4.jpg"},
    {"id": 5, "nom": "VIP 5", "prix": 90000, "revenu_journalier": 20000, "image": "cyber5.jpg"},
    {"id": 6, "nom": "VIP 6", "prix": 180000, "revenu_journalier": 42000, "image": "cyber6.jpg"},
    {"id": 7, "nom": "VIP 7", "prix": 400000, "revenu_journalier": 100000, "image": "cyber7.jpg"},
    {"id": 8, "nom": "VIP 8", "prix": 800000, "revenu_journalier": 220000, "image": "cyber8.jpg"}
]

# ============================
# PAGE PRODUITS RAPIDES
# ============================
@app.route("/produits_rapide")
@login_required
def produits_rapide_page():
    phone = get_logged_in_user_phone()
    user = User.query.filter_by(phone=phone).first()

    return render_template(
        "produits_rapide.html",
        user=user,
        produits=PRODUITS_VIP
    )


# ============================
# CONFIRMATION D’ACHAT (affichage + validation finale)
# ============================
@app.route("/produits_rapide/confirmer/<int:vip_id>", methods=["GET", "POST"])
@login_required
def confirmer_produit_rapide(vip_id):
    phone = get_logged_in_user_phone()
    user = User.query.filter_by(phone=phone).first()

    # retrouver le produit
    produit = next((p for p in PRODUITS_VIP if p["id"] == vip_id), None)
    if not produit:
        flash("Produit introuvable.", "danger")
        return redirect(url_for("produits_rapide_page"))

    montant = produit["prix"]
    revenu_journalier = produit["revenu_journalier"]
    revenu_total = revenu_journalier * 14  # durée fixe 14 jours

    # GET → afficher la page de confirmation
    if request.method == "GET":
        return render_template(
            "confirm_rapide.html",
            p=produit,
            revenu_total=revenu_total,
            user=user
        )

    # POST → vérifier solde
    if float(user.solde_total or 0) < montant:
        flash("Solde insuffisant.", "danger")
        return redirect(url_for("produits_rapide_page"))

    # Débiter le solde
    user.solde_total -= montant

    # Créer l’investissement
    inv = Investissement(
        phone=phone,
        montant=montant,
        revenu_journalier=revenu_journalier,
        duree=14,
        actif=True
    )
    db.session.add(inv)
    db.session.commit()

    # afficher animation de succès
    return render_template(
        "confirm_rapide_loading.html",
        montant=montant,
        produit=produit
    )


# ============================
# VALIDATION DIRECTE (ancienne route)
# → On la garde pour compatibilité mais elle n’est plus affichée dans HTML
# ============================
@app.route("/produits_rapide/valider/<int:vip_id>", methods=["POST"])
@login_required
def valider_produit_rapide(vip_id):
    phone = get_logged_in_user_phone()
    user = User.query.filter_by(phone=phone).first()

    produit = next((p for p in PRODUITS_VIP if p["id"] == vip_id), None)
    if not produit:
        flash("Produit introuvable.", "danger")
        return redirect(url_for("produits_rapide_page"))

    montant = produit["prix"]

    if user.solde_total < montant:
        flash("Solde insuffisant.", "danger")
        return redirect(url_for("produits_rapide_page"))

    inv = Investissement(
        phone=phone,
        montant=montant,
        revenu_journalier=produit["revenu_journalier"],
        duree=14,
        actif=True
    )
    db.session.add(inv)

    user.solde_total -= montant
    db.session.commit()

    return render_template("achat_rapide_loader.html", produit=produit)

@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit_page():
    phone = get_logged_in_user_phone()
    user = User.query.filter_by(phone=phone).first()

    if request.method == "POST":
        montant = float(request.form["montant"])
        reference = request.form["reference"]

        depot = Depot(
            phone=phone,
            montant=montant,
            reference=reference
        )
        db.session.add(depot)
        db.session.commit()

        flash("Dépôt soumis avec succès !", "success")
        return redirect(url_for("dashboard_page"))

    return render_template("deposit.html", user=user)

@app.route("/submit_reference", methods=["POST"])
@login_required
def submit_reference():
    phone = get_logged_in_user_phone()
    montant = float(request.form["montant"])
    reference = request.form["reference"]

    depot = Depot(
        phone=phone,
        montant=montant,
        reference=reference
    )
    db.session.add(depot)
    db.session.commit()

    # 👉 au lieu de redirect, on affiche une page avec loader + succès
    return render_template(
        "submit_reference_loading.html",
        montant=montant,
        reference=reference
    )

@app.route("/ajouter_portefeuille", methods=["GET", "POST"])
@login_required
def wallet_setup_page():
    phone = get_logged_in_user_phone()
    user = User.query.filter_by(phone=phone).first()

    if not user:
        flash("Session expirée, reconnectez-vous.", "danger")
        return redirect(url_for("connexion_page"))

    if user.wallet_number:
        return redirect(url_for("retrait_page"))

    if request.method == "POST":
        country = request.form["country"]
        operator = request.form["operator"]
        number = request.form["number"]

        user.wallet_country = country
        user.wallet_operator = operator
        user.wallet_number = number
        db.session.commit()

        flash("Compte de retrait enregistré avec succès.", "success")
        return redirect(url_for("retrait_page"))

    return render_template("wallet_setup.html")


# 🎄 Offres Noël
OFFRES_NOEL = [
    {"id": 1, "nom": "VIP 1", "prix": 3000,
     "revenu_journalier": int((3000 * 0.75) / 7), "duree": 7,
     "revenu_total": int(3000 * 1.75), "image": "cyber1.jpg"},

    {"id": 2, "nom": "VIP 2", "prix": 8000,
     "revenu_journalier": int((8000 * 0.75) / 7), "duree": 7,
     "revenu_total": int(8000 * 1.75), "image": "cyber2.jpg"},

    {"id": 3, "nom": "VIP 3", "prix": 20000,
     "revenu_journalier": int((20000 * 0.75) / 7), "duree": 7,
     "revenu_total": int(20000 * 1.75), "image": "cyber3.jpg"},

    {"id": 4, "nom": "VIP 4", "prix": 40000,
     "revenu_journalier": int((40000 * 0.75) / 7), "duree": 7,
     "revenu_total": int(40000 * 1.75), "image": "cyber4.jpg"},

    {"id": 5, "nom": "VIP 5", "prix": 90000,
     "revenu_journalier": int((90000 * 0.75) / 7), "duree": 7,
     "revenu_total": int(90000 * 1.75), "image": "cyber5.jpg"},

    {"id": 6, "nom": "VIP 6", "prix": 180000,
     "revenu_journalier": int((180000 * 0.75) / 7), "duree": 7,
     "revenu_total": int(180000 * 1.75), "image": "cyber6.jpg"},

    {"id": 7, "nom": "VIP 7", "prix": 400000,
     "revenu_journalier": int((400000 * 0.75) / 7), "duree": 7,
     "revenu_total": int(400000 * 1.75), "image": "cyber7.jpg"},

    {"id": 8, "nom": "VIP 8", "prix": 800000,
     "revenu_journalier": int((800000 * 0.75) / 7), "duree": 7,
     "revenu_total": int(800000 * 1.75), "image": "cyber8.jpg"}
]

@app.route("/offres_noel")
@login_required
def offres_noel_page():
    phone = get_logged_in_user_phone()
    user = User.query.filter_by(phone=phone).first()

    max_invest = db.session.query(db.func.max(Investissement.montant)) \
        .filter_by(phone=phone, actif=True).scalar() or 0

    return render_template(
        "offres_noel.html",
        user=user,
        produits=OFFRES_NOEL,
        max_invest=max_invest
    )


@app.route("/offres_noel/valider/<int:prod_id>", methods=["POST"])
@login_required
def valider_offre_noel(prod_id):
    phone = get_logged_in_user_phone()
    user = User.query.filter_by(phone=phone).first()

    produit = next((p for p in OFFRES_NOEL if p["id"] == prod_id), None)
    if not produit:
        flash("Offre introuvable.", "danger")
        return redirect(url_for("offres_noel_page"))

    montant = produit["prix"]

    if user.solde_total < montant:
        flash("Solde insuffisant.", "danger")
        return redirect(url_for("offres_noel_page"))

    # Enregistrer en attente de confirmation
    return redirect(url_for("confirmer_offre_noel", prod_id=prod_id))


@app.route("/offres_noel/confirmer/<int:prod_id>", methods=["GET", "POST"])
@login_required
def confirmer_offre_noel(prod_id):
    phone = get_logged_in_user_phone()
    user = User.query.filter_by(phone=phone).first()

    # Recherche du produit
    produit = next((p for p in OFFRES_NOEL if p["id"] == prod_id), None)
    if not produit:
        flash("Offre introuvable.", "danger")
        return redirect(url_for("offres_noel_page"))

    montant = produit["prix"]
    revenu_journalier = produit["revenu_journalier"]
    revenu_total = produit["revenu_total"]
    # --- Affichage du template (GET)
    if request.method == "GET":
        return render_template(
            "confirm_noel.html",
            p=produit,  # clé `p` pour correspondre au template
            revenu_total=revenu_total,
            user=user
        )

    # --- Validation de l’achat (POST)
    if float(user.solde_total or 0) < montant:
        flash("Solde insuffisant.", "danger")
        return redirect(url_for("offres_noel_page"))

    # Débiter le solde
    user.solde_total -= montant

    # Créer un investissement
    inv = Investissement(
        phone=phone,
        montant=montant,
        revenu_journalier=revenu_journalier,
        duree=7,
        actif=True
    )
    db.session.add(inv)
    db.session.commit()

    # Page de chargement / confirmation
    return render_template(
        "achat_rapide_loader.html",
        produit=produit,
        montant=montant
    )

@app.route("/retrait", methods=["GET", "POST"])
@login_required
def retrait_page():
    phone = get_logged_in_user_phone()
    user = User.query.filter_by(phone=phone).first()

    if not user:
        flash("Session invalide.", "danger")
        return redirect(url_for("connexion_page"))

    # Le user doit avoir configuré son portefeuille
    if not user.wallet_number:
        return redirect(url_for("wallet_setup_page"))

    # ✅ Solde retirable = Parrainage + Revenus
    solde_retraitable = (user.solde_parrainage or 0) + (user.solde_revenu or 0)

    if request.method == "POST":
        try:
            montant = float(request.form["montant"])
        except:
            flash("Montant invalide.", "danger")
            return redirect(url_for("retrait_page"))

        if montant < 1000:
            flash("Montant minimum : 1000 XOF.", "warning")
            return redirect(url_for("retrait_page"))

        if montant > solde_retraitable:
            flash("Solde insuffisant.", "danger")
            return redirect(url_for("retrait_page"))

        return redirect(url_for("retrait_confirmation_page", montant=montant))

    return render_template(
        "retrait.html",
        user=user,
        solde_total=user.solde_total,
        solde_retraitable=solde_retraitable
    )

@app.route("/retrait/confirmation/<int:montant>", methods=["GET", "POST"])
@login_required
def retrait_confirmation_page(montant):
    phone = get_logged_in_user_phone()
    user = User.query.filter_by(phone=phone).first()

    if not user:
        flash("Session expirée.", "danger")
        return redirect(url_for("connexion_page"))

    # Vérification des fonds
    solde_retraitable = (user.solde_parrainage or 0) + (user.solde_revenu or 0)
    if montant > solde_retraitable:
        flash("Solde insuffisant.", "danger")
        return redirect(url_for("retrait_page"))

    # Calcul taxe et montant net
    taxe = int(montant * 0.15)
    net = montant - taxe

    # Si l'utilisateur clique sur "Confirmer"
    if request.method == "POST":

        retrait = Retrait(
            phone=phone,
            montant=montant,
            statut="en_attente"
        )
        db.session.add(retrait)

        # Déduction du solde
        reste = montant

        if user.solde_parrainage >= reste:
            user.solde_parrainage -= reste
            reste = 0
        else:
            reste -= user.solde_parrainage
            user.solde_parrainage = 0

        if reste > 0:
            user.solde_revenu -= reste


        db.session.commit()

        # 👉 On renvoie une page spéciale avec chargement + succès + redirection
        return render_template(
            "retrait_confirmation_loading.html",
            montant=montant,
            taxe=taxe,
            net=net,
            user=user
        )

    # GET → afficher la page de confirmation normale
    return render_template(
        "retrait_confirmation.html",
        montant=montant,
        taxe=taxe,
        net=net,
        user=user
    )

@app.route("/jalonnement", methods=["GET", "POST"])
@login_required
def jalonnement_page():
    user_phone = get_logged_in_user_phone()
    user = User.query.filter_by(phone=user_phone).first()

    PRODUITS_JALON = {
        "VIP2": {"min": 8000},
        "VIP3": {"min": 20000},
        "VIP4": {"min": 40000},
        "VIP5": {"min": 90000},
    }

    if request.method == "POST":
        vip = request.form.get("vip")
        montant = request.form.get("montant")

        if not vip or not montant:
            flash("Veuillez remplir tous les champs.", "warning")
            return redirect(url_for("jalonnement_page"))

        montant = float(montant)

        min_requis = PRODUITS_JALON[vip]["min"]

        if montant < min_requis:
            flash(f"Montant minimum pour {vip} : {min_requis} FCFA", "danger")
            return redirect(url_for("jalonnement_page"))

        if user.solde_depot < montant:
            flash("Solde insuffisant pour jalonner.", "danger")
            return redirect(url_for("jalonnement_page"))

        taux_moyen = (1.80 + 2.20) / 2 / 100  # converti en pourcentage
        revenu_total = montant * taux_moyen * 15  # 15 jours

        staking = Staking(
            phone=user_phone,
            vip_level=vip,
            montant=montant,
            duree=15,
            revenu_total=revenu_total,
        )

        db.session.add(staking)

        user.solde_depot -= montant

        db.session.commit()

        flash("Jalonnement effectué avec succès.", "success")
        return redirect(url_for("jalonnement_page"))

    return render_template("jalonnement.html")


@app.route("/finance")
@login_required
def finance_page():
    phone = get_logged_in_user_phone()
    user = User.query.filter_by(phone=phone).first()

    if not user:
        flash("Session expirée.", "danger")
        return redirect(url_for("connexion_page"))

    revenus_totaux = (user.solde_revenu or 0) + (user.solde_parrainage or 0)
    fortune_totale = (user.solde_depot or 0) + revenus_totaux

    retraits = Retrait.query.filter_by(phone=phone).order_by(Retrait.date.desc()).limit(10).all()

    actifs_raw = Investissement.query.filter_by(phone=phone, actif=True).all()

    actifs = []
    for a in actifs_raw:
        date_fin = a.date_debut + timedelta(days=a.duree)
        actifs.append({
            "montant": a.montant,
            "revenu_journalier": a.revenu_journalier,
            "duree": a.duree,
            "date_debut": a.date_debut,
            "date_fin": date_fin
        })

    return render_template(
        "finance.html",
        user=user,
        revenus_totaux=revenus_totaux,
        fortune_totale=fortune_totale,
        retraits=retraits,
        actifs=actifs
    )

@app.route("/annonce")
@login_required
def annonce_page():
    ANNONCES = [
        {
            "titre": "🔔 Mise à jour des produits VIP",
            "date": "7 Dec 2025",
            "contenu": "Les VIP 5 à 8 ont été améliorés. Rendements optimisés et stabilité renforcée."
        },
        {
            "titre": "💰 Bonus de premier dépôt",
            "date": "07 Dec 2025",
            "contenu": "Obtenez 5% de bonus sur votre premier dépôt du mois. Offre limitée !"
        }
    ]

    return render_template("annonce.html", annonces=ANNONCES)

@app.route("/profile")
@login_required
def profile_page():
    phone = get_logged_in_user_phone()
    user = User.query.filter_by(phone=phone).first()

    return render_template("profile.html", user=user)

def get_image(montant):
    mapping = {
        3000: "cyber1.jpg",
        8000: "cyber2.jpg",
        20000: "cyber3.jpg",
        40000: "cyber4.jpg",
        90000: "cyber5.jpg",
        180000: "cyber6.jpg",
        400000: "cyber7.jpg",
        800000: "cyber8.jpg",
    }
    return mapping.get(int(montant), "cyber1.jpg")

@app.route("/historique")
@login_required
def historique_invest_page():
    phone = get_logged_in_user_phone()

    investissements = []

    now = datetime.now()   # 👍 PAS DE WARNING

    for inv in Investissement.query.filter_by(phone=phone).all():

        jours_passes = (now - inv.date_debut).days
        progression = int((jours_passes / inv.duree) * 100)
        progression = min(progression, 100)
        jours_restants = max(inv.duree - jours_passes, 0)

        investissements.append({
            "nom": f"prix {inv.montant}",
            "revenu_journalier": inv.revenu_journalier,
            "jours_restants": jours_restants,
            "progression": progression,
            "image": get_image(inv.montant)
        })

    return render_template("historique_invest.html",
                           investissements=investissements)

@app.route('/team')
@login_required
def team_page():
    phone = get_logged_in_user_phone()
    user = User.query.filter_by(phone=phone).first()

    referral_code = phone
    referral_link = url_for('inscription_page', _external=True) + f'?ref={referral_code}'

    from sqlalchemy import func

    # ----- NIVEAU 1 -----
    level1_users = User.query.filter_by(parrain=referral_code).all()
    level1_phones = [u.phone for u in level1_users]
    level1_count = len(level1_users)

    # ----- NIVEAU 2 -----
    if level1_phones:
        level2_users = User.query.filter(User.parrain.in_(level1_phones)).all()
        level2_phones = [u.phone for u in level2_users]
        level2_count = len(level2_users)
    else:
        level2_users = []
        level2_phones = []
        level2_count = 0

    # ----- NIVEAU 3 -----
    if level2_phones:
        level3_users = User.query.filter(User.parrain.in_(level2_phones)).all()
        level3_phones = [u.phone for u in level3_users]
        level3_count = len(level3_users)
    else:
        level3_users = []
        level3_phones = []
        level3_count = 0

    # ----- COMMISSIONS -----
    commissions_total = float(user.solde_parrainage or 0)

    # ----- DÉPÔTS DE LA TEAM (NIVEAU 1 + 2 + 3) -----
    all_team_phones = level1_phones + level2_phones + level3_phones

    if all_team_phones:
        team_deposits = float(
            db.session.query(func.coalesce(func.sum(Depot.montant), 0))
            .filter(Depot.phone.in_(all_team_phones))
            .scalar()
        )
    else:
        team_deposits = 0.0

    # ----- STATISTIQUES -----
    stats = {
        "level1": level1_count,
        "level2": level2_count,
        "level3": level3_count,
        "commissions_total": commissions_total,
        "team_deposits": team_deposits
    }

    return render_template(
        "team.html",
        referral_code=referral_code,
        referral_link=referral_link,
        stats=stats
    )

@app.route("/admin/deposits")
def admin_deposits():
    depots = Depot.query.order_by(Depot.date.desc()).all()
    return render_template("admin_deposits.html", depots=depots)


@app.route("/admin/deposits/valider/<int:depot_id>")
def valider_depot(depot_id):
    depot = Depot.query.get_or_404(depot_id)
    user = User.query.filter_by(phone=depot.phone).first()

    if not user:
        flash("Utilisateur introuvable.", "danger")
        return redirect("/admin/deposits")

    if hasattr(depot, "statut") and depot.statut == "valide":
        flash("Ce dépôt est déjà validé.", "warning")
        return redirect("/admin/deposits")

    # 🔥 VÉRIFIER SI C'EST SON PREMIER DÉPÔT VALIDÉ
    premier_depot = Depot.query.filter_by(phone=user.phone, statut="valide").first()

    # 🔥 Créditer le dépôt
    user.solde_depot += depot.montant
    user.solde_total += depot.montant
    depot.statut = "valide"

    # 🔥 SI C’EST SON PREMIER DÉPÔT → COMMISSIONS
    if not premier_depot and user.parrain:
        donner_commission(user.phone, depot.montant)

    db.session.commit()

    flash("Dépôt validé et crédité avec succès !", "success")
    return redirect("/admin/deposits")

@app.route("/admin/deposits/rejeter/<int:depot_id>")
def rejeter_depot(depot_id):
    depot = Depot.query.get_or_404(depot_id)

    # Si déjà traité
    if hasattr(depot, "statut") and depot.statut in ["valide", "rejete"]:
        flash("Ce dépôt a déjà été traité.", "warning")
        return redirect("/admin/deposits")

    depot.statut = "rejete"
    db.session.commit()

    flash("Dépôt rejeté avec succès.", "danger")
    return redirect("/admin/deposits")

@app.route("/admin/retraits")
def admin_retraits():
    retraits = Retrait.query.order_by(Retrait.date.desc()).all()
    return render_template("admin_retraits.html", retraits=retraits)

@app.route("/admin/retraits/valider/<int:retrait_id>")
def valider_retrait(retrait_id):
    retrait = Retrait.query.get_or_404(retrait_id)

    if retrait.statut == "validé":
        flash("Ce retrait est déjà validé.", "info")
        return redirect("/admin/retraits")

    retrait.statut = "validé"
    db.session.commit()

    flash("Retrait validé avec succès !", "success")
    return redirect("/admin/retraits")

@app.route("/admin/retraits/refuser/<int:retrait_id>")
def refuser_retrait(retrait_id):
    retrait = Retrait.query.get_or_404(retrait_id)
    user = User.query.filter_by(phone=retrait.phone).first()

    if retrait.statut == "refusé":
        flash("Ce retrait est déjà refusé.", "info")
        return redirect("/admin/retraits")

    # Remboursement automatique
    montant = retrait.montant

    # On rembourse d'abord le solde_parrainage jusqu'à ce qu'il atteigne 0
    # Puis le reste va dans solde_revenu
    # Si tu veux séparer les sources (revenu/parrainage) on peut le faire différemment.
    # Mais ici tu veux simplement recréditer le montant refusé.

    user.solde_revenu += montant
    retrait.statut = "refusé"
    db.session.commit()

    flash("Retrait refusé et montant recrédité à l’utilisateur.", "warning")
    return redirect("/admin/retraits")

@app.route("/admin/vlog")
def admin_vlog():
    vlogs = Vlog.query.order_by(Vlog.date.desc()).all()
    return render_template("admin_vlog.html", vlogs=vlogs)

@app.route("/admin/vlog/valider/<int:id>")
def admin_vlog_valider(id):
    vlog = Vlog.query.get_or_404(id)
    user = User.query.filter_by(phone=vlog.phone).first()

    if not user:
        flash("Utilisateur introuvable", "danger")
        return redirect("/admin/vlog")

    if vlog.statut == "valide":
        flash("Déjà validé", "warning")
        return redirect("/admin/vlog")

    bonus = vlog.montant * 0.10

    user.solde_revenu += bonus

    vlog.statut = "valide"
    db.session.commit()

    flash(f"Bonus {bonus} XOF crédité !", "success")
    return redirect("/admin/vlog")

@app.route("/admin/vlog/rejeter/<int:vlog_id>")
def rejeter_vlog(vlog_id):
    vlog = Vlog.query.get_or_404(vlog_id)
    user = User.query.filter_by(phone=vlog.phone).first()

    vlog.statut = "rejete"
    db.session.commit()

    flash("Preuve rejetée avec succès !", "warning")
    return redirect("/admin/vlog")



@app.route("/vlog", methods=["GET", "POST"])
@login_required
def vlog_page():
    phone = get_logged_in_user_phone()
    user = User.query.filter_by(phone=phone).first()

    # Vérifier si l'utilisateur a fait un retrait dans les 24h
    retrait_recent = Retrait.query.filter(
    Retrait.phone == phone,
    Retrait.statut.in_(["validé", "valider", "approved"])
        ).order_by(Retrait.date.desc()).first()

    if not retrait_recent or (datetime.utcnow() - retrait_recent.date) > timedelta(hours=24):
        flash("Vous n'avez pas effectué un retrait dans les dernières 24h.", "danger")
        return redirect(url_for("dashboard_page"))

    # ----------- SI POST (envoi du vlog) ----------
    if request.method == "POST":
        montant = float(request.form["montant"])
        file = request.files["photo"]

        filename = secure_filename(file.filename)

        # créer le dossier si n’existe pas
        folder = "static/vlogs"
        if not os.path.exists(folder):
            os.makedirs(folder)

        path = os.path.join(folder, filename)
        file.save(path)

        vlog = Vlog(
            phone=phone,
            montant=montant,
            image=filename,
            statut="en_attente"
        )
        db.session.add(vlog)
        db.session.commit()

        return render_template("vlog_loading.html")

    # ----------- affichage des preuves du user =====
    vlogs = Vlog.query.filter_by(phone=phone)\
        .order_by(Vlog.date.desc()).all()

    return render_template("vlog.html", user=user, vlogs=vlogs)

@app.route("/cron/pay_invests")
def cron_pay_invests():
    maintenant = datetime.utcnow()
    invests = Investissement.query.filter_by(actif=True).all()

    total_payes = 0

    for inv in invests:
        # Protéger si dernier_paiement manquant
        if not inv.dernier_paiement:
            inv.dernier_paiement = inv.date_debut

        diff = maintenant - inv.dernier_paiement

        # 🔥 Si 24h sont passées → créditer le revenu
        if diff.total_seconds() >= 86400:

            user = User.query.filter_by(phone=inv.phone).first()
            if user:
                user.solde_revenu += inv.revenu_journalier
                total_payes += 1

            inv.dernier_paiement = maintenant

            # Incrémenter la durée restante
            inv.duree -= 1
            if inv.duree <= 0:
                inv.actif = False

    db.session.commit()
    return f"{total_payes} paiements effectués."

import threading
import time
from datetime import datetime, timedelta

def paiement_quotidien():
    while True:
        time.sleep(60)  # vérifie toutes les 60 secondes

        with app.app_context():  # 🔥 OBLIGATOIRE pour éviter l’erreur "Working outside application context"

            investissements = Investissement.query.filter_by(actif=True).all()

            for inv in investissements:
                now = datetime.utcnow()

                # Si jamais la colonne est vide
                if not inv.dernier_paiement:
                    inv.dernier_paiement = inv.date_debut

                # Vérifie si 24h sont passées
                if now - inv.dernier_paiement >= timedelta(hours=24):

                    user = User.query.filter_by(phone=inv.phone).first()
                    if not user:
                        continue

                    # 🔥 Crédit du revenu
                    user.solde_revenu = float(user.solde_revenu or 0) + inv.revenu_journalier
                    user.solde_total = float(user.solde_total or 0) + inv.revenu_journalier

                    # Met à jour la date du dernier paiement
                    inv.dernier_paiement = now

                    # Réduit la durée restante
                    inv.duree -= 1
                    if inv.duree <= 0:
                        inv.actif = False

                    db.session.commit()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
