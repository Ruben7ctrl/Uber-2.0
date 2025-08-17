from marshmallow import (
    Schema, fields, validate, ValidationError,
    pre_load, validates_schema, EXCLUDE
)

# Reglas reutilizables
NAME_LEN = validate.Length(min=2, max=100)
DESC_LEN = validate.Length(max=1024)

class BasePermissionSchema(Schema):
    """Normaliza y valida campos comunes."""
    class Meta:
        unknown = EXCLUDE  # Ignora campos no definidos en el esquema
        ordered = True

    @pre_load
    def normalize(self, data, **kwargs):
        if not isinstance(data, dict):
            return data
        # Name: sin espacios sobrantes y colapsar espacios internos
        name = data.get("name")
        if isinstance(name, str):
            data["name"] = " ".join(name.split())
        # Description: recorta espacios extremos
        desc = data.get("description")
        if isinstance(desc, str):
            data["description"] = desc.strip()
        return data


class PermissionCreateSchema(BasePermissionSchema):
    name = fields.Str(
        required=True, validate=NAME_LEN,
        error_messages={
            "required": "El nombre es obligatorio",
            "null": "El nombre no puede ser nulo",
        },
    )
    description = fields.Str(required=False, allow_none=True, validate=DESC_LEN)


class PermissionUpdateSchema(BasePermissionSchema):
    name = fields.Str(validate=NAME_LEN)
    description = fields.Str(allow_none=True, validate=DESC_LEN)

    @validates_schema
    def at_least_one_field(self, data, **kwargs):
        if not data:
            raise ValidationError("Debes enviar al menos un campo para actualizar.")
