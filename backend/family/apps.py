from django.apps import AppConfig


class FamilyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "family"

    def ready(self):
        # Feature models live in separate modules to keep the core model file merge-friendly.
        from . import models as core_models
        from .birthday_context_models import BirthdayOccasion
        from .board_models import BoardImage, BoardPost
        from .context_models import ContextLink
        from .family_master_models import FamilyMasterData
        from .notes_models import Note, NoteRevision, NoteShare
        from .shopping_models import ShoppingListStoreProfile, ShoppingStore, ShoppingTemplate, ShoppingTemplateItem
        from .today_models import TodayLayout
        from .todo_models import TodoActionPreference, TodoPreference
        from .travel_models import Trip, TripPhoto
        core_models.BirthdayOccasion = BirthdayOccasion
        core_models.BoardPost = BoardPost
        core_models.BoardImage = BoardImage
        core_models.ContextLink = ContextLink
        core_models.FamilyMasterData = FamilyMasterData
        core_models.Note = Note
        core_models.NoteShare = NoteShare
        core_models.NoteRevision = NoteRevision
        core_models.ShoppingStore = ShoppingStore
        core_models.ShoppingListStoreProfile = ShoppingListStoreProfile
        core_models.ShoppingTemplate = ShoppingTemplate
        core_models.ShoppingTemplateItem = ShoppingTemplateItem
        core_models.TodayLayout = TodayLayout
        core_models.TodoPreference = TodoPreference
        core_models.TodoActionPreference = TodoActionPreference
        core_models.Trip = Trip
        core_models.TripPhoto = TripPhoto
        from . import models_features  # noqa: F401
        from . import board_notifications  # noqa: F401
        from . import invitation_signals  # noqa: F401
        from . import prediction_signals  # noqa: F401
        from . import signals  # noqa: F401
        from . import travel_signals  # noqa: F401
        from . import waste_calendar  # noqa: F401

        # Invitation links are rendered lazily by the mailer. The reference ID contains
        # only invite UUID + a non-secret generation nonce; the raw bearer token is
        # reconstructed in memory and is never persisted in either invite or outbox rows.
        from mailing.service import register_reference_resolver
        from .invitation_service import invitation_path

        register_reference_resolver("family.invitation", invitation_path)
