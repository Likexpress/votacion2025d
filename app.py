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
from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFProtect
from flask import Flask, request, render_template, redirect, jsonify, session
from datetime import datetime, timedelta
from itsdangerous import URLSafeTimedSerializer




# ---------------------------
# Configuración inicial Hasta aqu sirve 123
# ---------------------------
load_dotenv()

SECRET_KEY = os.environ.get("SECRET_KEY", "clave-super-secreta")
app = Flask(__name__)
app.secret_key = SECRET_KEY

csrf = CSRFProtect(app)  # ✅ Protección CSRF
serializer = URLSafeTimedSerializer(SECRET_KEY)  # ✅ Crear serializer después de definir la clave



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
# Whatsapp
# ---------------------------

@app.route('/whatsapp', methods=['POST'])
@csrf.exempt
def whatsapp_webhook():
    try:
        data = request.get_json()
        print("📥 JSON recibido:")
        print(json.dumps(data, indent=2))

        entry = data.get('entry', [])[0]
        changes = entry.get('changes', [])[0]
        value = changes.get('value', {})
        messages = value.get('messages')

        if not messages:
            return "ok", 200

        numero = messages[0]['from']  # Ej: 591XXXXXXXX
        texto = messages[0].get('text', {}).get('body', '').strip().lower()
        numero_completo = "+" + numero

        print(f"📨 Mensaje recibido de {numero_completo}: '{texto}'")

        # ❌ Ignorar si no contiene "votar"
        if "votar" not in texto:
            print("❌ Mensaje ignorado (no contiene 'votar')")
            return "ok", 200

        # ⚠️ Consultar si está bloqueado
        bloqueo = db.session.execute(
            db.select(BloqueoWhatsapp).where(BloqueoWhatsapp.numero == numero_completo)
        ).scalar_one_or_none()

        if bloqueo and bloqueo.bloqueado:
            print(f"🚫 Número bloqueado: {numero_completo}")
            return "ok", 200

        # ✅ Verificar si está autorizado (debe existir en NumeroTemporal)
        autorizado = NumeroTemporal.query.filter_by(numero=numero_completo).first()
        if not autorizado:
            print(f"❌ Número no autorizado: {numero_completo}")

            # Manejo de advertencias
            if not bloqueo:
                bloqueo = BloqueoWhatsapp(numero=numero_completo, intentos=1)
                db.session.add(bloqueo)
            else:
                bloqueo.intentos += 1
                if bloqueo.intentos >= 4:
                    bloqueo.bloqueado = True

            db.session.commit()

            if bloqueo.intentos < 4:
                advertencia = (
                    "⚠️ Para recibir tu enlace de votación, primero debes registrarte en el portal oficial:\n\n"
                    "👉 https://bit.ly/primariaBK\n\n"
                    "Asegúrate de ingresar correctamente tu número de WhatsApp durante el registro, "
                    "ya que solo ese número podrá recibir el enlace.\n\n"
                    f"Advertencia {bloqueo.intentos}/3"
                )
            else:
                advertencia = (
                    "🚫 Has excedido el número de intentos permitidos. "
                    "Tus mensajes ya no serán respondidos por este sistema."
                )

            # Enviar advertencia solo si aún no está bloqueado
            requests.post(
                "https://waba-v2.360dialog.io/messages",
                headers={
                    "Content-Type": "application/json",
                    "D360-API-KEY": os.environ.get("WABA_TOKEN")
                },
                json={
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": numero_completo,
                    "type": "text",
                    "text": {
                        "preview_url": False,
                        "body": advertencia
                    }
                }
            )
            return "ok", 200

        # ✅ Ya está autorizado, usar su token guardado
        if not autorizado.token:
            print(f"⚠️ No se encontró token almacenado para {numero_completo}")
            return "ok", 200

        link = f"{os.environ.get('AZURE_DOMAIN', request.host_url.rstrip('/')).rstrip('/')}/votar?token={autorizado.token}"

        print(f"🔗 Enlace recuperado: {link}")

        mensaje = (
            "Estás por ejercer un derecho fundamental como ciudadano boliviano.\n\n"
            "Participa en las *Primarias Bolivia 2025* y elige de manera libre y responsable.\n\n"
            f"Aquí tienes tu enlace único para votar (válido por 10 minutos):\n{link}\n\n"
            "Este enlace es personal e intransferible. Solo se permite un voto por persona.\n\n"
            "Gracias por ser parte del cambio que Bolivia necesita."
        )

        # Enviar mensaje con el enlace
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": numero_completo,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": mensaje
            }
        }

        headers = {
            "Content-Type": "application/json",
            "D360-API-KEY": os.environ.get("WABA_TOKEN")
        }

        respuesta = requests.post("https://waba-v2.360dialog.io/messages", headers=headers, json=payload)
        if respuesta.status_code == 200:
            print("✅ Enlace enviado correctamente.")
        else:
            print(f"❌ Error al enviar mensaje WhatsApp: {respuesta.status_code} - {respuesta.text}")

    except Exception as e:
        print("❌ Error procesando webhook:", str(e))

    return "ok", 200





