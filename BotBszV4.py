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
    filters,
)

# ==============================
# CONFIGURACION SEGURA
# ==============================

API_KEY = os.getenv("60509DF1-3D9D-4B03-A7F4-4CB9LC6EA649")
SECRET_KEY = os.getenv("fab6effe60ec982f683d8982626fa6b1ee6c17cc")
TOKEN = os.getenv("8439810935:AAEFnqLOSjwhRg4f6AmFL1H-ifr3umOxx7E")

FLOW_URL = "https://api.flow.cl/api/payment/create"

if not TOKEN:
    raise ValueError("Falta TELEGRAM_TOKEN en variables de entorno")

if not API_KEY or not SECRET_KEY:
    raise ValueError("Faltan FLOW_API_KEY o FLOW_SECRET_KEY en variables de entorno")


# ==============================
# GENERAR FIRMA FLOW
# ==============================

def generar_firma(params, secret_key):
    cadena = ""

    for key in sorted(params.keys()):
        cadena += f"{key}{params[key]}"

    cadena += secret_key

    return hashlib.sha256(cadena.encode("utf-8")).hexdigest()


# ==============================
# MENSAJE RESULTADO
# ==============================

def generar_mensaje(data, tarjeta):
    if isinstance(data, dict) and "url" in data:
        return f"""✅ PAGO CREADO

Tarjeta:
{tarjeta}

Link de pago:
{data.get("url")}
"""

    return f"""❓ RESPUESTA DESCONOCIDA

Tarjeta:
{tarjeta}

Respuesta:
{data}
"""


# ==============================
# START
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Envíame tarjetas separadas por salto de línea.\n"
        "Formato ejemplo:\n"
        "5154620023923996|01|2029|120\n"
        "5154620023949041|01|2029|196\n"
        "5154620023915653|01|2029|893\n"
    )


# ==============================
# CREAR PAGO
# ==============================

async def crear_pago(session, tarjeta):
    partes = [p.strip() for p in tarjeta.split("|")]

    number = partes[0] if len(partes) >= 1 and partes[0] else "5154620023923996"
    expiry_month = partes[1] if len(partes) >= 2 and partes[1] else "01"
    expiry_year = partes[2] if len(partes) >= 3 and partes[2] else "2029"
    cvv = partes[3] if len(partes) >= 4 and partes[3] else "120"

    params = {
        "apiKey": API_KEY,
        "commerceOrder": f"ORD-{uuid.uuid4().hex[:12]}",
        "subject": "Pago generado",
        "currency": "CLP",
        "amount": int(1000),  # Puedes cambiar el monto según sea necesario
        "cardNumber": number,
        "expiryMonth": expiry_month,
        "expiryYear": expiry_year,
        "cvv": cvv,
    }

    params["s"] = generar_firma(params, SECRET_KEY)

    async with session.post(FLOW_URL, data=params) as res:
        text_response = await res.text()

        try:
            data = json.loads(text_response)
        except json.JSONDecodeError:
            data = text_response

        return res.status, data


# ==============================
# PROCESAR MENSAJES
# ==============================

async def process_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

    tarjetas = [
        line.strip()
        for line in text.split("\n")
        if "|" in line
    ]

    if not tarjetas:
        await update.message.reply_text("❌ No se encontraron tarjetas válidas.")
        return

    results = {
        "live": [],
        "die": [],
        "unknown": [],
    }

    await update.message.reply_text("🔍 Procesando pagos...")

    timeout = ClientTimeout(total=30)

    async with ClientSession(timeout=timeout) as session:
        for tarjeta in tarjetas:
            try:
                status, data = await crear_pago(session, tarjeta)

                if status != 200:
                    results["unknown"].append(tarjeta)
                    await update.message.reply_text(
                        f"⚠️ Flow respondió HTTP {status} para:\n{tarjeta}"
                    )
                    print(f"Flow error {status}: {data}")
                    continue

                if isinstance(data, dict) and "url" in data:
                    results["live"].append(tarjeta)
                else:
                    results["unknown"].append(tarjeta)

                await update.message.reply_text(generar_mensaje(data, tarjeta))

            except asyncio.TimeoutError:
                results["unknown"].append(tarjeta)
                await update.message.reply_text(f"⏱️ Timeout:\n{tarjeta}")

            except ValueError as e:
                results["die"].append(tarjeta)
                await update.message.reply_text(f"❌ Dato inválido:\n{str(e)}\n\n{tarjeta}")

            except Exception as e:
                results["die"].append(tarjeta)
                print(f"Error procesando tarjeta '{tarjeta}': {e}")
                await update.message.reply_text(f"❌ Error procesando:\n{tarjeta}")

            await asyncio.sleep(1)

    live_count = len(results["live"])
    die_count = len(results["die"])
    unknown_count = len(results["unknown"])
    total = live_count + die_count + unknown_count

    resumen = f"""✅ CREADOS: {live_count}
❌ ERROR: {die_count}
❓ DESCONOCIDOS: {unknown_count}
📊 TOTAL: {total}
"""

    await update.message.reply_text(resumen)


# ==============================
# KEEP ALIVE PARA RENDER
# ==============================

class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is running")

    def log_message(self, format, *args):
        return


def keep_alive():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)

    threading.Thread(
        target=server.serve_forever,
        daemon=True,
    ).start()


# ==============================
# MAIN
# ==============================

def main():
    keep_alive()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            process_payments,
        )
    )

    print("Bot ejecutándose")

    app.run_polling()


if __name__ == "__main__":
    main()