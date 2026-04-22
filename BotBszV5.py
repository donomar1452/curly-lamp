const TelegramBot = require("node-telegram-bot-api");
const express = require("express");
const fetch = require("node-fetch");
const crypto = require("crypto");

const app = express();

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// =========================
// CONFIGURACIÓN
// =========================

// Token de tu bot de Telegram
const TELEGRAM_TOKEN = "8439810935:AAEFnqLOSjwhRg4f6AmFL1H-ifr3umOxx7E";

// Credenciales Flow
const API_KEY =
  "60509DF1-3D9D-4B03-A7F4-4CB9LC6EA649";

const SECRET_KEY =
  "fab6effe60ec982f683d8982626fa6b1ee6c17cc";

// Producción
const FLOW_URL =
  "https://www.flow.cl/api/payment/create";

// Crear bot
const bot = new TelegramBot(
  TELEGRAM_TOKEN,
  { polling: true }
);

// =========================
// FUNCIÓN FIRMA SHA256
// =========================

function generarFirma(params) {

  const keys =
    Object.keys(params).sort();

  let cadena = "";

  keys.forEach(key => {
    cadena += key + params[key];
  });

  cadena += SECRET_KEY;

  return crypto
    .createHash("sha256")
    .update(cadena)
    .digest("hex");
}

// =========================
// CREAR PAGO FLOW
// =========================

async function crearPago(monto, email) {

  try {

    const params = {
      apiKey: API_KEY,

      commerceOrder:
        "ORD-" + Date.now(),

      subject: "Pago desde Telegram",

      currency: "CLP",

      amount: monto,

      email: email
    };

    const firma =
      generarFirma(params);

    params.s = firma;

    const response =
      await fetch(
        FLOW_URL,
        {
          method: "POST",

          headers: {
            "Content-Type":
              "application/x-www-form-urlencoded"
          },

          body:
            new URLSearchParams(
              params
            )
        }
      );

    const data =
      await response.json();

    return data;

  } catch (error) {

    return {
      error: error.message
    };

  }

}

// =========================
// COMANDO /start
// =========================

bot.onText(/\/start/, msg => {

  bot.sendMessage(
    msg.chat.id,

    "Bienvenido.\n\n" +
    "Usa:\n" +
    "/pagar 1000\n\n" +
    "Ejemplo:\n" +
    "/pagar 5000"
  );

});

// =========================
// COMANDO /pagar
// =========================

bot.onText(
  /\/pagar (\d+)/,

  async (msg, match) => {

    const chatId =
      msg.chat.id;

    const monto =
      parseInt(match[1]);

    bot.sendMessage(
      chatId,

      "Creando pago..."
    );

    const email =
      "cliente@email.com";

    const pago =
      await crearPago(
        monto,
        email
      );

    if (pago.url) {

      const link =
        `${pago.url}?token=${pago.token}`;

      bot.sendMessage(
        chatId,

        "Pago creado correctamente\n\n" +
        "Monto: $" + monto + "\n\n" +
        "Pagar aquí:\n" +
        link
      );

    } else {

      bot.sendMessage(
        chatId,

        "Error al crear pago:\n\n" +
        JSON.stringify(pago)
      );

    }

  }
);

// =========================
// WEBHOOK DE CONFIRMACIÓN
// =========================

app.post(
  "/webhook-flow",

  (req, res) => {

    console.log(
      "Pago confirmado:",
      req.body
    );

    res.sendStatus(200);

  }
);

// =========================
// SERVIDOR
// =========================

app.listen(3000, () => {

  console.log(
    "Bot ejecutándose..."
  );

});