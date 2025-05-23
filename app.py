from flask import Flask, request, render_template, redirect
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from datetime import datetime
import os

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", "sqlite:///votos.db")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Modelo de la base de datos
class Voto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50), nullable=False)
    ci = db.Column(db.BigInteger, nullable=False)
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

# Redireccionar raíz al formulario directamente
@app.route('/')
def index():
    return redirect('/votar')

# Formulario de votación
@app.route('/votar')
def votar():
    return render_template("votar.html", numero="+000000000")

# Procesar voto
@app.route('/enviar_voto', methods=['POST'])
def enviar_voto():
    numero = request.form.get('numero', '')
    ci = request.form.get('ci')
    candidato = request.form.get('candidato')
    pais = request.form.get('pais')
    ciudad = request.form.get('ciudad')
    dia = request.form.get('dia_nacimiento')
    mes = request.form.get('mes_nacimiento')
    anio = request.form.get('anio_nacimiento')

    if not all([numero, ci, candidato, pais, ciudad, dia, mes, anio]):
        return "Faltan campos obligatorios."

    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()

    # Permitir múltiples votos para +000000000 (modo demo o pruebas)
    if numero == "+000000000":
        return render_template("voto_exitoso.html",
                               candidato=candidato,
                               numero=numero,
                               ci=ci,
                               dia=dia,
                               mes=mes,
                               anio=anio,
                               ciudad=ciudad,
                               pais=pais)

    # Evitar múltiples votos por el mismo número (excepto el +000000000)
    if Voto.query.filter_by(numero=numero).first():
        return render_template("voto_ya_registrado.html")

    # Registrar nuevo voto
    nuevo_voto = Voto(
        numero=numero,
        ci=int(ci),
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

# Crear tablas y ejecutar app
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
