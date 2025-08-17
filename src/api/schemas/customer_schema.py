from marshmallow import (
    Schema, fields, validate,
    ValidationError, validates_schema, pre_load, EXCLUDE
)

# Reglas reutilizables
NAME_LEN = validate.Length(min=3, max=255)
EMAIL_LEN = validate.Length(max=255)
PASSWORD_LEN = validate.Length(min=8, max=128)  # permitir passphrases largas
# Si quieres complejidad mínima (letra + número), descomenta:
# PASSWORD_COMPLEXITY = validate.Regexp(
#     r'^(?=.*[A-Za-z])(?=.*\d).+$',
#     error='La contraseña debe incluir al menos una letra y un número'
# )

class BaseCustomerSchema(Schema):
    """Normaliza y valida campos comunes."""
    class Meta:
        unknown = EXCLUDE   # Ignora campos no definidos en el esquema
        ordered = True

    @pre_load
    def normalize(self, data, **kwargs):
        if not isinstance(data, dict):
            return data
        if isinstance(data.get("email"), str):
            data["email"] = data["email"].strip().lower()
        if isinstance(data.get("name"), str):
            # quita espacios extra internos
            data["name"] = " ".join(data["name"].split())
        return data


class CustomerCreateSchema(BaseCustomerSchema):
    name = fields.Str(
        required=True, validate=NAME_LEN,
        error_messages={"required": "El nombre es obligatorio", "null": "El nombre no puede ser nulo"}
    )
    email = fields.Email(
        required=True, validate=EMAIL_LEN,
        error_messages={"required": "El email es obligatorio", "null": "El email no puede ser nulo"}
    )
    password = fields.Str(
        required=True, load_only=True, validate=PASSWORD_LEN,
        # validate=[PASSWORD_LEN, PASSWORD_COMPLEXITY],  # si activas complejidad
        error_messages={"required": "La contraseña es obligatoria", "null": "La contraseña no puede ser nula"}
    )
    marketing_allowed = fields.Bool(missing=False)
    # profile_photo_path: manejar con upload aparte


class CustomerUpdateSchema(BaseCustomerSchema):
    """Para PUT/PATCH. Todos opcionales, pero debe venir al menos uno."""
    name = fields.Str(validate=NAME_LEN)
    email = fields.Email(validate=EMAIL_LEN)
    password = fields.Str(load_only=True, validate=PASSWORD_LEN)
    marketing_allowed = fields.Bool()

    @validates_schema
    def at_least_one_field(self, data, **kwargs):
        if not data:
            raise ValidationError("Debes enviar al menos un campo para actualizar.")
