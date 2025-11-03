from rest_framework import serializers
from django.contrib.auth import get_user_model
User = get_user_model()

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=155, required=True)
    password = serializers.CharField(min_length=8, required=True)

    def validate(self, attrs):
        password = attrs.get('password', None)
        username = attrs.get('username', None)

        user = User.objects.filter(username=username).first()
        if not user:
            raise serializers.ValidationError({"error": "Invalid username or password"})
        
        if not user.check_password(password):
            raise serializers.ValidationError({"error": "Invalid username or password"})

        # if not user.is_active:
        #     raise serializers.ValidationError({"non_field_errors": ["Your account is not yet approved by the admin."]})

        attrs['user'] = user
        return attrs

class RegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['username', 'github', 'name', 'password', 'profile_picture']
        extra_kwargs = {
            'password': {'write_only': True, 'required': True, 'min_length': 8},
            'username': {'required': True},
            'name': {'required': True},
            'github': {'required': False, 'allow_blank': True},
            'profile_picture': {'required': False, 'allow_blank': True}
        }
    
    def validate_github(self, value):
        value = (value or "").strip()

        if not value:
            return ""
        
        if value.startswith("https://github.com"):
            return value
        
        return f"https://github.com/{value}"
    
    def validate_name(self, value):
        return value.strip()
            

    def create(self, validated_data):
        username = validated_data.pop('username')
        password = validated_data.pop('password')
        profile_picture = validated_data.pop('profile_picture', "")

        if not profile_picture:
            name = validated_data.get('name', "Anonymous")
            if (len(name.split(" "))) > 1:
                profile_picture = f"https://avatar.iran.liara.run/username?username={"+".join(name.split())}"
            else:
                profile_picture = f"https://avatar.iran.liara.run/username?username={name}"
            validated_data['profile_picture'] = profile_picture
        else:
            validated_data['profile_picture'] = profile_picture.strip()

        if User.objects.filter(username=username).exists():
            raise serializers.ValidationError({"error": "Username already exists"})

        try:
            user = User.objects.create_user(username, password, **validated_data)
        except Exception as e:
            raise serializers.ValidationError({"error": str(e)})
      
        return user

        
        


