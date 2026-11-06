"""
F 娱乐场 · Telegram 表情游戏机器人（@fpay_wallet_game_bot）

由机器人调用 sendDice 发出 Telegram 官方动画表情，点数由 Telegram 服务器决定，
机器人按点数结算。玩的是「点数」，和小程序一样不涉及真钱。

游戏：🎲 骰子  🎯 飞镖  🏀 篮球  ⚽ 足球  🎳 保龄球  🎰 老虎机

运行：
  pip install -r requirements.txt
  export BOT_TOKEN=123456:ABC...        # BotFather 给的 token
  export WEBAPP_URL=https://allenfxxku064-beep.github.io/fpay-bot/   # 可选
  python bot.py
"""
import asyncio
import datetime as dt
import logging
import os
import sqlite3
from zoneinfo import ZoneInfo

from telegram import (BotCommand, InlineKeyboardButton, InlineKeyboardMarkup,
                      Update, WebAppInfo)
from telegram.constants import ChatType, DiceEmoji
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

TOKEN = os.environ.get("BOT_TOKEN", "")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://allenfxxku064-beep.github.io/fpay-bot/")
DB_PATH = os.environ.get("DB_PATH", "fpay_points.db")
TZ = ZoneInfo("Asia/Taipei")

START_POINTS = 120      # 新用户初始点数
DAILY_POINTS = 500      # 每日领取
DEFAULT_BET = 10
MIN_BET, MAX_BET = 1, 5000
ANIM_WAIT = {"dice": 3.3, "dart": 3.0, "basket": 4.2, "football": 4.2, "bowling": 3.8, "slot": 2.3}

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
log = logging.getLogger("fpay")

# ---------------------------------------------------------------- 数据库
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.execute("""CREATE TABLE IF NOT EXISTS users(
  uid INTEGER PRIMARY KEY, name TEXT, points INTEGER NOT NULL, last_daily TEXT)""")
db.execute("""CREATE TABLE IF NOT EXISTS plays(
  id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, game TEXT, opt TEXT,
  bet INTEGER, value INTEGER, payout INTEGER, ts TEXT)""")
db.commit()


def user(uid: int, name: str) -> dict:
    row = db.execute("SELECT points,last_daily FROM users WHERE uid=?", (uid,)).fetchone()
    if row is None:
        db.execute("INSERT INTO users(uid,name,points) VALUES(?,?,?)", (uid, name, START_POINTS))
        db.commit()
        return {"points": START_POINTS, "last_daily": None}
    db.execute("UPDATE users SET name=? WHERE uid=?", (name, uid))
    return {"points": row[0], "last_daily": row[1]}


def add_points(uid: int, delta: int) -> int:
    db.execute("UPDATE users SET points=points+? WHERE uid=?", (delta, uid))
    db.commit()
    return db.execute("SELECT points FROM users WHERE uid=?", (uid,)).fetchone()[0]


def today() -> str:
    return dt.datetime.now(TZ).date().isoformat()


# ---------------------------------------------------------------- 规则与赔率
# 赔率都是「含本金的返还倍数」，长期返还约 93%–97%。
SLOT_SYM = ["BAR", "🍇", "🍋", "7️⃣"]


