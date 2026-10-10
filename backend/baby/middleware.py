class PrivateBabyNoStoreMiddleware:
    """Keep Pregnancy & Baby API responses out of shared/browser caches."""

    def __init__(self,get_response):
        self.get_response=get_response

    def __call__(self,request):
        response=self.get_response(request)
        if request.path.startswith('/api/baby/'):
            response['Cache-Control']='private, no-store, max-age=0'
            response['Pragma']='no-cache'
            response['Vary']='Cookie, Authorization'
        return response
