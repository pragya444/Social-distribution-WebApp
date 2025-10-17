from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth.models import AnonymousUser
from ..utils import jwtUtils
import jwt

class JWTAuthMiddleware(MiddlewareMixin):

    def process_request(self, request):
        if getattr(request, "user", None) and request.user.is_authenticated:
            return
        

        token = request.COOKIES.get('jwt')
        if not token:
            return
        
        try:
            user = jwtUtils.decode_and_get_user(token)
            if user:
                request.user = user
        except jwt.ExpiredSignatureError:
            pass
        except jwt.InvalidTokenError:
            pass