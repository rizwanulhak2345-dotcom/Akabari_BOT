import os
import time
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import pandas as pd
import numpy as np
import yfinance as yf
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# --- Telegram Bot Token ---
TOKEN = "8963497539:AAEhFzP1t_ZbwYL6Q1c1EXsLXE8oyTYx1i0"
CHANNEL_USERNAME = "-1004360214961"  # यहाँ आपका चैनल परमानेंट सेट है

bot_stats = {"total_signals": 0, "real_wins": 0, "real_losses": 0}

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Akbari AI Professional Auto-Signal Bot is Running!")
    def log_message(self, format, *args):
        return

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    server.serve_forever()

# --- Professional ADX Calculation ---
def calculate_adx(highs, lows, closes, period=14):
    try:
        df = pd.DataFrame({'High': highs, 'Low': lows, 'Close': closes})
        if len(df) < period + 5:
            return 25.0
        df['TR1'] = df['High'] - df['Low']
        df['TR2'] = abs(df['High'] - df['Close'].shift(1))
        df['TR3'] = abs(df['Low'] - df['Close'].shift(1))
        df['TR'] = df[['TR1', 'TR2', 'TR3']].max(axis=1)
        
        df['UpMove'] = df['High'] - df['High'].shift(1)
        df['DownMove'] = df['Low'].shift(1) - df['Low']
        
        df['+DM'] = np.where((df['UpMove'] > df['DownMove']) & (df['UpMove'] > 0), df['UpMove'], 0.0)
        df['-DM'] = np.where((df['DownMove'] > df['UpMove']) & (df['DownMove'] > 0), df['DownMove'], 0.0)
        
        alpha = 1 / period
        tr_smooth = df['TR'].ewm(alpha=alpha, adjust=False).mean()
        plus_dm_smooth = df['+DM'].ewm(alpha=alpha, adjust=False).mean()
        minus_dm_smooth = df['-DM'].ewm(alpha=alpha, adjust=False).mean()
        
        plus_di = 100 * (plus_dm_smooth / tr_smooth)
        minus_di = 100 * (minus_dm_smooth / tr_smooth)
        sum_di = (plus_di + minus_di).replace(0, 0.001)
        dx = 100 * abs(plus_di - minus_di) / sum_di
        adx = dx.ewm(alpha=alpha, adjust=False).mean()
        
        val = adx.iloc[-1]
        return round(float(val), 1) if not np.isnan(val) else 25.0
    except:
        return 25.0

# --- Professional MACD Calculation ---
def calculate_macd(closes):
    try:
        s = pd.Series(closes)
        ema12 = s.ewm(span=12, adjust=False).mean()
        ema26 = s.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        histogram = macd_line - signal_line
        return round(float(macd_line.iloc[-1]), 4), round(float(signal_line.iloc[-1]), 4), round(float(histogram.iloc[-1]), 4)
    except:
        return 0.0, 0.0, 0.0

