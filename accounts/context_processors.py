def status_profil(request):
    """Banner "Nomor HP belum tercatat" (AB-19) di semua halaman."""
    user = getattr(request, "user", None)
    return {"no_hp_kosong": bool(user and user.is_authenticated and not user.no_hp)}
