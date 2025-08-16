# app/schemas/user_schemas.py

from marshmallow import Schema, fields, validate, pre_load
from typing import Any, Iterable


class RoleSchema(Schema):
    id = fields.Int(dump_only=True)
    name = fields.Str(required=True)

    class Meta:
        ordered = True


class PermissionSchema(Schema):
    id = fields.Int(dump_only=True)
    code = fields.Str(required=True)
    name = fields.Str(required=False)

    class Meta:
        ordered = True


class UserSchema(Schema):
    """Schema principal para usuarios con soporte de roles y permisos.

    - Valida `name`, `email`, `marketing_allowed` en entrada.
    - Normaliza `email` (minúsculas y sin espacios) en `pre_load`.
    - Expone `roles` y `permissions` solo en salida (dump_only).
    - No serializa información sensible (contraseñas, tokens, etc.).
    """

    # Campos base
    id = fields.Int(dump_only=True)
    name = fields.Str(
        required=True,
        validate=validate.Length(min=2, max=100),
        error_messages={
            "required": "El nombre es obligatorio",
            "null": "El nombre no puede ser nulo",
        },
    )
    email = fields.Email(
        required=True,
        validate=validate.Length(max=255),
        error_messages={
            "required": "El email es obligatorio",
            "null": "El email no puede ser nulo",
            "invalid": "El email no es válido",
        },
    )
    marketing_allowed = fields.Bool(required=False, missing=False)

    # Solo salida
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)

    # ---- Salida enriquecida
    # Preferimos listas de objetos (id, name) si el modelo lo permite; si no, devolvemos strings.
    roles = fields.Method("_dump_roles", dump_only=True)
    permissions = fields.Method("_dump_permissions", dump_only=True)

    class Meta:
        ordered = True

    # ------- Normalización de entrada
    @pre_load
    def _normalize(self, data: dict[str, Any], **kwargs):
        if not isinstance(data, dict):
            return data
        email = data.get("email")
        if isinstance(email, str):
            data["email"] = email.strip().lower()
        name = data.get("name")
        if isinstance(name, str):
            data["name"] = name.strip()
        return data

    # ------- Serialización de roles/permissions
    def _dump_roles(self, obj: Any) -> list[dict] | list[str]:
        roles_attr = getattr(obj, "roles", None)
        if isinstance(roles_attr, Iterable):
            out = []
            for r in roles_attr:
                # Compatibilidad: algunos proyectos usan `name`, otros `slug`
                rid = getattr(r, "id", None)
                rname = getattr(r, "name", None) or getattr(r, "slug", None)
                if rid is not None and rname is not None:
                    out.append({"id": rid, "name": rname})
                elif rname is not None:
                    out.append(rname)
            return out
        # Si no hay relación, intenta método get_primary_role
        primary = getattr(obj, "get_primary_role", lambda: None)()
        return [primary] if primary else []

    def _dump_permissions(self, obj: Any) -> list[dict] | list[str]:
        # Casos comunes: user.permissions directo, o agregado por roles
        perms_attr = getattr(obj, "permissions", None)
        if isinstance(perms_attr, Iterable):
            return _serialize_permissions(perms_attr)

        # Si no existe, intenta agregarlas desde roles (role.permissions)
        roles_attr = getattr(obj, "roles", None)
        if isinstance(roles_attr, Iterable):
            agg = []
            seen = set()
            for r in roles_attr:
                rp = getattr(r, "permissions", None)
                if not isinstance(rp, Iterable):
                    continue
                for p in rp:
                    key = getattr(p, "id", None) or getattr(p, "code", None) or getattr(p, "name", None)
                    if key in seen:
                        continue
                    seen.add(key)
                    agg.append(p)
            return _serialize_permissions(agg)
        return []


# --------- Helpers internos ---------

def _serialize_permissions(perms: Iterable[Any]) -> list[dict] | list[str]:
    out = []
    for p in perms:
        pid = getattr(p, "id", None)
        code = getattr(p, "code", None) or getattr(p, "name", None)
        name = getattr(p, "name", None)
        if pid is not None and code is not None:
            out.append({"id": pid, "code": code, "name": name})
        elif code is not None:
            out.append(code)
    return out
