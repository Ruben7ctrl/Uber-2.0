from __future__ import annotations
from typing import Optional, List
from datetime import datetime
import hashlib
import os

from flask import current_app
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import (
    String, Boolean, Integer, Float, DateTime, Enum,
    ForeignKey, Numeric, JSON, event, Table
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Si usas MailChimp:
from mailchimp3 import MailChimp

db = SQLAlchemy()


# =========================================================
# MODELOS DE USUARIO Y AUTENTICACIÓN
# =========================================================

class User(db.Model):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # client, driver, admin
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    marketing_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    profile_photo_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    type: Mapped[str] = mapped_column(String(50))  # discriminador polimórfico

    vehicle_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey('vehicles.id'), nullable=True, unique=True
    )

    roles: Mapped[List["Role"]] = relationship(
        "Role", secondary=roles_users, back_populates="users"
    )
    documents: Mapped[List["DriverDocument"]] = relationship(
        "DriverDocument", back_populates="user"
    )
    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction", back_populates="user"
    )
    rides_as_driver: Mapped[List["Ride"]] = relationship(
        "Ride", foreign_keys="Ride.driver_id", back_populates="driver"
    )
    rides_as_customer: Mapped[List["Ride"]] = relationship(
        "Ride", foreign_keys="Ride.customer_id", back_populates="customer"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __mapper_args__ = {
        'polymorphic_identity': 'user',
        'polymorphic_on': type
    }

    def is_driver(self) -> bool: return self.role == "driver"
    def is_client(self) -> bool: return self.role == "client"
    def is_admin(self) -> bool: return self.role == "admin"

    def serialize(self): {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "marketing_allowed": self.marketing_allowed,
            "profile_photo_path": self.profile_photo_path,
            "type": self.type,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
        if isinstance(self, Driver):
            base["documents"] = [doc.serialize() for doc in self.documents]
            base["vehicle"] = self.vehicle.serialize() if self.vehicle else None
        return base

    def _subscriber_hash(self) -> str:
        return hashlib.md5(self.email.lower().encode('utf-8')).hexdigest()

    @staticmethod
    def t(query: str) -> str:
        return {"user": "cliente", "users": "clientes"}.get(query.lower(), query)

    @staticmethod
    def after_save_hook(mapper, connection, target):
        if current_app.config.get("ENV") != "development" and target.email:
            print("📨 Ejecutando sincronización con Mailchimp...")
            try:
                from mailchimp3 import MailChimp
                client = MailChimp(
                    mc_api=os.environ['MAILCHIMP_API_KEY'],
                    mc_user=os.environ['MAILCHIMP_USERNAME']
                )
                list_id = os.environ['MAILCHIMP_LIST_ID']
                if target.marketing_allowed:
                    client.lists.members.create_or_update(
                        list_id, target._subscriber_hash(),
                        {
                            'email_address': target.email,
                            'status_if_new': 'subscribed',
                            'status': 'subscribed',
                            'merge_fields': {'FNAME': target.name}
                        }
                    )
                else:
                    client.lists.members.update(
                        list_id, target._subscriber_hash(),
                        {'status': 'unsubscribed'}
                    )
            except Exception as e:
                print(f"[Mailchimp Sync Error] {e}")

event.listen(User, 'after_insert', User.after_save_hook)
event.listen(User, 'after_update', User.after_save_hook)

class Admin(User):
    __mapper_args__ = {'polymorphic_identity': 'admin'}
    def can_manage_reservations(self) -> bool: return True
    def can_edit_content(self) -> bool: return True

class Driver(User):
    __mapper_args__ = {'polymorphic_identity': 'driver'}
    vehicle: Mapped[Optional["Vehicle"]] = relationship("Vehicle", back_populates="driver", uselist=False)
    def get_assigned_vehicle(self): return self.vehicle
    def can_view_assigned_trips(self) -> bool: return True

class Customer(User):
    __mapper_args__ = {'polymorphic_identity': 'customer'}
    def can_make_reservations(self) -> bool: return True
    def serialize(self):
        base = super().serialize()
        base["marketing_allowed"] = self.marketing_allowed
        return base

# =========================================================
# MODELOS DE VIAJE
# =========================================================

class RideStatus(db.Model):
    __tablename__ = 'ride_statuses'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hex: Mapped[str] = mapped_column(String(7), nullable=False)
    rides: Mapped[List["Ride"]] = relationship("Ride", back_populates="status")
    
    def serialize(self): 
        return {
            "id": self.id, 
            "name": self.name, 
            "display_name": self.display_name, 
            "hex": self.hex
        }

class RideExtra(db.Model):
    __tablename__ = 'ride_extras'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    
    def serialize(self): 
        return {
            "id": self.id, 
            "name": self.name, 
            "price": self.price
        }

class Ride(db.Model):
    __tablename__ = 'rides'
    STATUS_ACTIVE = 'active'
    STATUS_DONE = 'done'
    STATUS_CANCELED = 'canceled'
    STATUS_CREATED = 'created'

    id: Mapped[int] = mapped_column(primary_key=True)
    pickup: Mapped[dict] = mapped_column(JSON, nullable=True)
    destination: Mapped[dict] = mapped_column(JSON, nullable=True)
    parada: Mapped[dict] = mapped_column(JSON, nullable=True)
    status_value: Mapped[str] = mapped_column(Enum(STATUS_ACTIVE, STATUS_DONE, STATUS_CANCELED, STATUS_CREATED), default=STATUS_CREATED)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    city_id: Mapped[int] = mapped_column(ForeignKey('cities.id'), nullable=False)
    driver_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id'), nullable=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    status_id: Mapped[Optional[int]] = mapped_column(ForeignKey('ride_statuses.id'), nullable=True)
    service_requested_id: Mapped[Optional[int]] = mapped_column(ForeignKey('vehicle_categories.id'), nullable=True)

    city: Mapped["City"] = relationship("City", back_populates="rides")
    driver: Mapped["User"] = relationship("User", foreign_keys=[driver_id], back_populates="rides_as_driver")
    customer: Mapped["User"] = relationship("User", foreign_keys=[customer_id], back_populates="rides_as_customer")
    status: Mapped["RideStatus"] = relationship("RideStatus", back_populates="rides")
    extras: Mapped[List["RideExtra"]] = relationship("RideExtra", secondary=ride_extras_pivot)
    transactions: Mapped[List["Transaction"]] = relationship("Transaction", back_populates="ride")

    def serialize(self):
        return {
            "id": self.id,
            "pickup": self.pickup,
            "destination": self.destination,
            "parada": self.parada,
            "status": self.status_value,
            "status_translation": self.get_ride_status_translation(self.status_value),
            "created_at": self.created_at.isoformat(),
            "city": self.city.serialize() if self.city else None,
            "driver": self.driver.serialize() if self.driver else None,
            "customer": self.customer.serialize() if self.customer else None,
            "extras": [extra.serialize() for extra in self.extras]
        }

    @staticmethod
    def get_ride_status_translation(status: str) -> str:
        return {
            Ride.STATUS_ACTIVE: "activo",
            Ride.STATUS_DONE: "completado",
            Ride.STATUS_CANCELED: "cancelado",
            Ride.STATUS_CREATED: "creado",
        }.get(status, status)

# =========================================================
# MODELOS RELACIONADOS
# =========================================================

class City(db.Model):
    __tablename__ = 'cities'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    rides: Mapped[List["Ride"]] = relationship("Ride", back_populates="city")
    
    def serialize(self) -> dict:
        return {
            "id": self.id, 
            "name": self.name, 
            "display_name": self.display_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None}
        
    @classmethod
    def madrid(cls): return cls.query.filter_by(name='madrid').first()
    @staticmethod
    def t(query: str) -> str: return {"city": "ciudad", "cities": "ciudades"}.get(query.lower(), query)

class DriverDocument(db.Model):
    __tablename__ = 'driver_documents'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    document_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_path: Mapped[str] = mapped_column(String(255), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user: Mapped["User"] = relationship("User", back_populates="documents")
    
    def serialize(self): 
        return {
            "id": self.id, 
            "user_id": self.user_id, 
            "document_type": self.document_type,
            "file_path": self.file_path, 
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None}

class UserImage(db.Model):
    __tablename__ = 'user_images'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    image_type: Mapped[str] = mapped_column(String(100), nullable=False)
    image_url: Mapped[str] = mapped_column(String(255), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user: Mapped["User"] = relationship("User")
    
    def serialize(self):
        return {
            "id": self.id, 
            "user_id": self.user_id, 
            "image_type": self.image_type,
            "image_url": self.image_url, 
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None
        }

# =========================================================
# MODELOS DE VEHÍCULOS
# =========================================================

class VehicleBrand(db.Model):
    __tablename__ = 'vehicle_brands'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    models: Mapped[List["VehicleModel"]] = relationship('VehicleModel', back_populates="brand")
    
    def serialize(self): 
        return {
            "id": self.id, 
            "name": self.name
        }

class VehicleModel(db.Model):
    __tablename__ = 'vehicle_models'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    brand_id: Mapped[int] = mapped_column(ForeignKey('vehicle_brands.id'))
    brand: Mapped["VehicleBrand"] = relationship("VehicleBrand", back_populates="models")
    vehicles: Mapped[List["Vehicle"]] = relationship("Vehicle", back_populates="model")
    
    def serialize(self): 
        return {
            "id": self.id, 
            "name": self.name, 
            "brand": self.brand.name if self.brand else None
        }

class VehicleColor(db.Model):
    __tablename__ = 'vehicle_colors'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hex: Mapped[str] = mapped_column(String(7), nullable=False)
    vehicles: Mapped[List["Vehicle"]] = relationship("Vehicle", back_populates="color")
    
    def serialize(self): 
        return {
            "id": self.id, 
            "name": self.name, 
            "hex": self.hex
        }

class VehicleCategory(db.Model):
    __tablename__ = 'vehicle_categories'
    id: Mapped[int] = mapped_column(primary_key=True)
    img: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    rate: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    min_rate: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    airport_min_rate: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    vehicles: Mapped[List["Vehicle"]] = relationship("Vehicle", back_populates="category")
    
    def serialize(self):
        return {
            "id": self.id, 
            "img": self.img, 
            "name": self.name,
            "rate": float(self.rate) if self.rate else None,
            "min_rate": float(self.min_rate) if self.min_rate else None,
            "airport_min_rate": float(self.airport_min_rate) if self.airport_min_rate else None}

class Vehicle(db.Model):
    __tablename__ = 'vehicles'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    license_plate: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    model_id: Mapped[int] = mapped_column(ForeignKey("vehicle_models.id"))
    color_id: Mapped[int] = mapped_column(ForeignKey("vehicle_colors.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("vehicle_categories.id"))
    model: Mapped["VehicleModel"] = relationship("VehicleModel", back_populates="vehicles")
    color: Mapped["VehicleColor"] = relationship("VehicleColor", back_populates="vehicles")
    category: Mapped["VehicleCategory"] = relationship("VehicleCategory", back_populates="vehicles")
    driver: Mapped[Optional[Driver]] = relationship("Driver", back_populates="vehicle", uselist=False)
    
    def serialize(self):
        return {
            "id": self.id, 
            "name": self.name, 
            "model": self.model.name if self.model else None,
            "color": self.color.name if self.color else None,
            "category": self.category.name if self.category else None}

# =========================================================
# OTROS MODELOS
# =========================================================

class Role(db.Model):
    __tablename__ = 'roles'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    users = relationship("User", secondary=roles_users, back_populates="roles")
    permissions = relationship("Permission", secondary=roles_permissions, back_populates="roles")
    
    def serialize(self): 
        return {
            "id": self.id, 
            "name": self.name, 
            "display_name": self.display_name,
            "permissions": [p.serialize() for p in self.permissions]
        }

class Permission(db.Model):
    __tablename__ = 'permissions'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    roles = relationship("Role", secondary=roles_permissions, back_populates="permissions")
    
    def serialize(self): 
        return {
            "id": self.id, 
            "name": self.name
        }

class Setting(db.Model):
    __tablename__ = 'settings'
    key: Mapped[str] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    
    def serialize(self): 
        return {
            "key": self.key, 
            "display_name": self.display_name, 
            "value": self.value
        }

# =========================================================
# TRANSACCIONES
# =========================================================

class Transaction(db.Model):
    __tablename__ = 'transactions'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    ride_id: Mapped[Optional[int]] = mapped_column(ForeignKey('rides.id'), nullable=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user: Mapped["User"] = relationship("User", back_populates="transactions")
    ride: Mapped[Optional["Ride"]] = relationship("Ride", back_populates="transactions")
    
    
    def serialize(self):
        return {"id": self.id, 
                "user_id": self.user_id, 
                "ride_id": self.ride_id,
                "amount": self.amount, 
                "type": self.type, 
                "currency": self.currency,
                "created_at": self.created_at.isoformat()
            }
