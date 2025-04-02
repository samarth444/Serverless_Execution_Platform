from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Function(Base):
    __tablename__ = "functions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    route = Column(String, unique=True, nullable=False)
    language = Column(String, nullable=False)
    timeout = Column(Integer, default=5)
    code = Column(Text, nullable=False)
