class VehiclesNoStoreMiddleware:
    """Sensitive endpoints must not enter proxy/browser caches, including errors."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(("/api/vehicles/", "/api/vehicle-journeys/")):
            response["Cache-Control"] = "private, no-store"
        return response
