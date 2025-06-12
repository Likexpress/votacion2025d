from flask import Flask, request, render_template, redirect, jsonify
from flask_sqlalchemy import SQLAlchemy
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from datetime import datetime
from dotenv import load_dotenv
import os
import requests
from flask_migrate import Migrate
import json
import csv
from paises import PAISES_CODIGOS
from flask import session
from flask import render_template

# ---------------------------
# Configuración inicial
# ---------------------------
load_dotenv()

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
    genero = db.Column(db.String(10), nullable=False)
    pais = db.Column(db.String(100), nullable=False)
    departamento = db.Column(db.String(100), nullable=False)
    provincia = db.Column(db.String(100), nullable=False)
    municipio = db.Column(db.String(100), nullable=False)
    recinto = db.Column(db.String(100), nullable=False)
    dia_nacimiento = db.Column(db.Integer, nullable=False)
    mes_nacimiento = db.Column(db.Integer, nullable=False)
    anio_nacimiento = db.Column(db.Integer, nullable=False)
    latitud = db.Column(db.Float, nullable=True)
    longitud = db.Column(db.Float, nullable=True)
    ip = db.Column(db.String(50), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    pregunta1 = db.Column(db.String(10), nullable=False)
    candidato = db.Column(db.String(100), nullable=False)
    pregunta2 = db.Column(db.String(10), nullable=False)
    pregunta3 = db.Column(db.String(10), nullable=False)
    ci = db.Column(db.BigInteger, nullable=True)

class NumeroTemporal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50), unique=True, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

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

            # Generar token con dominio y número
            token_data = {
                "numero": numero_completo,
                "dominio": os.environ.get("AZURE_DOMAIN", request.host_url.rstrip('/'))
            }
            token = serializer.dumps(token_data)

            dominio = os.environ.get("AZURE_DOMAIN") or request.host_url.rstrip('/')
            link = f"{dominio}/votar?token={token}"

            mensaje = (
                "Estás por ejercer un derecho fundamental como ciudadano boliviano.\n\n"
                "Participa en las *Primarias Bolivia 2025* y elige de manera libre y responsable.\n\n"
                f"Aquí tienes tu enlace único para votar (válido por 10 minutos):\n{link}\n\n"
                "Este enlace es personal e intransferible. Solo se permite un voto por persona.\n\n"
                "Gracias por ser parte del cambio que Bolivia necesita."
            )

            # Enviar mensaje por WhatsApp
            url = "https://waba-v2.360dialog.io/messages"
            headers = {
                "Content-Type": "application/json",
                "D360-API-KEY": os.environ.get("WABA_TOKEN")
            }
            body = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": numero_completo,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": mensaje
                }
            }

            r = requests.post(url, headers=headers, json=body)

            if r.status_code == 200:
                print("✅ Enlace enviado correctamente.")

                # ✅ Guardar o actualizar número_confirmado
                registro = NumeroTemporal.query.filter_by(numero=numero_completo).first()
                if registro:
                    registro.numero_confirmado = numero_completo
                else:
                    nuevo = NumeroTemporal(numero=numero_completo, numero_confirmado=numero_completo)
                    db.session.add(nuevo)

                db.session.commit()
            else:
                print("❌ Error al enviar mensaje:", r.text)

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


from flask import session

@app.route('/votar')
def votar():
    token = request.args.get('token')
    if not token:
        return "Acceso no válido."

    try:
        data = serializer.loads(token, max_age=600)
        numero = data.get("numero")
        dominio_token = data.get("dominio")
        dominio_esperado = os.environ.get("AZURE_DOMAIN")

        if dominio_token != dominio_esperado:
            return "Dominio inválido para este enlace."

    except SignatureExpired:
        return "El enlace ha expirado. Solicita uno nuevo."
    except BadSignature:
        return "Enlace inválido o alterado."
    except Exception as e:
        return f"Error al procesar el token: {str(e)}"

    # ✅ Verificación completa del número y número_confirmado
    registro = NumeroTemporal.query.filter_by(numero=numero).first()
    if not registro or registro.numero_confirmado != numero:
        return render_template("numero_no_coincide.html")

    # Si ya votó
    if Voto.query.filter_by(numero=numero).first():
        return render_template("voto_ya_registrado.html")

    # Si todo está correcto, se muestra el formulario
    return render_template("votar.html", numero=numero)






# ---------------------------
# Enviar voto
# ---------------------------
@app.route('/enviar_voto', methods=['POST'])
def enviar_voto():
    numero = request.form.get('numero')
    genero = request.form.get('genero')
    pais = request.form.get('pais')
    departamento = request.form.get('departamento')
    provincia = request.form.get('provincia')
    municipio = request.form.get('municipio')
    recinto = request.form.get('recinto')
    dia = request.form.get('dia_nacimiento')
    mes = request.form.get('mes_nacimiento')
    anio = request.form.get('anio_nacimiento')
    pregunta1 = request.form.get('pregunta1')
    candidato = request.form.get('candidato')
    pregunta2 = request.form.get('pregunta2')
    pregunta3 = request.form.get('pregunta3')
    ci = request.form.get('ci') or None

    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()

    # Validación de campos obligatorios
    if not all([numero, genero, pais, departamento, provincia, municipio, recinto, dia, mes, anio, pregunta1, candidato, pregunta2, pregunta3]):
        return "Faltan campos obligatorios.", 400

    if pregunta3 == "Sí" and not ci:
        return "Debes ingresar tu CI si respondes que colaborarás en el control del voto.", 400

    if ci:
        try:
            ci = int(ci)
        except:
            return "CI inválido.", 400

    # Validación de doble voto
    if Voto.query.filter_by(numero=numero).first():
        return render_template("voto_ya_registrado.html")

    # Validación de coincidencia entre número ingresado y número confirmado por WhatsApp
    registro = NumeroTemporal.query.filter_by(numero=numero).first()
    if not registro or registro.numero_confirmado != numero:
        return render_template("numero_no_coincide.html")

    # Registro del voto
    nuevo_voto = Voto(
        numero=numero,
        genero=genero,
        pais=pais,
        departamento=departamento,
        provincia=provincia,
        municipio=municipio,
        recinto=recinto,
        dia_nacimiento=int(dia),
        mes_nacimiento=int(mes),
        anio_nacimiento=int(anio),
        pregunta1=pregunta1,
        candidato=candidato,
        pregunta2=pregunta2,
        pregunta3=pregunta3,
        ci=ci,
        ip=ip
    )

    db.session.add(nuevo_voto)
    NumeroTemporal.query.filter_by(numero=numero).delete()
    db.session.commit()

    return render_template("voto_exitoso.html",
                           numero=numero,
                           genero=genero,
                           pais=pais,
                           departamento=departamento,
                           provincia=provincia,
                           municipio=municipio,
                           recinto=recinto,
                           dia=dia,
                           mes=mes,
                           anio=anio,
                           candidato=candidato)









# ---------------------------
# API local desde CSV
# ---------------------------
@app.route('/api/recintos')
def api_recintos():
    archivo = os.path.join(os.path.dirname(__file__), "RecintosParaPrimaria.csv")
    datos = []
    with open(archivo, encoding='utf-8') as f:
        lector = csv.DictReader(f)
        for fila in lector:
            datos.append({
                "nombre_pais": fila["nombre_pais"],
                "nombre_departamento": fila["nombre_departamento"],
                "nombre_provincia": fila["nombre_provincia"],
                "nombre_municipio": fila["nombre_municipio"],
                "nombre_recinto": fila["nombre_recinto"]
            })
    return jsonify(datos)

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
