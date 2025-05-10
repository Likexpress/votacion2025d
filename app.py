from flask import Flask, request, render_template, redirect
from flask_sqlalchemy import SQLAlchemy
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from datetime import datetime
from dotenv import load_dotenv
import os
import requests
from flask_migrate import Migrate
import json

# ---------------------------
# Configuración inicial
# ---------------------------
load_dotenv()  # Solo tiene efecto localmente, en Azure se usan variables del entorno

app = Flask(__name__)
SECRET_KEY = os.environ.get("SECRET_KEY", "clave-super-secreta")
serializer = URLSafeTimedSerializer(SECRET_KEY)

# ---------------------------
# Configuración de la base de datos
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

class NumeroTemporal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50), unique=True, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

# ⚠️ SOLO PARA DESARROLLO: En producción usar migraciones
with app.app_context():
    db.create_all()

# ---------------------------
# Webhook para WhatsApp
# ---------------------------
@app.route('/whatsapp', methods=['POST'])
def whatsapp_webhook():
    data = request.json
    print("📥 JSON recibido:")
    print(json.dumps(data, indent=2))  # Log para depuración

    try:
        entry = data['entry'][0]
        value = entry['changes'][0]['value']
        messages = value.get('messages')

        if not messages:
            return "ok", 200

        numero = messages[0]['from']
        texto = messages[0]['text']['body'].strip().lower()

        if "votar" in texto:
            numero_completo = "+" + numero

            if not NumeroTemporal.query.filter_by(numero=numero_completo).first():
                db.session.add(NumeroTemporal(numero=numero_completo))
                db.session.commit()

            token = serializer.dumps(numero_completo)
            dominio = os.environ.get("AZURE_DOMAIN", "https://sistemadevotacion2025.azurewebsites.net")
            link = f"{dominio}/votar?token={token}"

            url = "https://waba-v2.360dialog.io/messages"
            headers = {
                "Content-Type": "application/json",
                "D360-API-KEY": os.environ.get("WABA_TOKEN")
            }
            body = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": "+" + numero,  # ✅ CORREGIDO
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": f"Hola, gracias por participar en las Primarias Bolivia 2025.\n\nAquí tienes tu enlace único para votar (válido por 10 minutos):\n{link}"
                }
            }

            r = requests.post(url, headers=headers, json=body)
            if r.status_code == 200:
                print("✅ Enlace enviado correctamente.")
            else:
                print("❌ Error al enviar:", r.text)

    except Exception as e:
        print("❌ Error procesando mensaje:", str(e))

    return "ok", 200

# ---------------------------
# Página principal
# ---------------------------
@app.route('/')
def index():
    return redirect('/generar_link')

@app.route('/generar_link', methods=['GET', 'POST'])
def generar_link():
    if request.method == 'POST':
        pais = request.form.get('pais')
        numero = request.form.get('numero')

        if not pais or not numero:
            return "Por favor, selecciona un país e ingresa tu número."

        numero = numero.replace(" ", "").replace("-", "")
        if not pais.startswith("+"):
            return "Código de país inválido."

        numero_completo = pais + numero

        if Voto.query.filter_by(numero=numero_completo).first():
            return render_template("voto_ya_registrado.html")

        if not NumeroTemporal.query.filter_by(numero=numero_completo).first():
            db.session.add(NumeroTemporal(numero=numero_completo))
            db.session.commit()

        return redirect("https://wa.me/59172902813?text=Quiero%20votar")

    return render_template("generar_link.html", paises=PAISES_CODIGOS)

# ---------------------------
# Página de votación
# ---------------------------
@app.route('/votar')
def votar():
    token = request.args.get('token')
    if not token:
        return "Acceso no válido."

    try:
        numero = serializer.loads(token, max_age=600)  # 10 minutos
    except SignatureExpired:
        return "El enlace ha expirado. Solicita uno nuevo."
    except BadSignature:
        return "Enlace inválido o alterado."

    if not NumeroTemporal.query.filter_by(numero=numero).first():
        return "Este enlace no fue solicitado correctamente."

    if Voto.query.filter_by(numero=numero).first():
        return render_template("voto_ya_registrado.html")

    return render_template("votar.html", numero=numero)

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
# Lista de países
# ---------------------------
PAISES_CODIGOS = {
    "Bolivia": "+591"
}

# ---------------------------
# Ejecutar localmente
# ---------------------------
if __name__ == '__main__':
    app.run(debug=True)
