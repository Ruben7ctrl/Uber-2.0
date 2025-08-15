from marshmallow import Schema, fields, validates_schema, ValidationError, validate


class LoginSchema(Schema):
    email = fields.Email(required=True)
    password = fields.String(required=True)


class RegisterSchema(Schema):
    name = fields.String(required=True)
    email = fields.Email(required=True)
    password = fields.String(required=True, validate=validate.Length(min=6))
    password_confirmation = fields.String(required=True)
    marketing_allowed = fields.Boolean(required=True)

    @validates_schema
    def validate_password_confirmation(self, data, **kwargs):
        if data.get("password") != data.get("password_confirmation"):
            raise ValidationError("Passwords do not match.",
                                  field_name="password_confirmation")


class GoogleLoginSchema(Schema):
    credential = fields.String(required=True)
    marketing_allowed = fields.Boolean(required=True)


class PasswordResetSchema(Schema):
    token = fields.Str(required=True)
    password = fields.Str(required=True, validate=validate.Length(min=6))
    password_confirmation = fields.Str(required=True)

    # Validar que password y confirmación coincidan
    def validate_password_confirmation(self, data, **kwargs):
        if data.get('password') != data.get('password_confirmation'):
            raise ValidationError('Las contraseñas no coinciden')
