import asyncio
import json
import hashlib
import threading
import os

from http.server import BaseHTTPRequestHandler, HTTPServer
from aiohttp import ClientSession, ClientTimeout

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)

# ==============================
# CONFIGURACIÓN API FLOW
# ==============================

API_KEY = "60509DF1-3D9D-4B03-A7F4-4CB9LC6EA649"
SECRET_KEY = "fab6effe60ec982f683d8982626fa6b1ee6c17cc"

FLOW_URL = "https://sandbox.flow.cl/api/payment/create"

# ==============================
# RESULTADOS
# ==============================

results = {
    "live": [],
    "die": [],
    "unknown": []
}

TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TOKEN:
    TOKEN = input("Introduce el TOKEN del bot de Telegram: ")

# ==============================
# GENERAR FIRMA
# ==============================

def generar_firma(params, secret_key):

    cadena = ""

    for key in sorted(params.keys()):
        cadena += f"{key}{params[key]}"

    cadena += secret_key

    return hashlib.sha256(
        cadena.encode("utf-8")
    ).hexdigest()

# ==============================
# MENSAJE RESULTADO
# ==============================

def generar_mensaje(data, linea):

    if "url" in data:

        return f"""
✅ LIVE

Dato:
{linea}

Link de pago:
{data.get("url")}
"""

    return f"""
❓ UNKNOWN

Dato:
{linea}

Respuesta:
{data}
"""

# ==============================
# START
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "Envíame líneas separadas por salto de línea.\n"
        "Formato:\n"
        "dato1|dato2|dato3"
    )

# ==============================
# PROCESAR
# ==============================

async def validate_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message:
        return

    results["live"].clear()
    results["die"].clear()
    results["unknown"].clear()

    text = update.message.text.strip()

    lines = [
        l.strip()
        for l in text.split('\n')
        if '|' in l
    ]

    if not lines:

        await update.message.reply_text(
            "❌ No se encontraron líneas válidas."
        )

        return

    live_count = 0
    die_count = 0
    unknown_count = 0

    await update.message.reply_text(
        "🔍 Procesando..."
    )

    timeout = ClientTimeout(total=30)

    async with ClientSession(timeout=timeout) as session:

        for linea in lines:

            try:

                params = {
                    "apiKey": API_KEY,
                    "commerceOrder": f"ORD-{int(asyncio.get_event_loop().time())}",
                    "subject": "Pago generado",
                    "currency": "CLP",
                    "amount": 1000,
                    "email": "cliente@email.com"
                }

                firma = generar_firma(
                    params,
                    SECRET_KEY
                )

                params["s"] = firma

                async with session.post(
                    FLOW_URL,
                    data=params
                ) as res:

                    if res.status != 200:

                        results["unknown"].append(linea)
                        unknown_count += 1

                        await update.message.reply_text(
                            f"⚠️ HTTP {res.status}"
                        )

                        continue

                    text_response = await res.text()

                    try:

                        data = json.loads(
                            text_response
                        )

                    except:

                        data = text_response

                    if isinstance(data, dict) and "url" in data:

                        results["live"].append(linea)
                        live_count += 1

                    else:

                        results["unknown"].append(linea)
                        unknown_count += 1

                    mensaje = generar_mensaje(
                        data,
                        linea
                    )

                    await update.message.reply_text(
                        mensaje
                    )

            except asyncio.TimeoutError:

                results["unknown"].append(linea)
                unknown_count += 1

                await update.message.reply_text(
                    f"⏱️ Timeout: {linea}"
                )

            except Exception as e:

                results["die"].append(linea)
                die_count += 1

                await update.message.reply_text(
                    f"❌ Error: {str(e)}"
                )

            await asyncio.sleep(1)

    total = live_count + die_count + unknown_count

    resumen = f"""
✅ LIVE: {live_count}
❌ DIE: {die_count}
❓ UNKNOWN: {unknown_count}
📊 TOTAL: {total}
"""

    await update.message.reply_text(resumen)

# ==============================
# KEEP ALIVE
# ==============================

class DummyHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()

        self.wfile.write(
            b"Bot is running"
        )

def keep_alive():

    port = int(
        os.environ.get(
            "PORT",
            8080
        )
    )

    server = HTTPServer(
        ("0.0.0.0", port),
        DummyHandler
    )

    threading.Thread(
        target=server.serve_forever,
        daemon=True
    ).start()

# ==============================
# MAIN
# ==============================

def main():

    keep_alive()

    app = ApplicationBuilder().token(
        TOKEN
    ).build()

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            validate_cards
        )
    )

    print("Bot ejecutándose")

    app.run_polling()

if __name__ == "__main__":

    main()