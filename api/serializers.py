from rest_framework import serializers

from api.services.scheduling import KNOWN_GRADES
from api.services.sessions import KNOWN_DIFFICULTIES


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, style={"input_type": "password"})

    def validate_email(self, value: str) -> str:
        # Store/lookup emails in lowercase so unique=True is case-safe.
        return value.strip().lower()


class CreateSessionSerializer(serializers.Serializer):
    category_id = serializers.IntegerField(min_value=1)
    difficulties = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=False,
    )

    def validate_difficulties(self, value: list[str]) -> list[str]:
        unknown = [item for item in value if item not in KNOWN_DIFFICULTIES]
        if unknown:
            raise serializers.ValidationError(
                f"Unknown difficulty values: {', '.join(sorted(set(unknown)))}."
            )
        # Preserve order, drop duplicates.
        seen: set[str] = set()
        ordered: list[str] = []
        for item in value:
            if item not in seen:
                seen.add(item)
                ordered.append(item)
        return ordered


class RateCardSerializer(serializers.Serializer):
    word_id = serializers.IntegerField(min_value=1)
    grade = serializers.CharField()

    def validate_grade(self, value: str) -> str:
        grade = value.strip().lower()
        if grade not in KNOWN_GRADES:
            raise serializers.ValidationError(f"Unknown grade: {value}. Expected hard or easy.")
        return grade


class FlagWordSerializer(serializers.Serializer):
    word_id = serializers.IntegerField(min_value=1)
