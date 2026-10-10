from django.apps import AppConfig


class FamilyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "family"

    def ready(self):
        # Feature models live in separate modules to keep the core model file merge-friendly.
        from . import models as core_models
        from .board_models import BoardImage, BoardPost
        from .family_master_models import FamilyMasterData
        from .notes_models import Note, NoteRevision, NoteShare
        from .today_models import TodayLayout
        core_models.BoardPost = BoardPost
        core_models.BoardImage = BoardImage
        core_models.FamilyMasterData = FamilyMasterData
        core_models.Note = Note
        core_models.NoteShare = NoteShare
        core_models.NoteRevision = NoteRevision
        core_models.TodayLayout = TodayLayout
        from . import models_features  # noqa: F401
        from . import board_notifications  # noqa: F401
        from . import prediction_signals  # noqa: F401
        from . import signals  # noqa: F401
        from . import waste_calendar  # noqa: F401
