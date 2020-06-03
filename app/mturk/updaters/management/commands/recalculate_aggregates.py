import time
import logging

from optparse import make_option
from django.db.models import F
from django.core.management import call_command
from django.conf import settings

from utils.management.commands.base.crawl_updater import CrawlUpdaterCommand
from utils.sql import execute_sql


class Command(CrawlUpdaterCommand):

    help = ("Clears aggregates for the given time period and calls appropriate"
        "commands to re-generate them.")

    log = logging.getLogger('mturk.aggregates')

    option_list = CrawlUpdaterCommand.option_list + (
        make_option("--skip-existing", dest="skip-existing", default=False,
            action="store_true",
            help='If True, related table entries will be deleted.'),
        make_option("--dont-chunk", dest="dont-chunk", default=False,
            action="store_true",
            help=('If True, all related objects for that period will be'
                'deleted before proceeding.')),
    )

    display_name = 'aggregates recaltulation'
    pid_file = 'mturk_aggregates_updater'
    crawls = 1
    overlap = 0
    chunk_size = 10

    def process_options(self, options):
        """Calls the parent process_options to have CrawlUpdaterCommand and
        TimeArgsCommand options populated.

        Additionally sets the following options on the instance:
        * clear_existing
        * chunk_delete

        """
        self.options = super(Command, self).process_options(options)
        self.clear_existing = not self.options['skip-existing']
        self.chunk_delete = not self.options['dont-chunk']
        return self.options

    def filter_crawls(self, crawls):
        """Filter crawls, excluding incomplete crawls."""
        return crawls.filter(groups_downloaded__gt=F('groups_available') *
            settings.INCOMPLETE_CRAWL_THRESHOLD)

    def prepare_data(self):
        """Called before any data sie queries. This is the bulk delete option,
        removing records before start of processing.

        """
        if self.clear_existing and not self.chunk_delete:
            self.clear_past_results(self.start, self.end)

    def process_chunk(self, start, end, chunk):
        """Called when chunk of data should be processed.
        Removes existing records if such option was provided and re-populates
        the aggregates.

        """
        if self.clear_existing and self.chunk_delete:
            self.clear_past_results(start, end)
        self.call_command_verbose('db_refresh_mviews', **{'force': True,
            'start': start, 'end': end, 'clear-existing': False})
        self.call_command_verbose('db_update_agregates', **{'start': start,
            'end': end, 'clear-existing': False})
        return True

    def clear_past_results(self, start, end):
        """Removes records from hits_mv and main_crawlaggregates tables matching
        the given time period.

        """
        q = "DELETE FROM {0} where start_time BETWEEN '{1}' AND '{2}';"
        for table in ['hits_mv', 'main_crawlagregates']:
            st = time.time()
            self.log.info('Deleting rows from {0} where start_time between {1}'
                ' and {2}.'.format(table, start, end))
            execute_sql(q.format(table, start, end), commit=True)
            self.log.info('{0}s elapsed.'.format(time.time() - st))

    def call_command_verbose(self, command, *args, **kwargs):
        """Calls management commands printing the name and time elapsed."""
        t = time.time()
        self.log.info('Starting {0}.'.format(command))
        res = call_command(command, *args, **kwargs)
        self.log.info('{0} took {1}s.'.format(command, time.time() - t))
        return res
