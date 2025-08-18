from decimal import Decimal, ROUND_HALF_UP

from marshmallow import EXCLUDE, pre_load, post_dump, fields
from marshmallow_sqlalchemy import SQLAlchemyAutoSchema
from api.models2 import db, Ride


class RideSchema(SQLAlchemyAutoSchema):
    class Meta:
        model = Ride
        sqla_session = db.session
        include_fk = True
        include_relationships = True   # Si no quieres relaciones, pon False
        load_instance = True
        ordered = True
        unknown = EXCLUDE
        # Formato ISO para DateTime (ajusta si tu modelo no usa tz):
        datetimeformat = "%Y-%m-%dT%H:%M:%S%z"
        # Marca como solo-salida si existen en tu modelo (si no existen, se ignoran)
        dump_only = ("id", "created_at", "updated_at")

    # ==== Ejemplos de personalización de campos (descomenta si existen en el modelo) ====
    # Si tienes columnas monetarias Numeric/DECIMAL en la tabla:
    # base_price = fields.Decimal(as_string=True, places=2)
    # total_price = fields.Decimal(as_string=True, places=2)

    # Relaciones anidadas (si quieres incluir info del relacionado):
    # customer = fields.Nested("UserSchema", only=("id", "name", "email"), dump_only=True)
    # driver = fields.Nested("DriverSchema", only=("id", "name"), dump_only=True)
    # vehicle = fields.Nested("VehicleSchema", only=("id", "plate"), dump_only=True)
    # extras = fields.List(fields.Nested("RideExtraSchema"), dump_only=True)

    @pre_load
    def _normalize_strings(self, data, **kwargs):
        """Recorta espacios en cadenas de entrada."""
        if isinstance(data, dict):
            for k, v in list(data.items()):
                if isinstance(v, str):
                    data[k] = v.strip()
        return data

    @post_dump
    def _decimal_to_string(self, data, **kwargs):
        """Convierte Decimal a string con 2 decimales en la salida JSON."""
        for k, v in list(data.items()):
            if isinstance(v, Decimal):
                data[k] = str(v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        return data