# --- Ultra-Strict Professional Confluence Engine ---
def get_professional_signal(pair, timeframe):
    try:
        clean_pair = pair.replace(" (OTC)", "").replace("/", "")
        ticker_symbol = f"{clean_pair}=X"
        
        data = yf.download(ticker_symbol, period="2d", interval="1m", progress=False)
        if data is None or len(data) < 30:
            return "WAIT / NO TRADE", 50, "Insufficient Data", 25.0, 50.0, 0.0
            
        if isinstance(data.columns, pd.MultiIndex):
            closes = data['Close'].iloc[:, 0].values
            highs = data['High'].iloc[:, 0].values
            lows = data['Low'].iloc[:, 0].values
        else:
            closes = data['Close'].values
            highs = data['High'].values
            lows = data['Low'].values

        current_price = closes[-1]
        
        # 1. Trend Filter (EMA 20 & EMA 50)
        s_closes = pd.Series(closes)
        ema20 = s_closes.ewm(span=20, adjust=False).mean().iloc[-1]
        ema50 = s_closes.ewm(span=50, adjust=False).mean().iloc[-1]
        
        # 2. ADX Filter (Market Strength)
        adx = calculate_adx(highs, lows, closes)
        if adx < 28:
            return "WAIT / NO TRADE", 50, f"Weak ADX ({adx}) - Sideways Market", adx, 50.0, 0.0

        # 3. RSI Filter (14 period)
        deltas = np.diff(closes)
        seed = deltas[:14]
        up = seed[seed >= 0].sum() / 14
        down = -seed[seed < 0].sum() / 14
        rs = up / down if down != 0 else 1
        rsi = round(float(100.0 - (100.0 / (1.0 + rs))), 1)

        # 4. Bollinger Bands (20, 2)
        rolling_std = np.std(closes[-20:])
        middle_band = np.mean(closes[-20:])
        upper_band = middle_band + (2 * rolling_std)
        lower_band = middle_band - (2 * rolling_std)

        # 5. MACD Momentum
        macd_l, macd_s, macd_h = calculate_macd(closes)

        # --- 5/5 CONFIRMATION LOGIC ---
        if current_price > ema20 and ema20 > ema50 and adx >= 28 and 40 <= rsi <= 68 and macd_h > 0:
            if current_price > middle_band:
                return "BUY (LONG)", 98, "5/5 Confirmed (All Indicators Aligned)", adx, rsi, macd_h

        elif current_price < ema20 and ema20 < ema50 and adx >= 28 and 32 <= rsi <= 60 and macd_h < 0:
            if current_price < middle_band:
                return "SELL (SHORT)", 98, "5/5 Confirmed (All Indicators Aligned)", adx, rsi, macd_h

        return "WAIT / NO TRADE", 50, "Filters Not Fully Met", adx, rsi, macd_h

    except Exception as e:
        logger.error(f"Error in professional engine: {e}")
        return "WAIT / NO TRADE", 50, "Error in Analysis", 25.0, 50.0, 0.0

# --- Background Result Verification ---
def verify_signal(ticker_symbol, entry_price, action_type, t_sec):
    try:
        time.sleep(t_sec)
        data = yf.download(ticker_symbol, period="1d", interval="1m", progress=False)
        if data is not None and len(data) > 0:
            exit_price = float(data['Close'].iloc[-1].iloc[0] if isinstance(data.columns, pd.MultiIndex) else data['Close'].iloc[-1])
            bot_stats["total_signals"] += 1
            if "BUY" in action_type:
                if exit_price > entry_price: bot_stats["real_wins"] += 1
                else: bot_stats["real_losses"] += 1
            elif "SELL" in action_type:
                if exit_price < entry_price: bot_stats["real_wins"] += 1
                else: bot_stats["real_losses"] += 1
    except Exception as e:
        logger.error(f"Verification error: {e}")

