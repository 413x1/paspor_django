class UnggahDitolakMiddleware:
    """Ubah status response menjadi 400 Bad Request bila unggahan ditolak karena
    bukan PDF (view menandainya lewat `paspor.validators.tandai_ditolak`).

    Halaman unggah dirender ulang dengan pesan error (status 200 bila tidak diubah);
    middleware ini membuat penolakan itu berstatus 400 tanpa mengubah tiap view.
    Response berupa redirect (3xx) dibiarkan: pesan error tampil di halaman tujuan."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if getattr(request, "unggah_ditolak", False) and response.status_code == 200:
            response.status_code = 400
        return response
