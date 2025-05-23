from flask import Flask, request, render_template, redirect
from flask_sqlalchemy import SQLAlchemy
from itsdangerous import URLSafeTimedSerializer
from datetime import datetime
from dotenv import load_dotenv
import os
from flask_migrate import Migrate
from paises import PAISES_CODIGOS

# ---------------------------
# Configuración inicial
# ---------------------------
load_dotenv()

app = Flask(__name__)
SECRET_KEY = os.environ.get("SECRET_KEY", "clave-super-secreta")
serializer = URLSafeTimedSerializer(SECRET_KEY)

# ---------------------------
# Configuración de base de datos
# ---------------------------
db_url = os.environ.get("DATABASE_URL", "sqlite:///votos.db")
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# ---------------------------
# Modelos
# ---------------------------
class Voto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50), unique=True, nullable=False, index=True)
    ci = db.Column(db.BigInteger, unique=True, nullable=False, index=True)
    candidato = db.Column(db.String(100), nullable=False)
    pais = db.Column(db.String(100), nullable=False)
    ciudad = db.Column(db.String(100), nullable=False)
    dia_nacimiento = db.Column(db.Integer, nullable=False)
    mes_nacimiento = db.Column(db.Integer, nullable=False)
    anio_nacimiento = db.Column(db.Integer, nullable=False)
    latitud = db.Column(db.Float, nullable=True)
    longitud = db.Column(db.Float, nullable=True)
    ip = db.Column(db.String(50), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

# ---------------------------
# Crear tablas si no existen
# ---------------------------
with app.app_context():
    db.create_all()

# ---------------------------
# Página principal
# ---------------------------
@app.route('/')
def index():
    return render_template("votar.html", numero="+000000000")

# ---------------------------
# Página de votación (sin token ni validación)
# ---------------------------
@app.route('/votar')
def votar():
    return render_template("votar.html", numero="+000000000")

# ---------------------------
# Enviar voto
# ---------------------------
@app.route('/enviar_voto', methods=['POST'])
def enviar_voto():
    numero = request.form.get('numero')
    ci = request.form.get('ci')
    candidato = request.form.get('candidato')
    pais = request.form.get('pais')
    ciudad = request.form.get('ciudad')
    dia = request.form.get('dia_nacimiento')
    mes = request.form.get('mes_nacimiento')
    anio = request.form.get('anio_nacimiento')

    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()

    if not all([numero, ci, candidato, pais, ciudad, dia, mes, anio]):
        return "Faltan campos obligatorios."

    ci = int(ci)

    if Voto.query.filter((Voto.numero == numero) | (Voto.ci == ci)).first():
        return render_template("voto_ya_registrado.html")

    nuevo_voto = Voto(
        numero=numero,
        ci=ci,
        candidato=candidato,
        pais=pais,
        ciudad=ciudad,
        dia_nacimiento=int(dia),
        mes_nacimiento=int(mes),
        anio_nacimiento=int(anio),
        ip=ip
    )
    db.session.add(nuevo_voto)
    db.session.commit()

    return render_template("voto_exitoso.html",
                           candidato=candidato,
                           numero=numero,
                           ci=ci,
                           dia=dia,
                           mes=mes,
                           anio=anio,
                           ciudad=ciudad,
                           pais=pais)

# ---------------------------
# Página de preguntas frecuentes
# ---------------------------
@app.route('/preguntas')
def preguntas_frecuentes():
    return render_template("preguntas.html")

# ---------------------------
# Ejecutar localmente
# ---------------------------
if __name__ == '__main__':
    app.run(debug=True)
