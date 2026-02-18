import os
from flask import Flask
from flask_cors import CORS

def create_app():
    app = Flask(__name__)
    app.config["SUPABASE_URL"] = os.getenv("SUPABASE_URL")
    app.config["SUPABASE_SERVICE_KEY"] = os.getenv("SUPABASE_SERVICE_KEY")
    app.config["SUPABASE_ANON_KEY"] = os.getenv("SUPABASE_ANON_KEY")
    app.config["JWT_SECRET"] = os.getenv("JWT_SECRET")
    app.config["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
    origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:4200").split(",") if o.strip()]
    CORS(app, origins=origins, supports_credentials=True)
    from . import auth, profiles, projects, proposals, interviews, messages
    app.register_blueprint(auth.bp, url_prefix="/api/auth")
    app.register_blueprint(profiles.bp, url_prefix="/api/profiles")
    app.register_blueprint(projects.bp, url_prefix="/api/projects")
    app.register_blueprint(proposals.bp, url_prefix="/api/proposals")
    app.register_blueprint(interviews.bp, url_prefix="/api/interviews")
    app.register_blueprint(messages.bp, url_prefix="/api/messages")
    return app
