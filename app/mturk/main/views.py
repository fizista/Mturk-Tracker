import datetime
import json

from itertools import chain
from collections import OrderedDict
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.contrib import messages
from django.shortcuts import redirect
from django.views.generic.simple import direct_to_template
from django.views.decorators.cache import cache_page, never_cache

import admin
import plot

from mturk.main.models import DayStats, HitGroupContent, HitGroupClass, \
                              RequesterProfile
from mturk.main.templatetags.graph import text_row_formater

from mturk.classification import NaiveBayesClassifier

from utils.enum import EnumMetaclass
from utils.sql import query_to_dicts, query_to_tuples
from utils.views import get_time_interval


HIT_DETAILS_COLUMNS = (
    ('date', 'Date'),
    ('number', '#HITs'),
)

ONE_DAY = 60 * 60 * 24
ONE_HOUR = 60 * 60


def data_formater(input):
    for cc in input:
        yield {
                'date': cc['start_time'],
                'row': (str(cc['hits']), str(cc['reward']),
                    str(cc['count']), str(cc['spam_projects'])),
        }


def general_tab_data_formatter(col, data):
    """Returns date and one other selected column."""
    for d in data:
        yield {'date': d['date'], 'row': (d['row'][col], )}


#@cache_page(ONE_HOUR)
def general(request, tab_slug=None):

    tab = GeneralTabEnum.value_for_slug.get(tab_slug, GeneralTabEnum.ALL)

    ctx = {
        'multichart': tab == GeneralTabEnum.ALL,
        'columns': GeneralTabEnum.get_graph_columns(tab),
        'title': GeneralTabEnum.get_tab_title(tab),
        'current_tab': GeneralTabEnum.enum_dict[tab],
        'top_tabs': GeneralTabEnum.enum_dict.values(),
    }

    date_from, date_to = get_time_interval(request.GET, ctx, days_ago=7)

    data = data_formater(query_to_dicts('''
            SELECT reward, hits, projects as "count", spam_projects, start_time
            FROM main_crawlagregates
            WHERE start_time >= %s AND start_time <= %s
            ORDER BY start_time ASC
        ''', date_from, date_to))

    def _is_anomaly(a, others):
        mid = sum(map(lambda e: int(e['row'][0]), others)) / len(others)
        return abs(mid - int(a['row'][0])) > 7000

    def _fixer(a, others):
        val = sum(map(lambda e: int(e['row'][0]), others)) / len(others)
        a['row'] = (str(val), a['row'][1], a['row'][2], a['row'][3])
        return a

    if settings.DATASMOOTHING:
        ctx['data'] = plot.repair(list(data), _is_anomaly, _fixer, 2)
    else:
        ctx['data'] = list(data)

    ctx['data'] = GeneralTabEnum.data_set_processor[tab](ctx['data'])
    return direct_to_template(request, 'main/graphs/timeline.html', ctx)


def model_fields_formatter(fields, data):
    return tuple(str(getattr(data, f)) for f in fields)


#@cache_page(ONE_DAY)
def arrivals(request, tab_slug=None):

    tab = ArrivalsTabEnum.value_for_slug.get(tab_slug, ArrivalsTabEnum.ALL)

    ctx = {
        'multichart': False,
        'columns': ArrivalsTabEnum.get_graph_columns(tab),
        'title': ArrivalsTabEnum.get_tab_title(tab),
        'top_tabs': ArrivalsTabEnum.enum_dict.values(),
        'current_tab': ArrivalsTabEnum.enum_dict[tab],
    }

    def arrivals_data_formater(input, tab):
        for cc in input:
            yield {
                'date': cc.date,
                'row': ArrivalsTabEnum.data_set_processor[tab](cc),
            }

    date_from, date_to = get_time_interval(request.GET, ctx)
    data = DayStats.objects.filter(date__gte=date_from, date__lte=date_to)
    ctx['data'] = arrivals_data_formater(data, tab)
    return direct_to_template(request, 'main/graphs/timeline.html', ctx)


