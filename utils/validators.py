from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class LoginInput(BaseModel):
    """Strict login payload; extra fields are rejected."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RegistrationInput(BaseModel):
    """Public registration payload limited to least-privilege staff accounts."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=1, max_length=100)

    @field_validator("full_name")
    @classmethod
    def name_must_contain_visible_text(cls, value: str) -> str:
        if not any(character.isalnum() for character in value):
            raise ValueError("Name must contain letters or numbers.")
        return value
