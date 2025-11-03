from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse, HttpResponseNotAllowed, HttpResponseForbidden, HttpResponse, Http404
from rest_framework.renderers import TemplateHTMLRenderer, JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView
from ..serializers import EntrySerializer
from ..models import Entry, EntryLike
from ..utils import helpers, images



def create_payload(request):
    data = request.data
    payload = {}
    title = data.get('title', None)
    content_type = data.get('content_type', None)
    visibility = data.get('visibility', None)
    content = data.get('content', None)


    # if not all([content_type, visibility, title, content]):
    #     return payload 
    if title:
        payload['title'] = title
    if visibility:
        payload['visibility'] = visibility


    is_image = content_type in ['image/png;base64', 'image/jpeg;base64']

    if is_image:
        img_file = request.FILES.get('image')
        if img_file:
            try:
                img_ct, b64_str = images.handle_uploaded_image(img_file)
                payload['content_type'] = img_ct
                payload['content'] = b64_str
            except ValueError as e:
                return Response({"error": str(e)}, status=400)
        else:
            if content:
                payload['content'] = content
            payload['content_type'] = content_type
    else:
        # Text mode
        if content:
            payload['content'] = content  # overwrite whatever was there
        if content_type:
            payload['content_type'] = content_type
    
    return payload



class SingleEntryView(APIView):
    renderer_classes = [JSONRenderer, TemplateHTMLRenderer]


    def get(self, request, author_id, entry_id):
        entry = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)
        like = EntryLike.objects.filter(user=request.user.id, entry=entry).first()
        serializer = EntrySerializer(entry)
        
        # if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
        if entry.visibility not in ['PUBLIC', 'UNLISTED']:
            if not helpers.can_view_entry(request.user, entry):
                if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
                    return HttpResponseForbidden("You do not have permission to view this entry.")
                return Response({"error": "This entry is not shareable."}, status=403)

        # elif entry.visibility == 'UNLISTED': # Updated because unlisted has to be author or follower
        #     if not (request.user.is_authenticated and (request.user == entry.author or helpers.is_follower(request.user, entry.author))):
        #         if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
        #             return HttpResponseForbidden("You must be a follower to view this unlisted entry.")
        #         return Response({"error": "You must be a follower to view this unlisted entry."}, status=403)

        if isinstance(request.accepted_renderer, JSONRenderer):
            return Response(serializer.data, status=200)
        
        entry.rendered = helpers.render_entry(entry)
        return render(request, "entry/entry_shared.html", {"entry": entry, "like": like})
    
    
    def put(self, request, author_id, entry_id):
        if not request.user or request.user.id != author_id:
            if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
                    return HttpResponseForbidden("Only the author can edit this entry.")
            return Response({"error" : "Only the author can edit this entry"}, status=403)
        
        entry = get_object_or_404(Entry, id=entry_id, author=author_id, is_deleted=False)
        payload = create_payload(request)

        serializer = EntrySerializer(entry, data=payload, partial=True)

        if not serializer.is_valid():
            if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
                return Response(
                    {
                        "author_id": author_id,
                        "entry": entry,
                        "errors": serializer.errors,
                    },
                    template_name="entry/entry_edit.html",
                    status=400,
                )

            return Response({"errors": serializer.errors}, status=400)
        
        updated_entry = serializer.save()
        
        if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
            return redirect('author-all-entries', author_id=author_id)
        return Response(serializer.data, status=200)


    def post(self, request, author_id, entry_id):
        method = request.data.get('_method', '').upper()
        if method == 'DELETE':
            return self.delete(request, author_id, entry_id)
        return self.put(request, author_id, entry_id)
    
    
    def delete(self, request, author_id, entry_id):
        if not request.user or request.user.id != author_id:
            if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
                return HttpResponseForbidden("Only the author can delete this entry.")
            return Response({"error": "Only the author can delete this entry"}, status=403)

        entry = get_object_or_404(Entry, id=entry_id, author=author_id, is_deleted=False)
        entry.is_deleted = True
        entry.save()

        if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
            return redirect('author-all-entries', author_id=author_id)
        return Response({"msg": "Entry deleted successfully."}, status=204)




class EntryView(APIView):
    renderer_classes = [JSONRenderer, TemplateHTMLRenderer]

    def get(self, request, author_id):
        if request.user.id == author_id:
            entries = Entry.objects.filter(author_id=author_id, is_deleted=False).order_by('-updated')
        else:
            entries = Entry.objects.filter(author_id=author_id, visibility="PUBLIC", is_deleted=False).order_by('-updated')
        serialized_entries = EntrySerializer(entries, many=True)

        if isinstance(request.accepted_renderer, JSONRenderer):
            return Response(serialized_entries.data, status=200)

        return JsonResponse({"entries": serialized_entries.data}, status=200)
    
    
    def post(self, request, author_id):
        if not request.user or request.user.id != author_id or not request.user.is_authenticated:
            if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
                    return HttpResponseForbidden("Have to login as an author to create an entry.")
            return Response({"error" : "Have to login as an author to create an entry."}, status=403)
        
        payload = create_payload(request)

        serializer = EntrySerializer(data=payload, context={"request": request})

        if not serializer.is_valid():
            if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
                return Response(
                    {
                        "author_id": author_id,
                        "errors": serializer.errors,
                    },
                    template_name="entry/entry_create.html",
                    status=400,
                )

            return Response({"errors": serializer.errors}, status=400)
        
        entry = serializer.save()
        
        if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
            return redirect('author-all-entries', author_id=author_id)
        return Response(EntrySerializer(entry).data, status=201)