from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config.json"
LAST_NUMBER_PATH = ROOT_DIR / "last_number.json"
USED_POSTS_PATH = ROOT_DIR / "used_posts.json"
REDDIT_DAILY_PATH = ROOT_DIR / "reddit_daily.json"
OUTPUT_DIR = ROOT_DIR / "output"
CHATGPT_PROMPT_PATH = OUTPUT_DIR / "chatgpt_prompt.txt"
TRANSLATION_RESULT_PATH = OUTPUT_DIR / "translation_result.txt"
PENDING_POSTS_PATH = OUTPUT_DIR / "pending_posts.json"
LOG_DIR = ROOT_DIR / "logs"
