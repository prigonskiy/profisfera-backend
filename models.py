from sqlalchemy import Column, String, Text, Integer, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class Manufacturer(Base):
    __tablename__ = "manufacturers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    logo = Column(String)
    website = Column(String)
    description = Column(Text)
    
    products = relationship("Product", back_populates="manufacturer")

    def __str__(self):
        return self.name

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    price = Column(String)
    images_json = Column(Text, default="[]") 
    shortDesc = Column(Text)
    fullDesc = Column(Text)
    other_data = Column(Text)
    manufacturer_id = Column(Integer, ForeignKey("manufacturers.id"))
    
    manufacturer = relationship("Manufacturer", back_populates="products")