"""Schemas Pydantic (DTOs) para Autenticación, Perfil y Menú por Rol (RF-01, RF-15)."""
from typing import List, Optional
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    identificador: str = Field(
        ...,
        description="Correo electrónico o número de cédula del usuario",
        examples=["admin@cooperativa.ec"],
    )
    password: str = Field(
        ...,
        description="Contraseña del usuario",
        examples=["admin123"],
    )


class RegisterRequest(BaseModel):
    email: str = Field(
        ...,
        description="Correo electrónico único del usuario",
        examples=["nuevo.padre@correo.ec"],
    )
    password: str = Field(
        ...,
        min_length=6,
        description="Contraseña del usuario (mínimo 6 caracteres)",
        examples=["padre123"],
    )
    nombre: str = Field(..., examples=["Carlos"])
    apellido: str = Field(..., examples=["Mendoza"])
    cedula: str = Field(
        ...,
        min_length=10,
        max_length=13,
        description="Cédula o RUC único del usuario",
        examples=["1723456789"],
    )
    telefono: Optional[str] = Field(default=None, examples=["0991234567"])
    rol: str = Field(
        default="PADRE",
        description="Rol del usuario a registrar: PADRE, CONDUCTOR, ADMIN o SOCIO",
        examples=["PADRE"],
    )
    cooperativa_id: Optional[int] = Field(
        default=1,
        description="ID de la cooperativa de transporte escolar",
        examples=[1],
    )
    licencia: Optional[str] = Field(
        default=None,
        description="Número/tipo de licencia profesional (requerido si rol=CONDUCTOR)",
        examples=["TIPO-E-1723456789"],
    )
    nombre_razon_social: Optional[str] = Field(
        default=None,
        description="Nombre o razón social (opcional si rol=SOCIO)",
    )


class MenuItemSchema(BaseModel):
    codigo: str
    titulo: str
    ruta: str
    icono: str
    roles_permitidos: List[str]


class UsuarioPerfilSchema(BaseModel):
    id: int
    cooperativa_id: int
    cooperativa_nombre: Optional[str] = None
    email: str
    nombre: str
    apellido: str
    cedula: str
    telefono: Optional[str] = None
    activo: int
    roles: List[str]
    conductor_id: Optional[int] = None
    socio_id: Optional[int] = None

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UsuarioPerfilSchema
    menu: List[MenuItemSchema]


class CambiarPasswordRequest(BaseModel):
    password_actual: str
    password_nueva: str = Field(..., min_length=6)