def requester_details(request, requester_id):
    if request.user.is_superuser:
        return admin.requester_details(request, requester_id)

    @cache_page(ONE_DAY)
    def _requester_details(request, requester_id):
        def row_formatter(input):

            for cc in input:
                row = [
                    '<a href="{}">{}</a>'.format(
                        reverse('hit_group_details', kwargs={'hit_group_id': cc[3]}),
                        cc[0],
                    ),
                    *cc[1:3],
                ]

                yield row

        requester_name = HitGroupContent.objects.filter(
            requester_id=requester_id).values_list(
            'requester_name', flat=True).distinct()

        if requester_name:
            requester_name = requester_name[0]
        else:
            requester_name = requester_id

        date_from = (datetime.date.today() - datetime.timedelta(days=30)) \
                    .isoformat()

        data = query_to_tuples("""
    select
        title,
        p.reward,
        p.occurrence_date,
        p.group_id
    from main_hitgroupcontent p
        LEFT JOIN main_requesterprofile r ON p.requester_id = r.requester_id
    where
        p.requester_id = '%s'
        AND coalesce(r.is_public, true) = true
        and
        p.occurrence_date > TIMESTAMP '%s';
        """ % (requester_id, date_from))

        columns = [
            ('string', 'HIT Title'),
            ('number', 'Reward'),
            ('datetime', 'Posted'),
        ]
        ctx = {
            'data': text_row_formater(row_formatter(data)),
            'columns': tuple(columns),
            'title': 'Tasks posted during last 30 days by %s' %
                     (requester_name, ),
            'requester_name': requester_name,
            'requester_id': requester_id,
            'user': request.user,
        }
        return direct_to_template(request, 'main/requester_details.html', ctx)

    return _requester_details(request, requester_id)


@never_cache
def hit_group_content(request, hit_group_id):
    """View used as an iframe source for hit_group_details."""

    try:
        hit_group = HitGroupContent.objects.get(group_id=hit_group_id)
        if RequesterProfile.objects.filter(requester_id=hit_group.requester_id,
            is_public=False):
            raise HitGroupContent.DoesNotExist()
    except HitGroupContent.DoesNotExist:
        messages.info(request, 'Hitgroup with id "{0}" was not found!'.format(
            hit_group_id))
        return redirect('haystack_search')

    params = {'hit_group': hit_group}
    return direct_to_template(request, 'main/hit_group_content.html', params)


@never_cache
def hit_group_details(request, hit_group_id):

    try:
        hit_group = HitGroupContent.objects.get(group_id=hit_group_id)
        if RequesterProfile.objects.filter(requester_id=hit_group.requester_id,
            is_public=False):
            raise HitGroupContent.DoesNotExist()
    except HitGroupContent.DoesNotExist:
        messages.info(request, 'Hitgroup with id "{0}" was not found!'.format(
            hit_group_id))
        return redirect('haystack_search')

    try:
        hit_group_class = HitGroupClass.objects.get(group_id=hit_group_id)
    except ObjectDoesNotExist:
        # TODO classification should be done on all models.
        hit_group_class = None
        try:
            with open(settings.CLASSIFIER_PATH, "r") as file:
                classifier = NaiveBayesClassifier(
                        probabilities=json.load(file)
                    )
                classified = classifier.classify(hit_group)
                most_likely = classifier.most_likely(classified)
                document = classified["document"]
                hit_group_class = HitGroupClass(
                        group_id=document.group_id,
                        classes=most_likely,
                        probabilities=classified["probabilities"])
                hit_group_class.save()
        except IOError:
            # We do not want make hit group details page unavailable when
            # classifier file does not exist.
            pass

    if hit_group_class is not None:
        hit_group_class_label = NaiveBayesClassifier.label(
                hit_group_class.classes
            )
    else:
        hit_group_class_label = NaiveBayesClassifier.label()

    params = {
        'multichart': False,
        'columns': HIT_DETAILS_COLUMNS,
        'title': '#Hits',
        'class': hit_group_class_label,
    }

    def hit_group_details_data_formater(input):
        for cc in input:
            yield {
                'date': cc['start_time'],
                'row': (str(cc['hits_available']),),
            }

    dicts = query_to_dicts(
                """ select start_time, hits_available from hits_mv
                    where group_id = '{}' order by start_time asc """
                .format(hit_group_id))
    data = hit_group_details_data_formater(dicts)
    params['date_from'] = hit_group.occurrence_date
    params['date_to'] = datetime.datetime.utcnow()
    params['data'] = data
    params['hit_group'] = hit_group
    return direct_to_template(request, 'main/hit_group_details.html', params)


