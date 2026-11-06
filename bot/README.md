# F 娱乐场 · 表情游戏机器人

由 @fpay_wallet_game_bot 调用 Telegram `sendDice` 发出官方动画表情（🎲🎯🏀⚽🎳🎰），点数由 Telegram 服务器决定，机器人按点数结算。玩的是点数，不涉及真钱。

## 启动
```bash
pip install -r requirements.txt
export BOT_TOKEN=从 BotFather 拿到的 token
export WEBAPP_URL=https://allenfxxku064-beep.github.io/fpay-bot/   # 小程序网址，可不设
python bot.py
```
点数存在同目录的 `fpay_points.db`（SQLite）。

## 部署
GitHub Pages 只能放网页，跑不了机器人。需要一台一直开着的机器：VPS，或 Railway、Render、Fly.io 这类平台。启动命令就是 `python bot.py`，并设置好 `BOT_TOKEN` 环境变量。

如果要在群里用：在 BotFather 里把机器人加进群，并给它发消息的权限。

## 指令
| 指令 | 说明 |
|---|---|
| `/dice 大 100` | 🎲 押 大/小/单/双 返还 ×1.95，押 1–6 点 ×5.8 |
| `/dart 50` | 🎯 正中红心 ×4，靠近红心 ×1.7 |
| `/basket 50` | 🏀 进球 ×2.35 |
| `/football 50` | ⚽ 进球 ×1.55 |
| `/bowling 50` | 🎳 全中 ×4，剩一瓶 ×1.7 |
| `/slot 50` | 🎰 7️⃣7️⃣7️⃣ ×20，任意三连 ×9，两个 7 ×1.5 |
| `/games` | 按钮菜单（每把 10 点）+ 打开小程序 |
| `/daily` `/points` `/top` `/help` | 每日 500 点 / 查点数 / 排行榜 / 玩法 |

倍数含本金，长期返还约 93%–98%。用户自己发或转发的表情不结算。
