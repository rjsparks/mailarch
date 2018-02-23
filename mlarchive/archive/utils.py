import codecs
import json
import os
import shutil
from collections import OrderedDict

from django.conf import settings
from django.core.cache import cache
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.template.loader import render_to_string

from mlarchive.archive.models import EmailList, Message
from mlarchive.utils.test_utils import get_search_backend

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------


def get_noauth(request):
    """This function takes a request object and returns a list of private email list names
    the user does NOT have access to, for use in an exclude().  The list is
    stored in the request session to minimize database hits.
    """
    noauth = request.session.get('noauth', None)
    if noauth:
        return noauth

    if request.user.is_superuser:
        lists = []
    elif request.user.is_authenticated:
        lists = [x.name for x in EmailList.objects.filter(private=True).exclude(members=request.user)]
    else:
        lists = [x.name for x in EmailList.objects.filter(private=True)]
    if get_search_backend() == 'xapian':
        lists = [x.replace('-', ' ') for x in lists]
    request.session['noauth'] = lists
    return request.session['noauth']


def get_lists():
    """Returns OrderedDict of all EmailLists"""
    lists = cache.get('lists')
    if lists:
        return lists
    else:
        lists = EmailList.objects.all().order_by('name').values_list('name', flat=True)
        lists = OrderedDict([(k, None) for k in lists])
        cache.set('lists', lists)
        return lists


def get_public_lists():
    lists = cache.get('lists_public')
    if lists:
        return lists
    else:
        public = EmailList.objects.filter(private=False).order_by('name').values_list('name', flat=True)
        lists = OrderedDict([(k, None) for k in public])
        cache.set('lists_public', lists)
        return lists


def get_lists_for_user(request):
    """Returns names of EmailLists the user has access to"""
    if not request.user.is_authenticated:
        return get_public_lists()

    if request.user.is_authenticated():
        if request.user.is_superuser:
            lists = get_lists()
        else:
            lists = EmailList.objects.all().exclude(name__in=get_noauth(request))
            lists = OrderedDict([(k, None) for k in lists])

    return lists


def jsonapi(fn):
    def to_json(request, *args, **kwargs):
        context_data = fn(request, *args, **kwargs)
        return HttpResponse(json.dumps(context_data), content_type='application/json')
    return to_json


def rebuild_static_index(elist=None):
    """Rebuilds static index pages for all public lists"""
    assert 'static' in settings.STATIC_INDEX_DIR    # extra precaution before removing
    if elist:
        assert not elist.private
        elists = [elist]
        path = os.path.join(settings.STATIC_INDEX_DIR, elist.name)
        if os.path.exists(path):
            shutil.rmtree(path)
    else:
        elists = EmailList.objects.filter(private=False).order_by('name')
        if os.path.exists(settings.STATIC_INDEX_DIR):
            shutil.rmtree(settings.STATIC_INDEX_DIR)
        os.mkdir(settings.STATIC_INDEX_DIR)

    for elist in elists:
        os.mkdir(os.path.join(settings.STATIC_INDEX_DIR, elist.name))
        build_index_page(elist)
        build_date_pages(elist)
        build_thread_pages(elist)


def build_index_page(elist):
    """Create the index.html"""
    index_path = os.path.join(settings.STATIC_INDEX_DIR, elist.name, 'index.html')
    content = render_to_string('archive/static_index_index.html', {'url': 'maillist.html'})
    with codecs.open(index_path, 'w', 'utf8') as index_file:
        index_file.write(content)


def build_date_pages(elist):
    messages = elist.message_set.order_by('date')
    paginator = Paginator(messages, settings.STATIC_INDEX_MESSAGES_PER_PAGE)
    for page_number in paginator.page_range:
        page = paginator.page(page_number)
        if page_number == paginator.num_pages:
            filename = 'maillist.html'
            date_index_page = 0
        else:
            filename = 'mail{page_number:04d}.html'.format(page_number=page_number)
            date_index_page = page_number

        queryset = Message.objects.filter(id__in=[m.id for m in page.object_list])
        queryset.update(date_index_page=date_index_page)

        path = os.path.join(settings.STATIC_INDEX_DIR, elist.name, filename)
        content = render_to_string('archive/static_index_date.html', {'page': page})
        with codecs.open(path, 'w', 'utf8') as static_file:
            static_file.write(content)


def build_thread_pages(elist):
    messages = list(elist.message_set.order_by('-thread__date', 'thread__id', 'thread_order'))
    messages.reverse()
    paginator = Paginator(messages, settings.STATIC_INDEX_MESSAGES_PER_PAGE)
    for page_number in paginator.page_range:
        page = paginator.page(page_number)
        if page_number == paginator.num_pages:
            filename = 'threadlist.html'
            thread_index_page = 0
        else:
            filename = 'thread{page_number:04d}.html'.format(page_number=page_number)
            thread_index_page = page_number

        queryset = Message.objects.filter(id__in=[m.id for m in page.object_list])
        queryset.update(thread_index_page=thread_index_page)

        path = os.path.join(settings.STATIC_INDEX_DIR, elist.name, filename)
        content = render_to_string('archive/static_index_thread.html', {'page': page})
        with codecs.open(path, 'w', 'utf8') as static_file:
            static_file.write(content)
