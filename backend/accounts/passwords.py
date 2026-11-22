from django.contrib.auth.password_validation import validate_password as django_validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

MIN_LENGTH = 8
MAX_LENGTH = 128


def validate_password_strength(value, user=None):
    errors = []
    if len(value) < MIN_LENGTH:
        errors.append(f"Password must be at least {MIN_LENGTH} characters.")
    if len(value) > MAX_LENGTH:
        errors.append(f"Password must be at most {MAX_LENGTH} characters.")
    if not any(ch.isdecimal() for ch in value):
        errors.append("Password must contain at least one digit.")
    if not any(not ch.isalnum() and not ch.isspace() for ch in value):
        errors.append("Password must contain at least one special character.")
    try:
        django_validate_password(value, user)
    except DjangoValidationError as exc:
        errors.extend(m for m in exc.messages if m not in errors)
    if errors:
        raise serializers.ValidationError(errors)
    return value