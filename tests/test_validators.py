import pytest
from pydantic import ValidationError

from utils.validators import LoginInput, RegistrationInput


def test_registration_accepts_a_name_written_in_bengali():
    registration = RegistrationInput(
        full_name="মাশহুদ রহমান",
        email="mashhud@example.com",
        password="valid-password-123",
    )

    assert registration.full_name == "মাশহুদ রহমান"


@pytest.mark.parametrize("full_name", ["   ", "---", "✨"])
def test_registration_rejects_names_without_letters_or_numbers(full_name):
    with pytest.raises(ValidationError):
        RegistrationInput(
            full_name=full_name,
            email="person@example.com",
            password="valid-password-123",
        )


def test_login_rejects_unexpected_fields():
    with pytest.raises(ValidationError):
        LoginInput(
            email="person@example.com",
            password="valid-password-123",
            role="admin",
        )
