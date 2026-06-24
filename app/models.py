from sqlalchemy import Column, Integer, String

from app.database import CatalogBase, ChatBase


class Conversation(ChatBase):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    sender = Column(String)
    message = Column(String)
    response = Column(String)

    def __repr__(self) -> str:
        return f"<Conversation id={self.id} sender={self.sender!r}>"


class Product(CatalogBase):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    anchor = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False)
    price_cents = Column(Integer, nullable=False, default=0)
    stock = Column(Integer, nullable=False, default=0)
    image_url = Column(String, nullable=True)

    def __repr__(self) -> str:
        return f"<Product id={self.id} anchor={self.anchor!r} name={self.name!r}>"