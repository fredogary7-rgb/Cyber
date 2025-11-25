from app import app, db

with app.app_context():
    print("⚠️ Suppression de toutes les tables...")
    db.drop_all()

    print("📌 Création des nouvelles tables...")
    db.create_all()

    print("✅ Base de données réinitialisée avec succès !")
