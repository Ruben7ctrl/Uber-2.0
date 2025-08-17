from marshmallow import (
    Schema, fields, validate, ValidationError,
    validates_schema, pre_load, EXCLUDE
)

# --- Reglas reutilizables
NAME_LEN = validate.Length(min=3, max=255)
EMAIL_LEN = validate.Length(max=255)
PWD_MIN, PWD_MAX = 8, 16  # mantengo tu rango original
VEHICLE_ID_RANGE = validate.Range(min=1, error="vehicle_id debe ser un entero positivo")


def validate_password(pwd: str):
    if not isinstance(pwd, str):
        raise ValidationError("La contraseña es inválida.")
    if not (PWD_MIN <= len(pwd) <= PWD_MAX):
        raise ValidationError(f"La contraseña debe tener entre {PWD_MIN} y {PWD_MAX} caracteres.")
    # Si quieres complejidad mínima (letra+número), descomenta:
    # import re
    # if not re.search(r"[A-Za-z]", pwd) or not re.search(r"\d", pwd):
    #     raise ValidationError("La contraseña debe incluir al menos una letra y un número.")


class BaseDriverSchema(Schema):
    """Normaliza y valida campos comunes para Driver."""
    class Meta:
        unknown = EXCLUDE
        ordered = True

    @pre_load
    def normalize(self, data, **kwargs):
        if not isinstance(data, dict):
            return data
        # email en minúsculas y sin espacios
        email = data.get("email")
        if isinstance(email, str):
            data["email"] = email.strip().lower()
        # name sin espacios dobles
        name = data.get("name")
        if isinstance(name, str):
            data["name"] = " ".join(name.split())
        return data


class DriverCreateSchema(BaseDriverSchema):
    name = fields.Str(
        required=True, validate=NAME_LEN,
        error_messages={"required": "El nombre es obligatorio", "null": "El nombre no puede ser nulo"},
    )
    email = fields.Email(
        required=True, validate=EMAIL_LEN,
        error_messages={"required": "El email es obligatorio", "null": "El email no puede ser nulo"},
    )
    password = fields.Str(
        required=True, load_only=True, validate=validate_password,
        error_messages={"required": "La contraseña es obligatoria", "null": "La contraseña no puede ser nula"},
    )
    vehicle_id = fields.Int(required=True, validate=VEHICLE_ID_RANGE)
    # Si guardas URL remota, usa fields.Url; si es ruta local, deja Str
    profile_photo_path = fields.Str(required=False, allow_none=True, validate=validate.Length(max=512))


class DriverUpdateSchema(BaseDriverSchema):
    """PUT/PATCH: todos opcionales, pero debe venir al menos un campo."""
    name = fields.Str(validate=NAME_LEN)
    email = fields.Email(validate=EMAIL_LEN)
    password = fields.Str(load_only=True, validate=validate_password)
    vehicle_id = fields.Int(validate=VEHICLE_ID_RANGE)
    profile_photo_path = fields.Str(allow_none=True, validate=validate.Length(max=512))

    @validates_schema
    def at_least_one_field(self, data, **kwargs):
        if not data:
            raise ValidationError("Debes enviar al menos un campo para actualizar.")
