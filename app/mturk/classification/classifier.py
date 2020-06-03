""" Simple HIT group classification algorithm based on keywords analysis. """

import re
import string

from math import log
from unidecode import unidecode
from utils.enum import EnumMetaclass


class Labels:
    # I'm adding the enum to have easy access to display_names tuples.
    # TODO: refactor - replace the references to definitions below with this
    # enum.

    __metaclass__ = EnumMetaclass

    # TODO: rename this to NO_LABEL and remove explicit display_names below
    NO_LABEL = 1
    AUDIO = 2
    VIDEO = 4
    GRAPHICS = 8
    TEXT = 16
    INTERNET = 32
    COMPUTER = 64
    SURVEY = 128


NOLABEL = 1
AUDIO = 2
VIDEO = 4
GRAPHICS = 8
TEXT = 16
INTERNET = 32
COMPUTER = 64
SURVEY = 128

LABELS = {
    NOLABEL: "no label",
    AUDIO: "audio",
    VIDEO: "video",
    GRAPHICS: "graphics",
    TEXT: "text",
    INTERNET: "internet",
    COMPUTER: "computer",
    SURVEY: "survey",
}


# XXX nasty workaround
class EmptyBatchException(Exception):
    """There is no possibility to know if the batch of
    documents is empty. It is useful in management command
    that feeds classifier with batches of documents."""
    pass


class DocumentClassifier(object):

    # TODO complete this list.
    WORDS = set((
                # Prepositions
                "aboard", "about", "above", "across", "after", "against",
				"along", "amid", "among", "anti", "around", "as", "at",
				"before", "behind", "below", "beneath", "beside", "besides",
				"between", "beyond", "but", "by", "concerning", "considering",
				"despite", "down", "during", "except", "excepting",
				"excluding", "following", "for", "from", "in", "inside",
				"into", "like", "minus", "near", "of", "off", "on", "onto",
				"opposite", "outside", "over", "past", "per", "plus",
				"regarding", "round", "save", "since", "than", "through", "to",
				"toward", "towards", "under", "underneath", "unlike", "until",
				"up", "upon", "versus", "via", "with", "within", "without",

                # Conjunctions
                "although", "and", "far", "if", "long", "soon", "though",
                "well", "because", "both", "either", "even", "how", "however",
                "only", "case", "order", "that", "neither", "nor", "now",
                "once", "or", "provided", "rather", "so", "till", "unless ",
                "when", "whenever", "where", "whereas", "wherever", "whether",
                "while", "yet",

                # Articles
                "the", "a", "an", "some",

                # Other
                "i", "you", "he", "she", "it", "we", "they",
                "me", "your", "him", "her", "its", "us", "your", "them",
                "my", "your", "their", "our",
        ))

    NUMBER = re.compile(r"^\d+$")

    @classmethod
    def isvalid(cls, keyword):
        return keyword not in cls.WORDS and not cls.NUMBER.search(keyword)

    @classmethod
    def keywords(cls, document):
        result = set()

        # TODO replace this with one consistent way to get document attributes.
        try:
            merged = [document.title, document.description, document.keywords]
        except AttributeError:
            merged = [document["title"], document["description"],
                      document["keywords"]]

        for keywords in merged:
            # Strip unicode characters, punctuation, etc.
            stripped =  string.translate(unidecode(keywords),
                                         string.maketrans("", ""),
                                         string.punctuation)
            # Split string into separate lowecase words.
            splitted = map(string.lower, stripped.split())
            # Filter out unwanted words.
            filtered = filter(cls.isvalid, splitted)
            result.update(filtered)
        return result

    @classmethod
    def increment(cls, dictionary, key, default_value=0):
        value = dictionary[key] = dictionary.get(key, default_value) + 1
        return value

    @classmethod
    def label(cls, l=0):
        # Sometimes l is not an integer (may be string?).
        return LABELS.get(int(l), LABELS[NOLABEL])

    def __init__(self, *args, **kwargs):
        super(DocumentClassifier, self).__init__()
        training_set = kwargs.get('training_set', None)
        prior = kwargs.get('prior', None)
        posterior = kwargs.get('posterior', None)
        probabilities = kwargs.get('probabilities', None)
        if training_set:
            self.probabilities = self.train(training_set)
        elif prior and posterior:
            self.probabilities = prior, posterior
        elif probabilities:
            self.probabilities = probabilities
        else:
            raise Exception("Improperly configured")

    def __call__(self, doc_or_batch):
        if isinstance(doc_or_batch, (tuple, list)):
            return self.classify_batch(doc_or_batch)
        return self.classify(doc_or_batch)

    def classify(self, document):
        raise NotImplementedError

    def classify_batch(self, documents):
        raise NotImplementedError

    def train(self, training_set):
        raise NotImplementedError


class NaiveBayesClassifier(DocumentClassifier):
    """ Classifies documents using Naive Bayes Cassification.
    """

    EPSILON = 1E-5

    @classmethod
    def most_likely(cls, result, num=1):
        prob = result["probabilities"]
        if not prob:
            return 0
        _compare = lambda k1, k2: k1 if prob[k1] > prob[k2] else k2
        return reduce(_compare, prob)

    def classify(self, document):
        """ Classifies a single document """
        prior, posterior = self.probabilities
        result = {}
        for keyword in self.keywords(document):
            probability = posterior.get(keyword, {})
            if not probability:
                continue
            minimal = min(probability.values())
            if self.EPSILON < minimal:
                minimal = self.EPSILON
            else:
                minimal /= 10.0
            for label in prior:
                probability[label] = probability.get(label, self.EPSILON)
            for label in probability:
                result[label] = result.get(label, 0) + log(probability[label])
        for label, value in result.items():
            value += log(prior[label])
        if not result:
            result = {NOLABEL: 0.0}
        return {"document": document, "probabilities": result}

    def classify_batch(self, documents):
        """ Classifies a batch od documents. """
        # TODO it is a nasty workaround...
        i = 0
        for document in documents:
            i += 1
            yield self.classify(document)
        if i == 0:
            raise EmptyBatchException

    def train(self, training_set):
        """ Calculates a prior probability of each label occurrence and a
            posterior probability of occurrence each word in a particular
            label.
        """
        # A prior probablity is stored as a dictionary which keys are
        # labels strings and values are calculated probabilities of
        # label occurrence. A posterior probability is stored as a dictionary
        # which keys are words strings with associated dictionaries that holds
        # conditional probability of word occurrence in a particular label.
        prior, posterior = {}, {}
        # Each word occurrences in the training set.
        occurrences = {}
        for test in training_set:
            # Each training entry is tuple storing a document and associated
            # label.
            document, label = test
            # Increase a number of this label occurrences.
            self.increment(prior, label)
            # For each word in the training document, calculate probability
            # of the word occurrence with the label.
            for keyword in self.keywords(document):
                probability = posterior.get(keyword, {})
                self.increment(probability, label)
                posterior[keyword] = probability
                self.increment(occurrences, keyword)
        # Divide each occurrences number to get probability value.
        for keyword, value in posterior.items():
            for label in posterior[keyword]:
                value[label] /= float(occurrences[keyword])
        num_labels = sum(prior.values())
        for label, value_ in prior.items():
            value_ /= float(num_labels)
        return prior, posterior