# ---------------------------
# Bloqueo WHatsapp
# ---------------------------

class BloqueoWhatsapp(db.Model):
    __tablename__ = "bloqueo_whatsapp"
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50), unique=True, nullable=False)
    intentos = db.Column(db.Integer, default=0)
    bloqueado = db.Column(db.Boolean, default=False)



# ---------------------------
# Página principal
# ---------------------------
@app.route('/')
def index():
    return redirect('/generar_link')


# ---------------------------
# Generar Link
# ---------------------------

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

        # Si ya votó, mostrar mensaje
        if Voto.query.filter_by(numero=numero_completo).first():
            return render_template("voto_ya_registrado.html")

        # Obtener dominio
        dominio = os.environ.get("AZURE_DOMAIN", request.host_url.rstrip('/')).rstrip('/')

        # Generar token único
        token_data = {
            "numero": numero_completo,
            "dominio": dominio
        }
        token = serializer.dumps(token_data)

        # Verificar si ya está registrado
        temporal = NumeroTemporal.query.filter_by(numero=numero_completo).first()
        if not temporal:
            temporal = NumeroTemporal(numero=numero_completo, token=token)
            db.session.add(temporal)
        else:
            temporal.token = token  # Actualizar token si ya existía

        db.session.commit()

        # Redireccionar al WhatsApp con el mensaje prellenado
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
        data = serializer.loads(token, max_age=600)
        numero = data.get("numero")
        dominio_token = data.get("dominio")
        dominio_esperado = os.environ.get("AZURE_DOMAIN")

        # Validación de dominio
        if dominio_token != dominio_esperado:
            return "Dominio inválido para este enlace."

    except SignatureExpired:
        return "El enlace ha expirado. Solicita uno nuevo."
    except BadSignature:
        return "Enlace inválido o alterado."

    # Verificar que el número esté en NumeroTemporal (aún válido)
    if not NumeroTemporal.query.filter_by(numero=numero).first():
        enviar_mensaje_whatsapp(numero, "Detectamos que intentó ingresar datos falsos. Por favor, use su número real o será bloqueado.")
        return "Este enlace ya fue utilizado, es inválido o ha intentado manipular el proceso."

    # Verificar si ya votó
    if Voto.query.filter_by(numero=numero).first():
        return render_template("voto_ya_registrado.html")

    # Guardar el número del token validado en sesión para comparación posterior segura
    session['numero_token'] = numero

    # Renderizar formulario y enviar el token también como campo oculto
    return render_template("votar.html", numero=numero, token=token)




# ---------------------------
# Enviar voto
# ---------------------------
@app.route('/enviar_voto', methods=['POST'])
def enviar_voto():
    # Verifica que el número de sesión esté presente
    numero = session.get('numero_token')
    if not numero:
        return "Acceso denegado: sin sesión válida o token expirado.", 403

    # Extraer datos del formulario
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
    latitud = request.form.get('latitud')
    longitud = request.form.get('longitud')

    # IP del usuario
    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()

    # Validar campos requeridos
    if not all([genero, pais, departamento, provincia, municipio, recinto,
                dia, mes, anio, pregunta1, candidato, pregunta2, pregunta3]):
        return "Faltan campos obligatorios.", 400

    if pregunta3 == "Sí" and not ci:
        return "Debes ingresar tu CI si respondes que colaborarás en el control del voto.", 400

    if ci:
        try:
            ci = int(ci)
        except:
            return "CI inválido.", 400

    # Verificar si ya votó
    if Voto.query.filter_by(numero=numero).first():
        return render_template("voto_ya_registrado.html")

    # Guardar el nuevo voto
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
        latitud=float(latitud) if latitud else None,
        longitud=float(longitud) if longitud else None,
        ip=ip,
        pregunta1=pregunta1,
        candidato=candidato,
        pregunta2=pregunta2,
        pregunta3=pregunta3,
        ci=ci
    )

    # Guardar en la base de datos y limpiar número temporal
    db.session.add(nuevo_voto)
    NumeroTemporal.query.filter_by(numero=numero).delete()
    db.session.commit()

    # Limpiar sesión
    session.pop('numero_token', None)

    # Mostrar pantalla de éxito
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
