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
# Configuración inicial este sirve 234
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
# CAMBIO EN MODELO VOTO
class Voto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50), unique=True, nullable=False, index=True)
    ci = db.Column(db.BigInteger, unique=False, nullable=True, index=True)  # <--- ahora opcional
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
    print(json.dumps(data, indent=2))

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

            # Guardar número si no está ya en tabla temporal
            if not NumeroTemporal.query.filter_by(numero=numero_completo).first():
                db.session.add(NumeroTemporal(numero=numero_completo))
                db.session.commit()

            # Generar token y link de votación
            token = serializer.dumps(numero_completo)
            dominio = os.environ.get("AZURE_DOMAIN")
            if not dominio:
                dominio = request.host_url.rstrip('/')
            link = f"{dominio}/votar?token={token}"

            # Preparar mensaje personalizado y profesional
            mensaje = (
                "Estás por ejercer un derecho fundamental como ciudadano boliviano.\n\n"
                "Participa en las *Primarias Bolivia 2025* y elige de manera libre y responsable.\n\n"
                f"Aquí tienes tu enlace único para votar (válido por 10 minutos):\n{link}\n\n"
                "Este enlace es personal e intransferible. Solo se permite un voto por persona.\n\n"
                "Gracias por ser parte del cambio que Bolivia necesita."
            )


            # Enviar por WhatsApp
            url = "https://waba-v2.360dialog.io/messages"
            headers = {
                "Content-Type": "application/json",
                "D360-API-KEY": os.environ.get("WABA_TOKEN")
            }
            body = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": "+" + numero,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": mensaje
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

        return redirect("https://wa.me/59172902813?text=Hola,%20deseo%20participar%20en%20este%20proceso%20democrático%20porque%20creo%20en%20el%20cambio.%20Quiero%20ejercer%20mi%20derecho%20a%20votar%20de%20manera%20libre%20y%20responsable%20por%20el%20futuro%20de%20Bolivia.")
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
# CAMBIO EN RUTA /enviar_voto
@app.route('/enviar_voto', methods=['POST'])
def enviar_voto():
    numero = request.form.get('numero')
    ci = request.form.get('ci') or None  # <--- aceptar vacío
    candidato = request.form.get('candidato')
    pais = request.form.get('pais')
    ciudad = request.form.get('ciudad')
    dia = request.form.get('dia_nacimiento')
    mes = request.form.get('mes_nacimiento')
    anio = request.form.get('anio_nacimiento')

    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()

    if not all([numero, candidato, pais, ciudad, dia, mes, anio]):
        return "Faltan campos obligatorios."

    if ci:
        try:
            ci = int(ci)
        except ValueError:
            return "CI inválido."
    else:
        ci = None  # permitir dejar vacío

    if Voto.query.filter_by(numero=numero).first():
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
