from django.shortcuts import get_object_or_404, redirect
from django.core.paginator import Paginator
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.renderers import TemplateHTMLRenderer, JSONRenderer
from rest_framework.permissions import IsAuthenticated, AllowAny
from api.models import User, Entry, Follow
from api.serializers import AuthorSerializer, AuthorsSerializer, EntrySerializer
from api.utils import helpers


class ProfileView(APIView):
    renderer_classes = [TemplateHTMLRenderer, JSONRenderer]
    
    def get(self, request, author_id):
        if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
            if not request.user.is_authenticated:
                return redirect('login')
        else:
            if not request.user.is_authenticated:
                return Response({"Message": "Forbidden"}, status=403)


        if (request.user.id != author_id):
            user = get_object_or_404(User, id=author_id)
            entries = Entry.objects.filter(author_id=author_id, visibility='PUBLIC', is_deleted=False).order_by('-updated')
        else:
            user = request.user
            entries = Entry.objects.filter(author_id=author_id, is_deleted=False).order_by('-updated')

# ======================================================================
# Developed with assistance from ChatGPT (GPT-5), October 2025
# ======================================================================


        # -------- counts + relationship status -------------------------
        # counts
        posts_count = Entry.objects.filter(author=user, is_deleted=False).count()

        followers_count = Follow.objects.filter(followee=user, status=Follow.Status.APPROVED).count()
        following_count = Follow.objects.filter(follower=user, status=Follow.Status.APPROVED).count()
        friends_count = len(helpers.friends_of(user))
        # relationship (viewer -> viewed)
        rel_status = "self"  # self / none / pending / approved / rejected
        can_approve = False  # whether viewed user has requested to follow me
        if request.user.is_authenticated and request.user.id != user.id:
            rel = Follow.objects.filter(follower=request.user, followee=user).first()
            rel_status = (rel.status if rel else "none")
            # incoming pending (user -> me): lets me show approve/deny if you want it here
            can_approve = Follow.objects.filter(
                follower=user, followee=request.user, status=Follow.Status.PENDING
            ).exists()
        # --------------------------------------------------------------------

        # Pre-render HTML for template
        if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
            for e in entries:
                e.rendered = helpers.render_entry(e)

            return Response(
                {
                    "user": user,
                    "entries": entries,
                  
                    "posts_count": posts_count,
                    "followers_count": followers_count,
                    "following_count": following_count,
                    "friends_count": friends_count,
                    "rel_status": rel_status,
                    "can_approve": can_approve,
                },
                template_name="author/profile.html",
            )

        #  JSON shape if you keep the API path
        serializer = AuthorSerializer(user, context={"request": request})

        entries_data = EntrySerializer(entries, many=True, context={"request": request}).data
        return Response(
            {
                **serializer.data,
                "entries": entries_data,
                "posts_count": posts_count,
                "followers_count": followers_count,
                "following_count": following_count,
                "friends_count": friends_count,
                "rel_status": rel_status,
                "can_approve": can_approve,
            },
            status=200,
        )
    
    def post(self, request, author_id):
        return self.put(request, author_id)
    
    def put(self, request, author_id):
        if request.user.id != author_id:
            if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
                return redirect('home')
            return Response({"errors": "Only the author can edit their profile"}, status=403)

        serializer = AuthorSerializer(request.user, data=request.data, partial=True, context={"request": request})
        if not serializer.is_valid():
            if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
                return Response({"errors": serializer.errors, "user": request.user}, template_name="author/profileEdit.html", status=400)
            return Response({"errors": serializer.errors}, status=400)

        user = serializer.save()
        if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
            return redirect('profile', author_id=user.id)
        return Response({ **serializer.data }, status=200)


class ProfileEditView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [TemplateHTMLRenderer, JSONRenderer]

    def get(self, request, author_id):
        if getattr(request, "user", None) and request.user.is_authenticated and request.user.id == author_id:
            return Response({"user": request.user }, template_name="author/profileEdit.html")
        else:
            return redirect('home')



class AuthorListView(APIView):
    renderer_classes = [TemplateHTMLRenderer, JSONRenderer]
    permission_classes = [AllowAny]

    def get(self, request):
        page = int(request.GET.get('page', 1))
        size = int(request.GET.get('size', 10))
        authors = User.objects.all()
        paginator = Paginator(authors, size)
        current_page = paginator.get_page(page)

        if request.accepted_renderer.format == 'html':
            return Response({
                'title': "All Authors",
                'users': current_page
            }, template_name='author/user_list.html')

        serializer = AuthorsSerializer({
            'type': 'authors',
            'page_number': page,
            'size': size,
            'count': paginator.count,
            'authors': current_page
        }, context={'request': request})
        return Response(serializer.data)