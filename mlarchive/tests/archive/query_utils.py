
import pytest

from haystack.query import SearchQuerySet
from django.core.cache import cache
from django.http import QueryDict
from django.test import RequestFactory
from django.urls import reverse
from factories import EmailListFactory

from mlarchive.archive.query_utils import (clean_queryid, generate_queryid, get_cached_query,
    get_filter_params, query_is_listname, parse_query, map_sort_option)
from mlarchive.utils.test_utils import get_request


def test_clean_queryid():
    # good queryid
    good_queryid = 'df6d7ccfedface723ffb184a6f52bab3'
    assert clean_queryid(good_queryid) == good_queryid
    # bad queryid
    bad_queryid = "df6d7ccfedface723ffb184a6f52bab3'+order+by+1+--+;"
    assert clean_queryid(bad_queryid) is None


def test_get_cached_query():
    sqs = SearchQuerySet()
    queryid = generate_queryid()
    cache.set(queryid, sqs)
    request_factory = RequestFactory()
    # using dummy url, only the qid parameter matters here
    request = request_factory.get('/arch', {'qid': queryid})
    assert get_cached_query(request)


def test_generate_queryid():
    queryid = generate_queryid()
    assert clean_queryid(queryid)


def test_get_filter_params():
    assert get_filter_params(QueryDict('f_list=pub')) == ['f_list']
    assert get_filter_params(QueryDict('f_from=joe')) == ['f_from']
    assert get_filter_params(QueryDict('f_list=pub&f_from=joe')) == ['f_list', 'f_from']
    assert get_filter_params(QueryDict('f_list=')) == []


def test_map_sort_option():
    assert map_sort_option('invalid') == ''
    assert map_sort_option('frm') == 'frm_name'
    assert map_sort_option('-frm') == '-frm_name'


@pytest.mark.django_db(transaction=True)
def test_query_is_listname():
    EmailListFactory.create(name='pubone')
    url = '%s?%s' % (reverse('archive_search'), 'q=pubone')
    request = get_request(url=url)
    assert query_is_listname(request) is True
    url = '%s?%s' % (reverse('archive_search'), 'q=dummy')
    request = get_request(url=url)
    assert query_is_listname(request) is False
    url = '%s?%s' % (reverse('archive_search'), 'q=pubone&qdr=w')
    request = get_request(url=url)
    assert query_is_listname(request) is False


def test_parse_query():
    factory = RequestFactory()
    # simple query
    request = factory.get('/arch/search/?q=dummy')
    assert parse_query(request) == 'dummy'
    # advanced query
    request = factory.get(
        '/arch/search/?as=1&nojs-query-0-field=text&nojs-query-0-qualifier=contains&nojs-query-0-value=dummy')
    assert parse_query(request) == 'text:(dummy)'
    # advanced query with nots
    request = factory.get(
        '/arch/search/?as=1&nojs-query-0-field=text&nojs-query-0-qualifier=contains&nojs-query-0-value=dummy&nojs-not-0-field=from&nojs-not-0-qualifier=contains&nojs-not-0-value=jones')  # noqa
    assert parse_query(request) == 'text:(dummy) -from:(jones)'
