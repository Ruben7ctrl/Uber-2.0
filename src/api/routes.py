"""
This module takes care of starting the API Server, Loading the DB and Adding the endpoints
"""
from flask import Flask, request, jsonify, url_for, Blueprint
from api.models import db, User, Admin, Driver, Customer, RideStatus, RideExtra, Ride, City, DriverDocument, UserImage, Vehicle, VehicleBrand, VehicleCategory, VehicleColor, VehicleModel, Role, Permission, Setting, Transaction
from api.utils import generate_sitemap, APIException
from flask_cors import CORS
from sqlalchemy import select, or_
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
from api.mail.mailer import send_mail
from flask import current_app
from datetime import datetime
import os
import stripe

api = Blueprint('api', __name__)

# Allow CORS requests to this API
CORS(api)


@api.route('/hello', methods=['POST', 'GET'])
def handle_hello():

    response_body = {
        "message": "Hello! I'm a message that came from the backend, check the network tab on the google inspector and you will see the GET request"
    }

    return jsonify(response_body), 200

# users_bp = Blueprint("users_bp", __name__, url_prefix="/users")


@api.route("/users", methods=["GET"])
def list_users():
    role = request.args.get("role")
    page = request.args.get("page", type=int, default=1)
    per_page = request.args.get("per_page", type=int, default=10)

    query = User.query
    if role:
        query = query.filter_by(role=role)

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    users = pagination.items

    return jsonify({
        "users": [user.serialize() for user in users],
        "total": pagination.total,
        "page": pagination.page,
        "pages": pagination.pages
    })


@api.route("/users", methods=["POST"])
def create_user():
    data = request.get_json()
    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    role = data.get("role", "client")
    is_active = data.get("is_active", True)

    if not name or not email or not password:
        return jsonify({"error": "Missing required fields"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already exists"}), 400

    hashed_password = generate_password_hash(password)
    user = User(
        name=name,
        email=email,
        password=hashed_password,
        role=role,
        is_active=is_active
    )
    db.session.add(user)
    db.session.commit()

    return jsonify(user.serialize()), 201


@api.route("/user/<int:user_id>", methods=["GET"])
def get_user(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify(user.serialize())


@api.route("/user/<int:user_id>/role", methods=["PUT"])
def change_role(user_id):
    data = request.get_json()
    new_role = data.get("role")

    user = User.query.get_or_404(user_id)
    user.role = new_role
    db.session.commit()

    return jsonify({"message": f"Role updated to {new_role}"}), 200


@api.route("/user/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": f"User {user_id} deleted"}), 200


@api.route('/signup', methods=['POST'])
def signup():
    try:
        data = request.get_json()

        if not data["email"] or not data["password"]:
            raise Exception({"error": "Missing Data"})

        stmt = select(Users).where(Users.email == data["email"])
        existing_user = db.session.execute(stmt).scalar_one_or_none()

        if existing_user:
            raise Exception({"error": "Existing email, try to SignIn"})

        hashed_password = generate_password_hash(data["password"])

        new_user = Users(
            email=data["email"],
            password=hashed_password,
            username=data.get("username"),
            firstname=data.get("firstname", None),
            lastname=data.get("lastname", None),
            dateofbirth=data.get("dateofbirth", None),
            phone=data.get("phone", None),
            avatar_image=data.get("avatar_image", None),
            is_active=True
        )

        db.session.add(new_user)
        db.session.commit()
        return jsonify(new_user.serialize()), 201

    except Exception as e:
        print(e)

        db.session.rollback()
        return jsonify({"error": "somthing went wrong"}), 400


@api.route('/signin', methods=['POST'])
def signin():
    try:
        data = request.get_json()

        if not data.get("password") or not data.get("identify"):
            return jsonify({"error": "missing data"})

        stmt = select(Users).where(
            or_(Users.email == data["identify"], Users.username == data["identify"]))
        user = db.session.execute(stmt).scalar_one_or_none()

        if not user:
            raise Exception({"error": "Email/Username not found"})

        if not check_password_hash(user.password, data["password"]):
            return jsonify({"success": False, "error": "wrong email/password"})

        token = create_access_token(identity=str(user.id))

        return jsonify({"success": True, "token": token, "msg": "SignIn OK", "user": user.serialize()}), 201

    except Exception as e:
        print(e)

        db.session.rollback()
        return jsonify({"error": "somthing went wrong"}), 400


@api.route('/mailer/<address>', methods=['POST'])
def handle_mail(address):
    return send_mail(address)


@api.route('/token', methods=['GET'])
@jwt_required()
def check_jwt():
    user_id = get_jwt_identity()
    users = Users.query.get(user_id)

    if users:
        return jsonify({"success": True, "user": users.serialize()}), 200
    return jsonify({"success": False, "msg": "Bad token"}), 401


@api.route('/forgot-password', methods=['POST'])
def forgot_password():

    try:
        data = request.get_json()

        user = db.session.query(Users).filter_by(email=data["email"]).first()
        if not user:
            return jsonify({"success": False, "error": "Email no encontrado"}), 404

        token = create_access_token(identity=str(user.id))
        result = send_mail(data["email"], token)
        print(result)

        return jsonify({"success": True, "token": token, "email": data["email"]}), 200

    except Exception as e:
        print("Error enviando correo:", str(e))
        return jsonify({"success": False, 'msg': 'Error enviando email', 'error': str(e)}), 500


@api.route('/reset-password', methods=['PUT'])
@jwt_required()
def reset_password():
    try:
        data = request.get_json()
        user_id = get_jwt_identity()
        print("Datos recibidos", data)
        print("password:", data.get("password"))

        if not data or not data.get("password"):
            return jsonify({"success": False, "msg": "PAssword is required"}), 422

        user = Users.query.get(user_id)
        print("user_id", user_id)

        if not user:
            return jsonify({"success": False, "msg": "User not found"}), 404

        hashed_password = generate_password_hash(data["password"])
        user.password = hashed_password
        db.session.commit()

        return jsonify({"success": True, "msg": "Contraseña actualizada"}), 200
    except Exception as e:
        db.session.rollback()
        print("Error al modificar password: {str(e)}")
        return jsonify({"success": False, "msg": f"Error al modificar password: {str(e)}"})