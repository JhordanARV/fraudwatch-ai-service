from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import List, Optional

class UsuarioCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UsuarioOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    fecha_registro: datetime
    class Config:
        from_attributes = True

class AnalisisCreate(BaseModel):
    texto_analizado: str
    resultado: str
    session_id: Optional[str] = None
    origen: Optional[str] = None

from typing import Optional

class AnalisisOut(BaseModel):
    id: int
    texto_analizado: str
    resultado: str
    session_id: Optional[str] = None
    origen: Optional[str] = None
    fecha: datetime
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
