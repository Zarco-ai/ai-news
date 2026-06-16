import sys
import os
from dotenv import load_dotenv
import logging


def load_configurations(app):
    load_dotenv()
    app.config["ACCESS_TOKEN"] = os.getenv("ACCESS_TOKEN")
    app.config["YOUR_PHONE_NUMBER"] = os.getenv("YOUR_PHONE_NUMBER")
    app.config["APP_ID"] = os.getenv("APP_ID")
    app.config["APP_SECRET"] = os.getenv("APP_SECRET")
    app.config["RECIPIENT_WAID"] = os.getenv("RECIPIENT_WAID")
    app.config["VERSION"] = os.getenv("VERSION")
    app.config["PHONE_NUMBER_ID"] = os.getenv("PHONE_NUMBER_ID")
    app.config["VERIFY_TOKEN"] = os.getenv("VERIFY_TOKEN")

    # Model + budget controls (see render.yaml / .env for production values).
    app.config["OPENAI_MODEL"] = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    # Hard global cap, kept under the $5 of credit to leave margin.
    app.config["GLOBAL_SPEND_CAP_USD"] = float(
        os.getenv("GLOBAL_SPEND_CAP_USD", "4.50")
    )
    # Max OpenAI-answered messages per user per UTC day.
    app.config["PER_USER_DAILY_LIMIT"] = int(os.getenv("PER_USER_DAILY_LIMIT", "20"))
    # Price per 1M tokens (USD). Defaults approximate gpt-4o-mini; verify current
    # pricing and override via env if you change models.
    app.config["INPUT_COST_PER_1M"] = float(os.getenv("INPUT_COST_PER_1M", "0.15"))
    app.config["OUTPUT_COST_PER_1M"] = float(os.getenv("OUTPUT_COST_PER_1M", "0.60"))


def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )