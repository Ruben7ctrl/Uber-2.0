from flask import (
    Blueprint, request, jsonify, render_template, redirect, url_for, flash, current_app
)
from werkzeug.security import generate_password_hash, check_password_hash
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from flask_mail import Message
from flask_login import current_user
from functools import wraps
from jwt import ExpiredSignatureError, InvalidTokenError
from marshmallow import ValidationError
import secrets

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from api.models2 import db, User
from api.utils.jwt_handler import create_token, decode_token
from api.schemas.auth_schemas import (
    LoginSchema, RegisterSchema, GoogleLoginSchema, PasswordResetSchema
)
from api.utils.token_utils import verify_reset_token  # si ya existe en tu proyecto
from api import mail

# Helpers opcionales (si tu proyecto los tiene)
try:
    from api.utils.email import send_reset_password_email  # helper propio, si existe
except Exception:
    send_reset_password_email = None

try:
    from api.utils.token_utils import generate_reset_token  # si ya existe
except Exception:
    generate_reset_token = None

# --- Blueprint
auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# --- Schemas
login_schema = LoginSchema()
register_schema = RegisterSchema()
google_login_schema = GoogleLoginSchema()
password_reset_schema = PasswordResetSchema()

# --- Helpers comunes

def _get_bearer_token() -> str | None:
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header.split(" ", 1)[1].strip() or None


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _get_bearer_token()
        if not token:
            return jsonify({"message": "Token is missing"}), 401
        try:
            data = decode_token(token)
            email = data.get("email")
            if not email:
                return jsonify({"message": "Invalid token payload"}), 401
            current_user_obj = User.query.filter_by(email=email.lower()).first()
            if not current_user_obj:
                return jsonify({"message": "User not found"}), 401
        except ExpiredSignatureError:
            return jsonify({"message": "Token expired"}), 401
        except InvalidTokenError:
            return jsonify({"message": "Invalid token"}), 401
        except Exception:
            return jsonify({"message": "Token error"}), 401
        return f(current_user_obj, *args, **kwargs)
    return decorated

# --- Token helpers (itsdangerous) para verificación de email y reset

def _get_serializer(salt: str) -> URLSafeTimedSerializer:
    secret_key = current_app.config.get("SECRET_KEY")
    return URLSafeTimedSerializer(secret_key, salt=salt)

EMAIL_VERIFY_SALT = "email-verify"
RESET_PWD_SALT = "password-reset"

def create_email_verification_token(user_id: int) -> str:
    s = _get_serializer(EMAIL_VERIFY_SALT)
    return s.dumps({"uid": user_id})

def verify_email_verification_token(token: str, max_age: int = 60 * 60 * 24) -> User | None:
    s = _get_serializer(EMAIL_VERIFY_SALT)
    try:
        data = s.loads(token, max_age=max_age)
        return User.query.get(data.get("uid"))
    except (BadSignature, SignatureExpired):
        return None

def create_password_reset_token(user_id: int) -> str:
    if callable(generate_reset_token):
        return generate_reset_token(user_id)
    s = _get_serializer(RESET_PWD_SALT)
    return s.dumps({"uid": user_id})

def verify_password_reset_token_local(token: str, max_age: int = 60 * 60) -> User | None:
    s = _get_serializer(RESET_PWD_SALT)
    try:
        data = s.loads(token, max_age=max_age)
        return User.query.get(data.get("uid"))
    except (BadSignature, SignatureExpired):
        return None

# --- Email utils

def send_verification_email(user: User) -> None:
    token = create_email_verification_token(user.id)
    verify_url = url_for("auth.verify_email", token=token, _external=True)

    subject = "Verify your email"
    body = (
        f"Hola {user.name},\n\n"
        f"Gracias por registrarte. Verifica tu email haciendo clic en este enlace:\n{verify_url}\n\n"
        "Si no te registraste, ignora este mensaje."
    )

    msg = Message(subject, recipients=[user.email])
    msg.body = body
    mail.send(msg)

# --- Rutas

@auth_bp.route("/login", methods=["POST"])
def login():
    json_data = request.get_json(silent=True) or {}
    try:
        data = login_schema.load(json_data)
    except ValidationError as err:
        return jsonify({"message": "Validation failed", "errors": err.messages}), 422

    email = data["email"].lower()
    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password, data["password"]):
        return jsonify({"message": "Unauthorized"}), 401

    token = create_token(user.email)
    return jsonify({
        "token": token,
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": getattr(user, "get_primary_role", lambda: None)()
        },
        "message": "Login successful"
    }), 200


@auth_bp.route("/register", methods=["POST"])
def register():
    json_data = request.get_json(silent=True) or {}
    try:
        data = register_schema.load(json_data)
    except ValidationError as err:
        return jsonify({"message": "Validation failed", "errors": err.messages}), 422

    email = data["email"].lower()
    if User.query.filter_by(email=email).first():
        return jsonify({"message": "Email already registered"}), 400

    hashed_password = generate_password_hash(data["password"])
    new_user = User(
        name=data["name"],
        email=email,
        password=hashed_password,
        marketing_allowed=data.get("marketing_allowed", False)
    )
    try:
        db.session.add(new_user)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"message": "Could not create user"}), 500

    # Asignar rol por defecto si existe el método
    if callable(getattr(new_user, "assign_role", None)):
        try:
            new_user.assign_role("cliente")
            db.session.commit()
        except Exception:
            db.session.rollback()

    # Enviar verificación (best-effort)
    try:
        send_verification_email(new_user)
    except Exception:
        pass

    token = create_token(new_user.email)
    return jsonify({
        "token": token,
        "user": {
            "id": new_user.id,
            "name": new_user.name,
            "email": new_user.email,
            "role": getattr(new_user, "get_primary_role", lambda: None)()
        },
        "message": "User registered successfully"
    }), 201


@auth_bp.route("/login_google", methods=["POST"])
def login_google():
    json_data = request.get_json(silent=True) or {}
    try:
        data = google_login_schema.load(json_data)
    except ValidationError as err:
        return jsonify({"message": "Validation failed", "errors": err.messages}), 422

    credential = data.get("credential")
    try:
        google_client_id = current_app.config.get("GOOGLE_CLIENT_ID")
        if not google_client_id:
            return jsonify({"message": "Server misconfigured: GOOGLE_CLIENT_ID missing"}), 500

        idinfo = id_token.verify_oauth2_token(
            credential, google_requests.Request(), google_client_id
        )

        email = (idinfo.get("email") or "").lower()
        name = idinfo.get("given_name") or idinfo.get("name") or "Usuario"
        if not email:
            return jsonify({"message": "Invalid token: email missing"}), 401

        user = User.query.filter_by(email=email).first()
        if not user:
            random_password = secrets.token_urlsafe(16)
            user = User(
                name=name,
                email=email,
                password=generate_password_hash(random_password),
                marketing_allowed=data.get("marketing_allowed", False)
            )
            try:
                db.session.add(user)
                db.session.commit()
            except Exception:
                db.session.rollback()
                return jsonify({"message": "Could not create user"}), 500

        if callable(getattr(user, "assign_role", None)):
            try:
                user.assign_role("cliente")
                db.session.commit()
            except Exception:
                db.session.rollback()

        token = create_token(user.email)
        return jsonify({
            "token": token,
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "role": getattr(user, "get_primary_role", lambda: None)()
            },
            "message": "Success"
        }), 200

    except ValueError:
        return jsonify({"message": "Invalid token"}), 401


@auth_bp.route("/profile", methods=["GET"])
@token_required
def profile(current_user_obj: User):
    return jsonify({
        "id": current_user_obj.id,
        "name": current_user_obj.name,
        "email": current_user_obj.email,
        "role": getattr(current_user_obj, "get_primary_role", lambda: None)(),
    })


@auth_bp.route("/check_token", methods=["GET"])
@token_required
def check_token(current_user_obj: User):
    return jsonify({
        "message": "Token válido",
        "user": {"id": current_user_obj.id, "role": getattr(current_user_obj, "get_primary_role", lambda: None)()},
        "status": "ok"
    }), 200


@auth_bp.route('/password/reset/<token>', methods=['GET'])
def show_reset_form(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    user = verify_reset_token(token) if callable(verify_reset_token) else verify_password_reset_token_local(token)
    if not user:
        flash('El token de reseteo no es válido o ha expirado.', 'danger')
        return redirect(url_for('auth.request_password_reset'))

    return render_template('auth/password_reset_form.html', token=token, email=user.email)


@auth_bp.route("/password/reset", methods=["POST"])
def reset_password():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    payload = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    try:
        data = password_reset_schema.load(payload)
    except ValidationError as err:
        return jsonify({"message": "Validation failed", "errors": err.messages}), 422

    token = data.get("token")
    password = data.get("password")

    user = verify_reset_token(token) if callable(verify_reset_token) else verify_password_reset_token_local(token)
    if not user:
        return jsonify({"error": "Token inválido o expirado"}), 400

    try:
        user.password = generate_password_hash(password)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "No se pudo actualizar la contraseña"}), 500

    if not callable(getattr(user, "has_role", None)) or not user.has_role(["editor", "admin"]):
        return redirect("/password/reset/complete")

    return redirect(url_for("admin.dashboard"))

# (1) NUEVO: Solicitar reset de contraseña (envía email con link)
@auth_bp.route("/password/request", methods=["POST"])
def request_password_reset():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").lower().strip()

    # Respuesta genérica SIEMPRE para evitar enumeración
    generic_msg = {"message": "Si el email existe, enviaremos instrucciones para restablecer la contraseña."}
    if not email:
        return jsonify(generic_msg), 200

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify(generic_msg), 200

    try:
        token = create_password_reset_token(user.id)
        reset_url = url_for("auth.show_reset_form", token=token, _external=True)

        if callable(send_reset_password_email):
            send_reset_password_email(user, reset_url)
        else:
            msg = Message("Restablecer contraseña", recipients=[user.email])
            msg.body = (
                f"Hola {user.name},\n\n"
                f"Para restablecer tu contraseña, haz clic en:\n{reset_url}\n\n"
                "Si no solicitaste este cambio, ignora este mensaje."
            )
            mail.send(msg)
    except Exception:
        # No filtramos el error (evita enumeración)
        return jsonify(generic_msg), 200

    return jsonify(generic_msg), 200

# (2) NUEVO: Verificación de email
@auth_bp.route("/verify", methods=["GET"])
def verify_email():
    token = request.args.get("token", type=str, default="")
    user = verify_email_verification_token(token)
    if not user:
        flash("El enlace de verificación no es válido o ha expirado.", "danger")
        return redirect(url_for("main.index"))

    try:
        updated = False
        if hasattr(user, "email_verified"):
            user.email_verified = True
            updated = True
        elif hasattr(user, "is_email_verified"):
            user.is_email_verified = True
            updated = True
        elif hasattr(user, "verified"):
            user.verified = True
            updated = True

        if updated:
            db.session.commit()

        flash("Email verificado correctamente. Ya puedes iniciar sesión.", "success")
        return redirect(url_for("main.index"))
    except Exception:
        db.session.rollback()
        flash("No se pudo completar la verificación.", "danger")
        return redirect(url_for("main.index"))
