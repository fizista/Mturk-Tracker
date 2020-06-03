import time
import datetime
import pytz


from django.utils.timezone import now, make_aware
from django.conf import settings

from mturk.main.models import Crawl, HitGroupContent


def pad_string(s, l):
    return str(s) + ((l - len(str(s))) * ' ')


def print_crawls(age=datetime.timedelta(hours=2), sleep=15, limit=None):
    """Script for displaying latest crawls and their details."""

    header = [
        '-----------------------------------------------------------',
        'Time           | mins  | avail | down  | objs  | missing % ',
        '-----------------------------------------------------------',
    ]
    while True:
        crawls = Crawl.objects.filter(start_time__gt=now() - age
            ).order_by('start_time')
        if limit:
            crawls = crawls[:limit]

        to_print = list(header)

        lencrawls = len(crawls)
        for i, c in enumerate(crawls):
            dev = 'error'
            disp = 'error'
            if (c.groups_available > 0 and c.groups_downloaded is not None):
                dev = float(c.groups_downloaded) / c.groups_available
                th = settings.INCOMPLETE_CRAWL_WARNING_THRESHOLD
                disp = int((1 - dev) * 100)
                if c.groups_available == c.groups_downloaded:
                    if i != lencrawls - 1:
                        # if it's not the latest it can't be running
                        disp = 'crashed'
                    else:
                        disp = 'running'
                else:
                    disp = '{0}%'.format(disp) + (' err' if dev < th else '')
            if c.end_time == c.start_time:
                end_time = now()
            else:
                end_time = c.end_time
            elapsed = round(
                float((end_time - c.start_time).total_seconds()) / 60, 1)
            to_display = [
                c.start_time.strftime('%y-%m-%d %H:%M'),
                pad_string(elapsed, 5),
                pad_string(c.groups_available, 5),
                pad_string(c.groups_downloaded, 5),
                pad_string(c.hitgroupstatus_set.count(), 5),
                disp,
            ]
            to_print.append(' | '.join(map(str, to_display)))
        for r in to_print:
            print r
        time.sleep(sleep)


def get_unavailable_group_ids_percent(period=30, periods=40):
    results = []
    today = now().date()
    today -= datetime.timedelta(days=today.day)
    for dt in datetime_range(today, period=period, periods=periods):
        dte = dt + datetime.timedelta(days=period)
        items = HitGroupContent.objects.filter(
            first_crawl__start_time__gt=dt, first_crawl__start_time__lt=dte
            ).only('group_id_hashed')
        hashed = len([i for i in items if i.group_id_hashed])
        percent = float(hashed) / len(items) * 100 if len(items) != 0 else 0
        results.append((dt, percent))
        print "{0} {1}".format(*results[-1])
    return results


def get_first_crawl_hits_posted_sums(days=200):
    results = []
    for i, dt in enumerate(datetime_range(now().date(), periods=days), start=1):
        tt = time.time()
        result = sum([
            sum([
                crawl.hitgroupstatus_set.get(hit_group_content__id=content.id
                ).hits_available for content in crawl.hitgroupcontent_set.all()
            ]) for crawl in
                Crawl.objects.filter(
                    start_time__gt=dt,
                    start_time__lt=dt + datetime.timedelta(days=1))
        ])
        results.append((dt, result))
        print '{0}. {1} - {2}, {3}s elapsed'.format(
            i, dt, result, time.time() - tt)
    return results


def convert_date_to_aware_utc_datetime(dt):
    return make_aware(datetime.datetime.combine(dt, datetime.time(0)), pytz.UTC)


def datetime_range(start=now(), period=1, periods=30):
    return [convert_date_to_aware_utc_datetime(
            start - datetime.timedelta(days=period * x)) for x in range(periods)]
