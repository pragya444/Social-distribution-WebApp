from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import TemplateHTMLRenderer, JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import redirect
from django.urls import reverse
from django.contrib.auth import logout as django_logout
from .serializers import LoginSerializer, RegisterSerializer
from ..utils import jwtUtils


class LoginView(APIView):
    renderer_classes = [TemplateHTMLRenderer, JSONRenderer]

    def get(self, request):
        if getattr(request, "user", None) and request.user.is_authenticated:
            return redirect('home')
        return Response(template_name="auth/login.html")
    
    def post(self, request):
        serializer = LoginSerializer(data=request.data)

        if not serializer.is_valid():
            print("Not Valid")
            return Response(
                {"errors": serializer.errors, "data": request.data},
                template_name="auth/login.html",
                status=400,
            )
        
        user = serializer.validated_data["user"]
        if not user.is_active:
            return Response(
                {"errors": {"non_field_errors": ["Your account is pending admin approval."]}},
                template_name="templates/login.html", status=403,)

        jwt_token = jwtUtils.make_access_token(user.id)
        print(jwt_token)
        response = redirect(reverse("author-all-entries", args=[user.id]))
        response.set_cookie('jwt', jwt_token, httponly=True, max_age=60*60*24*7)
        print("Redirecting")
        return response


class RegisterView(APIView):
    renderer_classes = [TemplateHTMLRenderer, JSONRenderer]

    def get(self, request):
        return Response(template_name="auth/register.html")
    
    def post(self, request):
        # print(request.data)
        serializer = RegisterSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(
                {"errors": serializer.errors, "data": request.data},
                template_name="auth/register.html",
                status=400,
            )

        user = serializer.save()

        return Response(
            {"msg": "Please wait for an admin to approve your account."},
            template_name="auth/register.html",
            status=201
        )


class LogoutView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        django_logout(request)
        resp = redirect('login')
        for name in ('jwt', 'sessionid', 'csrftoken'):
            resp.delete_cookie(name, path='/')
        return resp
