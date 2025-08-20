# Filename: app/models.py
# Approx lines modified: ~1-30
# Reason: (Optional) Add a __repr__ for easier debugging in logs/UI; no schema change.

from sqlalchemy import Column, Integer, String
from app.database import Base

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    sender = Column(String)
    message = Column(String)
    response = Column(String)

    def __repr__(self) -> str:  # [ADDED]
        # Helpful for debugging and in templates if needed
        return f"<Conversation id={self.id} sender={self.sender!r}>"
