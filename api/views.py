from django.shortcuts import render, get_object_or_404, redirect
from .models import Entry
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

# Create your views here.
def author_stream(request, author_id):
    # simple placeholder queryset — adjust privacy rules as needed
    entries = Entry.objects.filter(deleted=False, visibility='PUBLIC').order_by('-updated')
    return render(request, 'author_all_entries.html', {'entries': entries})

@csrf_exempt  # remove for production; use CSRF token in real clients
@require_POST
def make_entries_public(request, entry_id): 
    # TODO: Implement permission checks
    """
    Sets the entry visibility to PUBLIC and redirects (or returns JSON).
    """
    entry = get_object_or_404(Entry, id=entry_id)
    entry.visibility = 'PUBLIC'
    entry.save()
    return JsonResponse({'status': 'ok', 'entry_id': entry_id, 'message': 'Entry made public successfully'}, status=200)
