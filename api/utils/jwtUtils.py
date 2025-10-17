import jwt, datetime
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist

User = get_user_model()

JWT_ALG = 'HS256'
JWT_ACCESS_DAYS = 7

def make_access_token(user_id):
    payload = {
        'id': user_id,
        'exp': datetime.datetime.now() + datetime.timedelta(days=7),
        'iat': datetime.datetime.now()
    }

    encoded_token = jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALG)
    return encoded_token

def decode_and_get_user(token):
    decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=JWT_ALG)
    user_id = decoded.get('id')

    if not user_id:
        return None
    
    try:
        return User.objects.get(pk=user_id, is_active=True)
    except ObjectDoesNotExist:
        return None