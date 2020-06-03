import sys
import time
import logging
from optparse import make_option

from django.db import transaction
from django.core.management.base import BaseCommand
from django.conf import settings

from utils.pid import Pid
from utils.sql import query_to_tuples, execute_sql

log = logging.getLogger('mturk.aggregates')


class Command(BaseCommand):
    """Clears hits_mv, hits_temp and main_crawlagregates entries related to
    crawls with not enough hits_downloaded and sets has_hits_mv to null.

    Command can run in two modes:
    * simple -- removing related objects in a single statement per crawl
    * chunked -- back processing groups of crawls using 'in' comparison.

    """

    option_list = BaseCommand.option_list + (
        make_option("--limit", dest="limit", type="int",
            help="Number of crawls to process."),
        make_option("--count-only", dest="count-only",
            default=False, action="store_true",
            help="Command will print the number of records requiring"
            " processing and exit."),
        make_option("--chunk-size", dest="chunk-size", type="int",
            default=20000, help="Number of crawls in a chunk for the chunked "
            "delete mode. By default a 'big enough' number to fit the whole "
            "query, alter this if you want to split the query, but keep in "
            "mind it will all be slower overall."),
        make_option("--simple", dest="simple",
            default=False, action="store_true",
            help="Turns chunked delete off."),
        make_option("--all", dest="all", default=False, action="store_true",
            help="Decides if crawls with has_hits_mv=False should be included, "
            "use to filter out already processed records."),
        make_option("--fix-interrupted", dest="fix-interrupted", default=False,
            action="store_true",
            help="If this option is provided, the command will search for "
            "crawls having groups_downloaded = groups_available and set "
            "groups_downloaded to the count of actually created hitgroupstatus"
            " rows."),
    )
    help = "Removes data related to bad crawls."

    def handle(self, **options):

        self.start_time = time.time()

        log.info('Starting remove_bad_crawl_related, acquiring PID.')
        pid = Pid('remove_bad_crawl_related', True)

        self.having_hits_mv = not options.get('all')
        self.chunk_size = options.get('chunk-size')
        self.chunked = not options.get('simple')
        self.limit = options.get('limit')
        self.fix_interrupted = options.get('fix-interrupted')

        # check this before counting the crawls to delete
        self.fix_interrupted and self.update_interrupted_crawl_stats()

        self.crawl_count = self.get_crawls_count()

        if self.crawl_count == 0 or options.get('count-only'):
            self.handle_count_only()

        # if limit is specified, show X/Y instead of just Y
        log.info('Starting bad crawl related data removal, {0}{1} records will '
            'be processed.'.format(
                '{0}/'.format(self.limit) if self.limit else '',
                self.crawl_count))

        ids = self.get_crawl_ids()
        deleted = self.do_deletes(ids)

        log.info('Command took: {0}, {1} crawls processed.'.format(
            self.time_elapsed(), deleted))

        pid.remove_pid()

    def time_elapsed(self):
        return time.time() - self.start_time

    def handle_count_only(self):
        """Handles the count_only option."""
        log.info('{0} records to process.'.format(self.crawl_count))
        sys.exit(0)

    def get_crawl_ids(self):
        """Returns an iterator containing the ids of records to delete."""
        return [a for (a, ) in query_to_tuples(self.__get_crawls_query())]

    def get_crawls_count(self):
        """Counts the records to delete."""
        return [a for a in query_to_tuples(self.__get_crawls_query(
            count_only=True))][0][0]

    crawls_query = """
    SELECT {what} FROM main_crawl
    WHERE
        {having_hits_mv}
        groups_available * {crawl_threshold} > groups_downloaded
    {ordering}
    """

    def __get_crawls_query(self, what='id', ordered=True, count_only=False):
        if count_only:
            ordered = False
            what = 'count(*)'
        ordering = "ORDER BY start_time DESC" if ordered else ""
        hmv = 'has_hits_mv is true AND' if self.having_hits_mv else ''
        return self.crawls_query.format(what=what, ordering=ordering,
            having_hits_mv=hmv,
            crawl_threshold=settings.INCOMPLETE_CRAWL_THRESHOLD)

    #
    # Deleting
    #
    def do_deletes(self, *args, **kwargs):
        """Main function, performs crawl agregates delete, then moves to either
        simple or chunked delete.

        """

        log.info('Deleting crawl agregates.')
        self.delete_crawl_agregates(*args, **kwargs)

        log.info('Starting hits_mv and hits_temp rows delete.')
        if self.chunked:
            return self.do_deletes_chunked(*args, **kwargs)
        else:
            return self.do_deletes_simple(*args, **kwargs)

    def delete_crawl_agregates(self, ids):
        """This will be done separately, as it'a a much faster query with
        immediately visible effect.
        """
        qq = self.__get_delete_queries(['main_crawlagregates'], 'in').next()
        execute_sql(qq.format(self.__chunk_str(ids)))
        transaction.commit_unless_managed()

    def do_deletes_simple(self, ids):
        """Performs a query per crawl and per table."""
        qs = list(self.__get_delete_queries(['hits_mv', 'hits_temp'], '='))
        for i, crawl_id in enumerate(ids, start=1):
            if self.limit and i > self.limit:
                break
            for q in qs:
                execute_sql(q.format(crawl_id))
            if i % 10 == 0:
                log.info(("{0}/{1} crawls processed, {2}s elapsed so far."
                    ).format(i, self.crawl_count, self.time_elapsed()))
                transaction.commit_unless_managed()
            execute_sql(("update main_crawl set has_hits_mv = false where"
                " id = {0}").format(crawl_id))

        transaction.commit_unless_managed()
        return i

    def read_chunks(self, iterator, chunk_size=10, limit=None):
        """Returns a list of next ``chunk_size`` elements, up to ``limit``
        total from given ``iterator``.
        """
        items = list()
        for i, crawl_id in enumerate(iterator, start=1):
            if limit and i > limit:
                break
            items.append(crawl_id)
            if len(items) == chunk_size:
                yield items
                items = []
        if items:
            yield items

    def __chunk_str(self, ids):
        return "({0})".format(",".join([str(a) for a in ids]))

    def do_deletes_chunked(self, ids):
        """More complex version, does multiple crawls at a time."""
        processed = 0
        qs = list(self.__get_delete_queries(['hits_mv', 'hits_temp'], 'in'))
        for chunk in self.read_chunks(
                ids, limit=self.limit, chunk_size=self.chunk_size):
            chunk_str = self.__chunk_str(chunk)
            for q in qs:
                execute_sql(q.format(chunk_str))
            execute_sql(("update main_crawl set has_hits_mv = false where"
                " id in {0}").format(chunk_str))
            processed += len(chunk)
            log.info('Processed crawls: {0}, {1}/{2} in {3}s.'.format(
                chunk, processed, self.crawl_count, self.time_elapsed()))
            transaction.commit_unless_managed()

        return processed

    def __get_delete_queries(self, tables, comparator='='):
        """Returns delete queries for all related tables, cmparator argument can
        be used to get 'crawl_id =' or 'crawl_id in' queries.
        """
        for t in tables:
            yield "delete from {0} where crawl_id {1} {{0}};".format(
                t, comparator)

    recount_query = """
    UPDATE main_crawl c
      SET groups_downloaded = (
        SELECT count(*) FROM main_hitgroupstatus WHERE crawl_id = c.id)
      WHERE c.id in (
        SELECT id FROM main_crawl
        WHERE groups_downloaded = groups_available);
    """

    def update_interrupted_crawl_stats(self):
        """Checks for crawls that were interrupted before updating the number
        of downloaded hit groups.

        Currently those crawls can be found by checking for crawls having
        groups_downloaded = groups_available, since at the begining of the crawl
        those values are set to be equal.

        """
        log.info('--fix-interrupted specified, updating interrupted crawls to '
            'have groups_downloaded match the actual downloaded object count.')
        execute_sql(self.recount_query)
        transaction.commit_unless_managed()
