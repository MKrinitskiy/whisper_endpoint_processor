import yaml
import dotenv
from pathlib import Path

config_dir = Path(__file__).parent.parent.resolve() / "config"

# load yaml config
with open(config_dir / "config.yml", 'r') as f:
    config_yaml = yaml.safe_load(f)

# load .env config
config_env = dotenv.dotenv_values(config_dir / "config.env")

# config parameters
allowed_telegram_usernames = config_yaml["allowed_telegram_usernames"]

# transcription_langs
with open(config_dir / "transcription_languages.yml", 'r') as f:
    transcription_langs = yaml.safe_load(f)
