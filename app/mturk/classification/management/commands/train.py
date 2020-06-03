import json
import logging
import resource
import sys

from optparse import make_option
from django.core.management.base import BaseCommand

from mturk.main.models import HitGroupContent
from mturk.classification import NaiveBayesClassifier


# Set limit for avaliable resources.
resource.setrlimit(resource.RLIMIT_AS, (2048 * 1048576L, -1L))
logger = logging.getLogger(__name__)

class TrainCommand(BaseCommand):

    option_list = BaseCommand.option_list + (
        make_option('--training-set-path', dest='training_set_path', 
                    action='store',
                    help=u'path to the training json data'),
        make_option('--classifier-path', dest='classifier_path', 
                    action='store',
                    help=u'path to the resultant classifier json '
                    'configuration file'),
    )

    def handle(self, *args, **options):

        objects = []
        with open(options['training_set_path'], 'r') as file:
            objects = json.load(file)
        logger.info('Fetching documents from a database')
        models = HitGroupContent.objects.filter(group_id__in=objects)
        training_set = map(lambda m: (m, objects[m.group_id]), models)
        logger.info('Trainig classificator')
        classifier = NaiveBayesClassifier(training_set=training_set)
        output_path = options['classifier_path']
        if output_path:
            with open(output_path, 'w') as file:
                json.dump(classifier.probabilities, file, ensure_ascii=True, indent=4)
        else:
            json.dump(classifier.probabilities, sys.stdout,
                      ensure_ascii=True, indent=4)
        logger.info('Done')


Command = TrainCommand
