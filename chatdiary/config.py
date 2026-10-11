from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "chat.db"
DAYS_DIR = DATA_DIR / "days"
RAW_DIR = DATA_DIR / "raw"  # 抓取到的原始对话 JSON
PROFILE_DIR = ROOT / "profile"  # 抓取专用 Chrome 的登录状态
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# 生活日：前一天 DAY_START_HOUR 点到当天 DAY_START_HOUR 点（按 TIMEZONE 计）
TIMEZONE = "America/Denver"
DAY_START_HOUR = 4
