from .prediction_serializers import RoutinePredictionSerializer
from .views import RoutineViewSet as BaseRoutineViewSet


class RoutineViewSet(BaseRoutineViewSet):
    serializer_class=RoutinePredictionSerializer