def slot_reels(v: int):
    v -= 1
    return [v % 4, (v // 4) % 4, (v // 16) % 4]


DICE_OPTS = {"大": "big", "小": "small", "单": "odd", "双": "even",
             "big": "big", "small": "small", "odd": "odd", "even": "even"}


def judge(game: str, opt: str, v: int):
    """返回 (返还倍数, 说明文字)"""
    if game == "dice":
        if opt in "123456" and len(opt) == 1:
            return (5.8, f"开 {v} 点，押中！") if v == int(opt) else (0, f"开 {v} 点，没押中 {opt} 点")
        hit = {"big": v >= 4, "small": v <= 3, "odd": v % 2 == 1, "even": v % 2 == 0}[opt]
        tag = ("大" if v >= 4 else "小") + ("单" if v % 2 else "双")
        return (1.95, f"开 {v} 点（{tag}），赢了！") if hit else (0, f"开 {v} 点（{tag}），这把没中")
    if game == "dart":
        if v == 6:
            return 4, "🎯 正中红心！"
        if v == 5:
            return 1.7, "离红心只差一点，小赚"
        return 0, "脱靶了" if v == 1 else "没中红心"
    if game == "basket":
        return (2.35, "🏀 空心入网！") if v >= 4 else (0, "打铁了")
    if game == "football":
        return (1.55, "⚽ 球进了！") if v >= 3 else (0, "被扑出去了")
    if game == "bowling":
        if v == 6:
            return 4, "🎳 全中 Strike！"
        if v == 5:
            return 1.7, "只剩一瓶，小赚"
        return 0, "洗沟了" if v == 1 else "没打全中"
    if game == "slot":
        r = slot_reels(v)
        face = " ".join(SLOT_SYM[i] for i in r)
        if v == 64:
            return 20, f"{face}\n💰 发发发！横财到手！"
        if r[0] == r[1] == r[2]:
            return 9, f"{face}\n🧧 三连发财！"
        if r.count(3) == 2:
            return 1.5, f"{face}\n双 7 小赚一笔"
        return 0, f"{face}\n差一点就发财，下一把必发！"
    raise ValueError(game)


GAMES = {
    "dice": (DiceEmoji.DICE, "骰子"),
    "dart": (DiceEmoji.DARTS, "飞镖"),
    "basket": (DiceEmoji.BASKETBALL, "篮球"),
    "football": (DiceEmoji.FOOTBALL, "足球"),
    "bowling": (DiceEmoji.BOWLING, "保龄球"),
    "slot": (DiceEmoji.SLOT_MACHINE, "发财老虎机"),
}

RULES = (
    "<b>F 娱乐场 · 表情游戏</b>（点数玩法，无真钱）\n\n"
    "🎲 <code>/dice 大 100</code> — 押 大/小/单/双 赔 1.95；押 1–6 点赔 5.8\n"
    "🎯 <code>/dart 50</code> — 正中红心 ×4，靠近红心 ×1.7\n"
    "🏀 <code>/basket 50</code> — 进球 ×2.35\n"
    "⚽ <code>/football 50</code> — 进球 ×1.55\n"
    "🎳 <code>/bowling 50</code> — 全中 ×4，剩一瓶 ×1.7\n"
    "🎰 <code>/slot 50</code> — 7️⃣7️⃣7️⃣ ×20，任意三连 ×9，两个 7 ×1.5\n\n"
    "倍数含本金。不写金额默认 10 点。\n"
    "/points 查点数 · /daily 每日领 500 点 · /top 排行榜 · /games 游戏菜单\n"
    "结果由 Telegram 官方动画决定；自己发的 🎲 不算数。"
)

busy: set[int] = set()


def again_kb(game: str, opt: str, bet: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔁 再来一把", callback_data=f"p|{game}|{opt}|{bet}"),
        InlineKeyboardButton("✖2 加倍", callback_data=f"p|{game}|{opt}|{min(MAX_BET, bet * 2)}"),
    ]])


def menu_kb(private: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("🎲 大", callback_data="p|dice|big|10"),
         InlineKeyboardButton("🎲 小", callback_data="p|dice|small|10"),
         InlineKeyboardButton("🎰 发财", callback_data="p|slot|-|10")],
        [InlineKeyboardButton("🎯", callback_data="p|dart|-|10"),
         InlineKeyboardButton("🏀", callback_data="p|basket|-|10"),
         InlineKeyboardButton("⚽", callback_data="p|football|-|10"),
         InlineKeyboardButton("🎳", callback_data="p|bowling|-|10")],
        [InlineKeyboardButton("🎁 每日领 500 点", callback_data="daily")],
    ]
    if private:  # WebApp 按钮只能在私聊里用
        rows.append([InlineKeyboardButton("🎃 打开 F 娱乐场", web_app=WebAppInfo(url=WEBAPP_URL))])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------- 核心：一局
async def play(update: Update, ctx: ContextTypes.DEFAULT_TYPE, game: str, opt: str, bet: int):
    u = update.effective_user
    chat_id = update.effective_chat.id
    reply = update.effective_message
    name = u.full_name or str(u.id)
    info = user(u.id, name)

    async def say(text, **kw):
        if update.callback_query:
            return await ctx.bot.send_message(chat_id, text, parse_mode="HTML", **kw)
        return await reply.reply_text(text, parse_mode="HTML", **kw)

    if u.id in busy:
        return await say("上一把还在开奖，稍等一下～")
    if not (MIN_BET <= bet <= MAX_BET):
        return await say(f"下注范围 {MIN_BET}–{MAX_BET} 点")
    if info["points"] < bet:
        return await say(f"点数不足：你有 {info['points']} 点，这把要 {bet} 点。/daily 可领每日点数")

    busy.add(u.id)
    try:
        add_points(u.id, -bet)
        emoji, title = GAMES[game]
        msg = await ctx.bot.send_dice(chat_id, emoji=emoji,
                                      reply_to_message_id=None if update.callback_query else reply.message_id)
        v = msg.dice.value
        mult, text = judge(game, opt, v)
        payout = round(bet * mult)
        await asyncio.sleep(ANIM_WAIT[game])       # 等动画播完再公布
        bal = add_points(u.id, payout)
        db.execute("INSERT INTO plays(uid,game,opt,bet,value,payout,ts) VALUES(?,?,?,?,?,?,?)",
                   (u.id, game, opt, bet, v, payout, dt.datetime.now(TZ).isoformat()))
        db.commit()
        net = payout - bet
        line = f"赢 <b>+{net}</b> 点 🎉" if net > 0 else ("保本" if net == 0 else f"输 {-net} 点")
        await ctx.bot.send_message(
            chat_id,
            f"<b>{title}</b> · {name} 下注 {bet}{'（' + opt_label(opt) + '）' if game == 'dice' else ''}\n"
            f"{text}\n{line} · 余额 <b>{bal}</b> 点",
            parse_mode="HTML", reply_to_message_id=msg.message_id,
            reply_markup=again_kb(game, opt, bet))
    finally:
        busy.discard(u.id)


