from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.exc import IntegrityError
from marshmallow import ValidationError, EXCLUDE

from app.models2 import db, User
from app.schemas.user_schemas import UserSchema

account_bp = Blueprint("account", __name__, url_prefix="/api/account")

# Reuse one schema instance for (de)serialization
user_schema = UserSchema()


def _get_json_or_400():
    data = request.get_json(silent=True)
    if data is None:
        return None, (jsonify({"message": "No input data provided (expecting JSON body)"}), 400)
    return data, None


def _normalize_email(email: str | None) -> str | None:
    return email.lower().strip() if isinstance(email, str) else email


@account_bp.route("/edit", methods=["PUT", "PATCH"])
@jwt_required()
def edit_account():
    """Update current user's editable fields (name, email).
    Accepts PUT/PATCH with JSON. Only updates provided fields.
    - Validates using UserSchema (only name/email), partial load.
    - Normalizes email to lowercase.
    - Prevents duplicate emails.
    """
    current_user_id = get_jwt_identity()
    user = User.query.get_or_404(current_user_id)

    data, err = _get_json_or_400()
    if err:
        return err

    # Consider only allowed fields
    payload = {k: v for k, v in data.items() if k in {"name", "email"}}
    if not payload:
        return jsonify({"message": "No editable fields provided"}), 400

    # Validate with schema (only these fields), allow partial
    try:
        validated = user_schema.load(payload, partial=True, unknown=EXCLUDE)
    except ValidationError as ve:
        return jsonify({"message": "Validation failed", "errors": ve.messages}), 422

    # Apply updates
    if "name" in validated:
        user.name = validated["name"]

    if "email" in validated:
        new_email = _normalize_email(validated["email"])
        if new_email != user.email:
            # Ensure email uniqueness
            exists = (
                User.query.filter(User.email == new_email, User.id != user.id).first()
            )
            if exists:
                return jsonify({"message": "Email already in use"}), 400
            user.email = new_email

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        # In case there's a unique constraint at DB level
        return jsonify({"message": "Email already in use"}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": "Error updating user"}), 500

    return jsonify({
        "user": user_schema.dump(user),
        "message": "Success",
    }), 200


@account_bp.route("/<int:user_id>", methods=["GET"])
@jwt_required()
def show_user(user_id: int):
    """Show a user's public profile. Restrict to self unless admin (if roles exist)."""
    requester_id = get_jwt_identity()

    # If the requester is not the same user, check for admin role when available
    if requester_id != user_id:
        requester = User.query.get_or_404(requester_id)
        has_role = getattr(requester, "has_role", None)
        if not callable(has_role) or not requester.has_role(["admin"]):
            return jsonify({"message": "Forbidden"}), 403

    user = User.query.get_or_404(user_id)
    return jsonify(user_schema.dump(user)), 200


@account_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    """Convenience endpoint to get the current authenticated user."""
    current_user_id = get_jwt_identity()
    user = User.query.get_or_404(current_user_id)
    return jsonify(user_schema.dump(user)), 200
