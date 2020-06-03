import logging
import resource

from datetime import datetime, timedelta
from optparse import make_option

from dateutil.parser import parse
from django.core.management.base import BaseCommand
from django.db.models import Max, Min

from utils.sql import execute_sql
from mturk.main.models import HitGroupClassAggregate, Crawl


# Set limit for avaliable resources.
resource.setrlimit(resource.RLIMIT_AS, (2048 * 1048576L, -1L))
logger = logging.getLogger(__name__)


class CalculateClassAggregates(BaseCommand):

    option_list = BaseCommand.option_list + (
        make_option("--clear-all", dest="clear_all",
                    action="store_true", default=False,
                    help=u"clears all existing aggregates and exists"),
        make_option("--clear-existing", dest="clear_existing",
                    action="store_true", default=False,
                    help=u"replaces existing aggregates"),
        make_option("--begin", dest="begin",
                    action="store", default=None,
                    help=u"specifies time interval"),
        make_option("--end", dest="end",
                    action="store", default=None)
    )

    def handle(self, *args, **options):

        if options["clear_all"]:
            logger.info("Removing all existing classification aggregates")
            # HitGroupClassAggregate.objects.all().delete()
            execute_sql('DELETE FROM main_hitgroupclassaggregate;', commit=True)
            return

        begin = options["begin"]
        end = options["end"]

        # If the end of the time interval is not specified compute aggregates
            # up to now.
        end = datetime.now() if end is None else parse(end)
        # If the begining of the time interval is not specified compute
        # from last existing aggregates.
        if begin is None:
            aggregate = HitGroupClassAggregate.objects.aggregate(Max('start_time'))
            start_time = aggregate['start_time__max']
            if start_time is None:
                aggregate = Crawl.objects.aggregate(Min('start_time'))
                start_time = aggregate['start_time__min'] + timedelta(seconds=1)
            else:
                start_time += timedelta(seconds=1)
            if start_time is not None:
                begin = start_time
            else:
                logger.warn("No crawls for processing")
                return
        else:
            begin = parse(begin)

        begin = begin.replace(tzinfo=None)
        end = end.replace(tzinfo=None)

        queryset = HitGroupClassAggregate.objects.filter(start_time__gte=begin,
                                                         start_time__lt=end)
        if options["clear_existing"]:
            queryset.delete()

        if queryset.exists():
            logger.error("Some of aggreagates are already calucated for a "
                         "given time interval")
            return

        logger.info("Calculating hit group class aggregates from {} to {} "
                    "with 1-hour intervals"
                    .format(begin, end, ))

        chunk_begin = begin
        chunk_end = begin + timedelta(hours=1)

        query_template = """
                INSERT INTO
                    main_hitgroupclassaggregate
                    (
                        crawl_id,
                        start_time,
                        classes,
                        hits_available
                    )
                SELECT
                    crawl_id,
                    start_time,
                    classes,
                    sum(hits_available) as hits_available
                FROM hits_mv
                JOIN main_hitgroupclass
                ON hits_mv.group_id = main_hitgroupclass.group_id
                WHERE
                    start_time >= '{}' AND
                    start_time < '{}'
                GROUP BY
                    crawl_id,
                    start_time,
                    classes;
            """
        while (chunk_end < end):
            logger.info("Processing chunk of crawls from {} to {}"
                        .format(chunk_begin, chunk_end))
            query = query_template.format(chunk_begin, chunk_end)
            execute_sql(query, commit=True)
            chunk_begin = chunk_end
            chunk_end += timedelta(hours=1)

        if chunk_begin < end:
            query = query_template.format(chunk_begin, end)
            execute_sql(query, commit=True)

        logger.info("Hit group class aggregates are made")


Command = CalculateClassAggregates
