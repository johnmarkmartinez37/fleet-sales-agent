from flask import Flask
from config import DEBUG


def create_app():
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.config["DEBUG"] = DEBUG
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

    from app.routes import bp
    app.register_blueprint(bp)

    return app