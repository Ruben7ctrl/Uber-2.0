from marshmallow import Schema, fields, validate, ValidationError, pre_load, EXCLUDE
from decimal import Decimal, ROUND_HALF_UP

NAME_LEN = validate.Length(min=1, max=120)
PRICE_MIN = Decimal("0.00")

class RideExtraSchema(Schema):
    class Meta:
        unknown = EXCLUDE   # Ignora campos no definidos
        ordered = True

    name = fields.Str(
        required=True,
        validate=NAME_LEN,
        error_messages={
            "required": "El nombre es obligatorio",
            "null": "El nombre no puede ser nulo",
        },
    )

    # Usar Decimal para precios (2 decimales, string en JSON para no perder precisión)
    price = fields.Decimal(
        required=True,
        as_string=True,       # Se serializa como string (recomendado para dinero)
        places=2,             # 2 decimales, 200
        
        rounding=ROUND_HALF_UP,
        allow_nan=False,
        validate=validate.Range(min=PRICE_MIN, error="El precio debe ser mayor o igual a 0."),
        error_messages={
            "required": "El precio es obligatorio",
            "null": "El precio no puede ser nulo",
            "invalid": "Formato de precio inválido",
        },
    )

    @pre_load
    def normalize(self, data, **kwargs):
        if not isinstance(data, dict):
            return data

        # Nombre: colapsar espacios internos y recortar extremos
        name = data.get("name")
        if isinstance(name, str):
            data["name"] = " ".join(name.split())

        # Precio: aceptar formatos tipo "12,34", "€ 12.34", "12 34"
        p = data.get("price")
        if isinstance(p, str):
            s = p.strip()
            # quitar símbolos de moneda comunes y espacios
            for sym in ("€", "$", "USD", "EUR"):
                s = s.replace(sym, "")
            s = s.replace(" ", "")
            # convertir coma decimal a punto
            s = s.replace(",", ".")
            data["price"] = s

        return data

class RideExtraUpdateSchema(RideExtraSchema):
    # todos opcionales en update
    name = fields.Str(validate=NAME_LEN)
    price = fields.Decimal(
        as_string=True, places=2, rounding=ROUND_HALF_UP, allow_nan=False,
        validate=validate.Range(min=PRICE_MIN, error="El precio debe ser mayor o igual a 0.")
    )