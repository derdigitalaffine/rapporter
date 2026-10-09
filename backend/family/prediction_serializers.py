from rest_framework import serializers

from .predictions import routine_prediction
from .serializers import RoutineSerializer as BaseRoutineSerializer


class RoutinePredictionSerializer(BaseRoutineSerializer):
    prediction=serializers.SerializerMethodField()
    def get_prediction(self,obj):return routine_prediction(obj)
    class Meta(BaseRoutineSerializer.Meta):
        fields=[*BaseRoutineSerializer.Meta.fields,"prediction"]
        read_only_fields=["prediction"]
