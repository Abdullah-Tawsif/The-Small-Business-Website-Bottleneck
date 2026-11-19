from pydantic import BaseModel, ConfigDict, EmailStr

class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    full_name: str
    email: EmailStr
    role: str