def opt_label(opt: str) -> str:
    return {"big": "大", "small": "小", "odd": "单", "even": "双"}.get(opt, f"{opt} 点")


def parse_bet(s: str | None) -> int | None:
    if s is None:
        return DEFAULT_BET
    try:
        return int(s)
    except ValueError:
        return None


# ---------------------------------------------------------------- 指令
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    info = user(u.id, u.full_name)
    private = update.effective_chat.type == ChatType.PRIVATE
    await update.message.reply_text(
        f"欢迎来到 <b>F 娱乐场</b>，{u.first_name}！你现在有 <b>{info['points']}</b> 点。\n\n" + RULES,
        parse_mode="HTML", reply_markup=menu_kb(private))


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(RULES, parse_mode="HTML")


async def cmd_games(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    private = update.effective_chat.type == ChatType.PRIVATE
    await update.message.reply_text("选一个玩（每把 10 点，指令可自定金额）：",
                                    reply_markup=menu_kb(private))


async def cmd_points(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    info = user(u.id, u.full_name)
    await update.message.reply_text(f"{u.first_name}，你有 <b>{info['points']}</b> 点", parse_mode="HTML")


async def do_daily(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    info = user(u.id, u.full_name)
    if info["last_daily"] == today():
        text = "今天已经领过了，明天再来 🎁"
    else:
        db.execute("UPDATE users SET last_daily=? WHERE uid=?", (today(), u.id))
        bal = add_points(u.id, DAILY_POINTS)
        text = f"🎁 领到 {DAILY_POINTS} 点！余额 <b>{bal}</b> 点"
    await ctx.bot.send_message(update.effective_chat.id, f"{u.first_name}：{text}", parse_mode="HTML")


async def cmd_top(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rows = db.execute("SELECT name,points FROM users ORDER BY points DESC LIMIT 10").fetchall()
    medal = ["🥇", "🥈", "🥉"] + [f"{i}." for i in range(4, 11)]
    text = "\n".join(f"{medal[i]} {n} — {p} 点" for i, (n, p) in enumerate(rows)) or "还没有人上榜"
    await update.message.reply_text("<b>发财排行榜</b>\n" + text, parse_mode="HTML")


def game_cmd(game: str):
    async def handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        args = ctx.args or []
        opt = "-"
        if game == "dice":
            first = args[0] if args else "大"
            if first in DICE_OPTS:
                opt = DICE_OPTS[first]
            elif first in list("123456"):
                opt = first
            else:
                return await update.message.reply_text("用法：/dice 大 100（大/小/单/双 或 1–6）")
            bet = parse_bet(args[1] if len(args) > 1 else None)
        else:
            bet = parse_bet(args[0] if args else None)
        if bet is None:
            return await update.message.reply_text("金额要写整数，例如 /slot 50")
        await play(update, ctx, game, opt, bet)
    return handler


async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "daily":
        return await do_daily(update, ctx)
    _, game, opt, bet = q.data.split("|")
    if game in GAMES:
        await play(update, ctx, game, opt, int(bet))


async def on_user_dice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # 用户自己发（或转发）的骰子不结算，防止挑好结果再发
    await update.message.reply_text("自己发的表情不算数哦，用 /dice /slot 等指令让机器人掷才结算 🎲")


async def post_init(app: Application):
    await app.bot.set_my_commands([
        BotCommand("games", "游戏菜单"), BotCommand("dice", "🎲 骰子 例：/dice 大 100"),
        BotCommand("slot", "🎰 发财老虎机"), BotCommand("dart", "🎯 飞镖"),
        BotCommand("basket", "🏀 篮球"), BotCommand("football", "⚽ 足球"),
        BotCommand("bowling", "🎳 保龄球"), BotCommand("daily", "每日领 500 点"),
        BotCommand("points", "查点数"), BotCommand("top", "排行榜"), BotCommand("help", "玩法说明"),
    ])


def main():
    if not TOKEN:
        raise SystemExit("请先设置环境变量 BOT_TOKEN")
    app = Application.builder().token(TOKEN).post_init(post_init).concurrent_updates(True).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("games", cmd_games))
    app.add_handler(CommandHandler("points", cmd_points))
    app.add_handler(CommandHandler("daily", do_daily))
    app.add_handler(CommandHandler("top", cmd_top))
    for g in GAMES:
        app.add_handler(CommandHandler(g, game_cmd(g)))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.Dice.ALL & ~filters.VIA_BOT, on_user_dice))
    log.info("F 娱乐场机器人启动")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