class GeneralTabEnum:
    """Describes available tabs on the general view."""

    __metaclass__ = EnumMetaclass

    ALL = 0
    HITS = 1
    REWARDS = 2
    PROJECTS = 3
    SPAM = 4

    ENUM_FIELDS = EnumMetaclass.ENUM_FIELDS + ['urls']
    EXTRA_FIELDS = {
        'urls': lambda d: dict([
            (v, reverse('graphs_general', kwargs={'tab_slug': slug}))
            for v, slug in d['slugs'].items()])
    }

    display_names = {
        ALL: 'General data',
        HITS: 'HITs'
    }

    data_set_processor = {
        ALL: lambda x: x,
        HITS: lambda x: general_tab_data_formatter(0, x),
        REWARDS: lambda x: general_tab_data_formatter(1, x),
        PROJECTS: lambda x: general_tab_data_formatter(2, x),
        SPAM: lambda x: general_tab_data_formatter(3, x),
    }

    graph_columns = OrderedDict([
        ('date', ('date', 'Date')),
        (HITS, ('number', '#HITs')),
        (REWARDS, ('number', 'Rewards($)')),
        (PROJECTS, ('number', '#Projects')),
        (SPAM, ('number', '#Spam Projects')),
    ])

    @classmethod
    def get_graph_columns(cls, tab):
        if tab == cls.ALL:
            return tuple(cls.graph_columns.values())
        return (cls.graph_columns['date'], cls.graph_columns[tab])

    @classmethod
    def get_tab_title(cls, tab):
        return cls.display_names[tab]


class ArrivalsTabEnum:
    """Describes available tabs on the general view."""

    __metaclass__ = EnumMetaclass

    ALL = 0
    ARRIVALS = 1
    COMPLETED = 2

    ENUM_FIELDS = EnumMetaclass.ENUM_FIELDS + ['urls']
    EXTRA_FIELDS = {
        'urls': lambda d: dict([
            (v, reverse('graphs_arrivals', kwargs={'tab_slug': slug}))
            for v, slug in d['slugs'].items()])
    }

    display_names = {
        ALL: 'Arrivals + Completitions'
    }

    data_set_processor = {
        ALL: lambda x: model_fields_formatter(
            ['arrivals', 'arrivals_value', 'processed', 'processed_value'], x),
        ARRIVALS: lambda x: model_fields_formatter(
            ['arrivals', 'arrivals_value'], x),
        COMPLETED: lambda x: model_fields_formatter(
            ['processed', 'processed_value'], x),
    }

    graph_columns = OrderedDict([
        ('date', [('date', 'Date')]),
        (ARRIVALS, [('number', '#HIT arrived'),
                    ('number', 'Reward arrived($)')]),
        (COMPLETED, [('number', '#HIT completed'),
                     ('number', 'Reward completed($)')]),
    ])

    @classmethod
    def get_tab_title(cls, tab):
        return cls.display_names[tab]

    @classmethod
    def get_graph_columns(cls, tab):
        if tab == cls.ALL:
            return tuple(chain(*cls.graph_columns.values()))
        return tuple(chain(cls.graph_columns['date'] + cls.graph_columns[tab]))
