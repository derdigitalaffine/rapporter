class PrivatePetNoStoreMiddleware:
    """Prevent browser/proxy caching of private pet health and share responses."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith('/api/pets/'):
            response['Cache-Control'] = 'private, no-store'
            response['Pragma'] = 'no-cache'
            response['X-Content-Type-Options'] = 'nosniff'
        return response
