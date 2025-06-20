from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_mapping(
        SECRET_KEY="yoursecretkey",  # Replace this with a secure key
        SQLALCHEMY_DATABASE_URI="sqlite:///site.db",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'main.login'

    with app.app_context():
        from . import routes, models
        from .routes import main
        app.register_blueprint(main)
        db.create_all()

    return app