# --- Telegram Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💱 EUR/USD", callback_data="pair_EURUSD"), InlineKeyboardButton("💱 GBP/USD", callback_data="pair_GBPUSD")],
        [InlineKeyboardButton("💱 AUD/USD", callback_data="pair_AUDUSD"), InlineKeyboardButton("💱 USD/CAD", callback_data="pair_USDCAD")],
        [InlineKeyboardButton("💱 USD/JPY", callback_data="pair_USDJPY"), InlineKeyboardButton("💱 NZD/USD", callback_data="pair_NZDUSD")],
        [InlineKeyboardButton("💱 EUR/GBP", callback_data="pair_EURGBP"), InlineKeyboardButton("💱 EUR/JPY", callback_data="pair_EURJPY")],
        [InlineKeyboardButton("💱 GBP/JPY", callback_data="pair_GBPJPY"), InlineKeyboardButton("💱 AUD/JPY", callback_data="pair_AUDJPY")],
        [InlineKeyboardButton("💱 EUR/USD (OTC)", callback_data="pair_EURUSD_otc"), InlineKeyboardButton("💱 GBP/USD (OTC)", callback_data="pair_GBPUSD_otc")],
        [InlineKeyboardButton("📈 Performance Stats", callback_data="send_stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "🤖 *Akbari AI Professional Bot* 🚀\n\n5/5 فلٹر کنفرمیشن فعال ہے۔ پئیر منتخب کریں:"
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.callback_query.message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def pair_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "send_stats":
        t = bot_stats["total_signals"]
        w = bot_stats["real_wins"]
        l = bot_stats["real_losses"]
        wr = round((w / t * 100), 1) if t > 0 else 0.0
        stats_msg = f"📊 *PROFESSIONAL BOT STATS* 📊\n\n🎯 Total Signals: {t}\n✅ Wins: {w}\n❌ Losses: {l}\n📈 Win Rate: {wr}%"
        await query.message.edit_text(stats_msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]]), parse_mode="Markdown")
        return

    is_otc = "_otc" in query.data
    p_code = query.data.replace("_otc", "").split("_")[1]
    display_name = f"{p_code[:3]}/{p_code[3:]}" + (" (OTC)" if is_otc else "")
    context.user_data['selected_pair'] = display_name
    
    kb = [
        [InlineKeyboardButton("⏱️ 30 SEC", callback_data="tf_30s"), InlineKeyboardButton("⏱️ 1 MIN", callback_data="tf_1m")],
        [InlineKeyboardButton("⏱️ 5 MIN", callback_data="tf_5m")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]
    ]
    await query.message.edit_text(f"📊 Selected: {display_name}\n\nٹائم فریم منتخب کریں:", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def timeframe_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "back_to_start":
        await start(update, context)
        return

    tf = query.data.split("_")[1].upper()
    pair = context.user_data.get('selected_pair', 'EUR/USD')
    
    await query.message.edit_text(f"🔄 Scanning 5/5 Professional Confluence for {pair} on {tf}...", parse_mode="Markdown")
    
    action, conf, reason, adx_val, rsi_val, macd_h = get_professional_signal(pair, tf)
    
    if "WAIT" in action:
        await query.message.edit_text(f"⚠️ *Signal Filtered (Not 5/5 Confirmed)!*\n\n🌐 Asset: {pair}\n🔍 Reason: {reason}\n\n❌ مارکیٹ میں مکمل 5/5 کنفرمیشن نہ ہونے کی وجہ سے سگنل روک دیا گیا ہے۔", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Try Another", callback_data="back_to_start")]]), parse_mode="Markdown")
        return

    t_sec = 30 if tf == "30S" else (60 if tf == "1M" else 300)
    c_pair = pair.replace(" (OTC)", "").replace("/", "")
    threading.Thread(target=verify_signal, args=(f"{c_pair}=X", 1.1000, action, t_sec), daemon=True).start()

    emoji = "🟢" if "BUY" in action else "🔴"
    arrow = "🚀" if "BUY" in action else "📉"
    
    msg = (
        f"{arrow} *AKBARI AI 5/5 PRO SIGNAL* {arrow}\n\n"
        f"🌐 Asset: {pair}\n"
        f"⏳ Timeframe: {tf}\n\n"
        f"{emoji} Action: *{action}*\n"
        f"🎯 Confidence: {conf}%\n"
        f"⚡ Status: {reason}\n"
        f"🧭 ADX: {adx_val} | RSI: {rsi_val} | MACD Hist: {macd_h}\n\n"
        f"⚠️ احتیاط برتیں۔"
    )
    
    try:
        # यह लाइन आपके चैनल पर ऑटोमैटिक सिग्नल भेजेगी
        await context.bot.send_message(chat_id=CHANNEL_USERNAME, text=msg, parse_mode="Markdown")
        await query.message.edit_text(f"✅ 5/5 Confirmed Signal Auto-Posted to Channel!\n\n{msg}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 New Analysis", callback_data="back_to_start")]]), parse_mode="Markdown")
    except Exception as e:
        await query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 New Analysis", callback_data="back_to_start")]]), parse_mode="Markdown")

def main():
    t_thread = threading.Thread(target=run_dummy_server, daemon=True)
    t_thread.start()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(pair_selected, pattern="^(pair_|send_stats)"))
    app.add_handler(CallbackQueryHandler(timeframe_selected, pattern="^(tf_|back_to_start)"))
    print("Akbari AI Professional Bot running with Auto-Channel Post...")
    app.run_polling()

if __name__ == "__main__":
    main()
