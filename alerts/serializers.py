from rest_framework import serializers

from .models import Alert


class AlertSerializer(serializers.ModelSerializer):
    resolved = serializers.BooleanField(source="is_resolved")
    timestamp = serializers.DateTimeField(source="created_at", read_only=True)
    branch_name = serializers.ReadOnlyField(source="branch.name")

    class Meta:
        model = Alert
        fields = [
            "id",
            "title",
            "description",
            "severity",
            "resolved",
            "timestamp",
            "created_at",
            "updated_at",
            "branch",
            "branch_name",
        ]
