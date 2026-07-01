import os

ONBID_SERVICE_KEY = os.environ.get("ONBID_SERVICE_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

ENABLE_COURT_SCRAPING = os.environ.get("ENABLE_COURT_SCRAPING", "false").lower() == "true"

_DEFAULT_PROFILES_PATH = os.path.join(os.path.dirname(__file__), "data", "profiles.json")
AUCTION_PROFILES_PATH = os.environ.get("AUCTION_PROFILES_PATH", _DEFAULT_PROFILES_PATH)
