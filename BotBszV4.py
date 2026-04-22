import asyncio
import json
import os
import uuid
import hmac
import hashlib
import tempfile
from aiohttp import ClientSession, ClientTimeout
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from dotenv import load_dotenv

# Asegurar que encuentre el archivo .env sin importar desde dónde se ejecute la terminal
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(dotenv_path=env_path)

# Diccionario para almacenar los resultados de las tarjetas
results = {
    "live": [],
    "die": [],
    "unknown": []
}

# Token del bot de Telegram (predeterminado)
TOKEN = os.getenv("8665043435:AAHFivj5qzSZduT71qGJujoFengHDe3AX_U")

# URL base de la API de Flow
FLOW_URL = "https://api.flow.cl/api/payment/create"

# Credenciales de la API de Flow
FLOW_API_KEY = os.getenv("60509DF1-3D9D-4B03-A7F4-4CB9LC6EA649")
FLOW_SECRET_KEY = os.getenv("fab6effe60ec982f683d8982626fa6b1ee6c17cc")

if not TOKEN or not FLOW_API_KEY or not FLOW_SECRET_KEY:
    print("❌ ERROR: Faltan las claves de API (TELEGRAM_BOT_TOKEN, FLOW_API_KEY o FLOW_SECRET_KEY). Revisa tu archivo .env.")
    exit(1)

# Ruta al archivo de bloqueo
LOCK_FILE = os.path.join(tempfile.gettempdir(), 'bot_lock_bsz')

def generar_firma(params, secret_key):
    """Genera la firma HMAC-SHA256 requerida por la API de Flow."""
    claves_ordenadas = sorted(params.keys())
    string_a_firmar = "".join([f"{k}{params[k]}" for k in claves_ordenadas])
    firma = hmac.new(secret_key.encode('utf-8'), string_a_firmar.encode('utf-8'), hashlib.sha256).hexdigest()
    return firma

def generar_mensaje(data, tarjeta):
    """Genera el mensaje formateado con la respuesta de la API."""
    code = data.get("code")
    status_msg = data.get("message", "Sin detalles adicionales")
    
    if code == 0:
        estado = "❌ DIE"
    elif code == 2:
        estado = "❓ UNKNOWN"
    else:
        estado = "✅ LIVE"
        
    return f"💳 <b>Tarjeta:</b> <code>{tarjeta}</code>\n📊 <b>Estado:</b> {estado}\n💬 <b>Respuesta:</b> {status_msg}"

def acquire_lock():
    """Adquiere un bloqueo."""
    try:
        with open(LOCK_FILE, 'x'):
            return True
    except FileExistsError:
        return False

def release_lock():
    """Libera el bloqueo."""
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "¡Hola! Envíame una lista de tarjetas separadas por línea (formato xxxx|xxxx|xxxx) para validarlas.\n"
        "También puedes mencionar al bot en un grupo con las tarjetas."
    )

async def validate_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    bot_username = (await context.bot.get_me()).username
    if update.message.chat.type != "private" and f"@{bot_username}" not in update.message.text:
        return

    text = update.message.text.replace(f"@{bot_username}", "").strip()
    lines = [l.strip() for l in text.split('\n') if '|' in l]

    if not lines:
        await update.message.reply_text("❌ No se encontraron tarjetas válidas.")
        return

    live_count = die_count = unknown_count = 0
    await update.message.reply_text("🔍 Validando tarjetas...\n")

    async with ClientSession() as session:
        for tarjeta in lines:
            try:
                partes = [p.strip() for p in tarjeta.split("|")]

                number = partes[0] if len(partes) >= 1 and partes[0] else "5154620023923996"
                expiry_month = partes[1] if len(partes) >= 2 and partes[1] else "01"
                expiry_year = partes[2] if len(partes) >= 3 and partes[2] else "2029"
                cvv = partes[3] if len(partes) >= 4 and partes[3] else "120"

                params = {
                    "apiKey": FLOW_API_KEY,
                    "commerceOrder": f"ORD-{uuid.uuid4().hex[:12]}",
                    "cardNumber": number,
                    "expiryMonth": expiry_month,
                    "expiryYear": expiry_year,
                    "cvv": cvv
                }

                params['signature'] = generar_firma(params, FLOW_SECRET_KEY)

                async with session.post(
                    FLOW_URL,
                    headers={
                        'Content-Type': 'application/json',
                        'User-Agent': 'Mozilla/5.0'
                    },
                    json=params
                ) as res:
                    text_response = await res.text()

                    try:
                        data = json.loads(text_response)
                    except json.JSONDecodeError:
                        await update.message.reply_text(
                            f"⚠️ Respuesta inesperada para {tarjeta}:\n{text_response}"
                        )
                        results["unknown"].append(tarjeta)
                        unknown_count += 1
                        continue

                    card_info = data.get("card", {}).get("card", tarjeta)
                    code = data.get("code")
                    status = data.get("status", "N/A")

                    if code == 0:
                        results["die"].append(card_info)
                        die_count += 1
                    elif code == 2:
                        results["unknown"].append(card_info)
                        unknown_count += 1
                    else:
                        results["live"].append(card_info)
                        live_count += 1

                    mensaje = generar_mensaje(data, tarjeta)
                    await update.message.reply_text(mensaje, parse_mode='HTML')

            except Exception as e:
                results["die"].append(tarjeta)
                die_count += 1
                await update.message.reply_text(f"❌ Error al validar {tarjeta}:\n{e}")

            await asyncio.sleep(1)

        total = live_count + die_count + unknown_count
        resumen = f"""
✅ LIVE: {live_count}
❌ DIE: {die_count}
❓ UNKNOWN: {unknown_count}
📊 TOTAL: {total}
🔍 Verificado con el bot BSZChecker
🔍 Web : https://chekerv2bsz.foroactivo.com 
"""
        await update.message.reply_text(resumen)

def main():
    if not acquire_lock():
        print("Otra instancia del bot ya está ejecutando.")
        return

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, validate_cards))

    try:
        app.run_polling()
    finally:
        release_lock()

if __name__ == "__main__":
    main()