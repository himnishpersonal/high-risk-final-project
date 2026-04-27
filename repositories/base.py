"""
Base repository providing common CRUD operations.
"""
from typing import Generic, TypeVar, Type, Optional, List
from sqlalchemy.orm import Session

from db.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    
    def __init__(self, db: Session, model: Type[ModelType]):
        self.db = db
        self.model = model
    
    def get(self, id: str) -> Optional[ModelType]:
        return self.db.query(self.model).filter(
            self.model.__table__.primary_key.columns.values()[0] == id
        ).first()
    
    def get_all(self, skip: int = 0, limit: int = 100) -> List[ModelType]:
        return self.db.query(self.model).offset(skip).limit(limit).all()
    
    def create(self, **kwargs) -> ModelType:
        instance = self.model(**kwargs)
        self.db.add(instance)
        self.db.flush()
        return instance
    
    def update(self, id: str, **kwargs) -> Optional[ModelType]:
        instance = self.get(id)
        if instance:
            for key, value in kwargs.items():
                if hasattr(instance, key):
                    setattr(instance, key, value)
            self.db.flush()
        return instance
    
    def delete(self, id: str) -> bool:
        instance = self.get(id)
        if instance:
            self.db.delete(instance)
            self.db.flush()
            return True
        return False
    
    def exists(self, id: str) -> bool:
        return self.db.query(self.model).filter(
            self.model.__table__.primary_key.columns.values()[0] == id
        ).count() > 0
    
    def count(self) -> int:
        return self.db.query(self.model).count()
