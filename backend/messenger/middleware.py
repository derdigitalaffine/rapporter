class MessengerNoStoreMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/api/chat/"):
            response["Cache-Control"] = "private, no-store"
            response["Referrer-Policy"] = "no-referrer"
        return response
