from django.db.models.signals import post_delete
from django.dispatch import receiver

from .media_models import BabyPrivateMedia
from .media_service import media_path


@receiver(post_delete, sender=BabyPrivateMedia)
def delete_private_media_file(sender, instance, **kwargs):
    try:
        path = media_path(instance)
    except Exception:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
