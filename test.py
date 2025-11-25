from app import app, db
from sqlalchemy import text

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS premier_depot BOOLEAN DEFAULT FALSE;'))
        conn.commit()

print("✅ Colonne premier_depot créée (ou déjà existante).")
