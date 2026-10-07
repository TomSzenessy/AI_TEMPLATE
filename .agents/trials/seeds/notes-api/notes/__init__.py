"""Team notes API: a small Flask service our team uses to keep shared notes."""

from flask import Flask

from .db import init_db


def create_app(database: str = "notes.db") -> Flask:
    app = Flask(__name__)
    app.config["DATABASE"] = database
    init_db(database)
    from .routes import bp

    app.register_blueprint(bp)
    return app
