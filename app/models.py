from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    fecha_registro = Column(DateTime, default=datetime.utcnow)
    analisis = relationship("Analisis", back_populates="usuario")

class Analisis(Base):
    __tablename__ = "analisis"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    texto_analizado = Column(Text, nullable=False)
    resultado = Column(Text, nullable=True)  # Permitir valores nulos para evitar errores
    session_id = Column(String, nullable=True)
    origen = Column(String, nullable=True)
    fecha = Column(DateTime, default=datetime.utcnow)
    usuario = relationship("Usuario", back_populates="analisis")
