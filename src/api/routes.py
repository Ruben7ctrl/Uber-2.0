"""
This module takes care of starting the API Server, Loading the DB and Adding the endpoints
"""
from flask import Flask, request, jsonify, url_for, Blueprint
from api.models import db, User
from api.utils import generate_sitemap, APIException
from flask_cors import CORS
from werkzeug.security import generate_password_hash

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