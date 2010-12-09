#!/usr/bin/env python
# -*- coding: utf-8 -*-

import urllib2
import logging
from optparse import make_option

from django.conf import settings
from django.core.management.base import BaseCommand

from mturk.main.models import IndexQueue

log = logging.getLogger('main.solr_sync')


class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
            make_option('--verbose', dest='verbose', action='store_true'),
            make_option('--clean-queue', dest='clean_queue', action='store_true'),
    )

    def handle(self, *args, **options):
        if options.get('verbose', False):
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            handler.setLevel(logging.DEBUG)
            handler.setFormatter(formatter)
            log.addHandler(handler)

        if options.get('clean_queue', False):
            # remove rows from index queue and quit
            IndexQueue.objects.all().delete()
            return

        log.info('solr delta sync started')
        url = "%s/import_db_hits/?command=delta-import" % settings.SOLR_MAIN
        f = urllib2.urlopen(url)

        log.debug(f.read())

