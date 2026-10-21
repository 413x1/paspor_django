from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import PeranUser, User


@receiver(post_save, sender=User)
def _pastikan_peranuser(sender, instance, raw=False, update_fields=None, **kwargs):
    """KOMPATIBILITAS SEMENTARA (dihapus di Fase 6): user yang disimpan dengan
    `role` yang belum tercatat di PeranUser (seed/test lama yang hanya mengisi
    `User.role`) otomatis mendapat baris PeranUser untuk role tersebut. Peran
    yang pernah dicabut (`is_active=False`) tidak diaktifkan ulang."""
    if raw or not instance.role:
        return
    if update_fields is not None and "role" not in update_fields:
        return
    if PeranUser.objects.filter(user=instance, role=instance.role).exists():
        return
    PeranUser.objects.create(
        user=instance,
        role=instance.role,
        unit_organisasi_id=instance.unit_organisasi_id if instance.role == User.Role.ADMIN_UNOR else None,
    )
    instance.reset_cache_peran()
