from django.db.models import Q

from tenclouds.crud.qfilters import ChoicesFilter, Filter, Group
from tenclouds.crud.resources import ModelResource


class SearchResource(ModelResource):
    """Modifies ModelResource to allow searching over dedicated search fields.

    Since it's not possible to sort over indexes' tokenized fields in Haystack
    additional sorting fields are introduced. To keep this fact invisible from
    the front-end api, mapping of field-to-search_field is necessary.

    """

    search_ordering_fields_map = None
    """A dictionary mapping regular field to its sortable counterpart
    (optional).

    """

    def __convert_ordering(self, ordering, mapping):
        """Converts order_by '-'-prefix-able sorters according to a mapping."""
        if isinstance(ordering, basestring):
            ordering = [ordering]
        new_ordering = []
        for orderer in ordering:
            # get filter name stripping '-' if exists
            inverted = orderer.startswith('-')
            name = orderer[1:] if inverted else orderer
            # get new name if required
            if name in mapping:
                orderer = mapping[name]
                orderer = '-' + orderer if inverted else orderer
            new_ordering.append(orderer)
        return new_ordering

    def __api_ordering_to_search_ordering(self, params):
        """Map filter field names to respective sortable field names using
        self.Meta.search_ordering_fields_map.

        """
        # if nothing to map or no mapping, exit
        if ('order_by' not in params or
            not getattr(self.Meta, 'search_ordering_fields_map', None)):
            return params

        new_order_by = self.__convert_ordering(
            dict(params).get('order_by'), self.Meta.search_ordering_fields_map)
        if new_order_by != params['order_by']:
            try:
                params['order_by'] = new_order_by
            except AttributeError:
                params = dict(params, order_by=new_order_by)
        return params

    def __search_ordering_to_api_ordering(self, orderings):
        """Map sortable fields to respective filter fields names using
        self.Meta.search_ordering_fields_map.

        """
        # if nothing to map or no mapping is defined, exit
        if not (orderings and getattr(self.Meta, 'search_ordering_fields_map')):
            return orderings
        reverse_map = dict([(v, k) for
            k, v in self.Meta.search_ordering_fields_map.items()])
        return self.__convert_ordering(orderings, reverse_map)

    def get_ordering(self, request):
        """Called to get a list of ordering parameters to pass to the queryset.

        """
        params = super(SearchResource, self).get_ordering(request)
        params = self.__api_ordering_to_search_ordering(params)
        return params

    def get_ordering_in_api_names(self, ordering):
        """Called to get ordering sent together with the request."""
        ordering = super(SearchResource, self).get_ordering_in_api_names(ordering)
        ordering = self.__search_ordering_to_api_ordering(ordering)
        return ordering

    def build_schema(self):
        """Filter out all sorting-dedicated fields from schema's fieldsSortable
        so that they won't be automatically added to the sorting widget.

        """
        res = super(SearchResource, self).build_schema()
        if ('fieldsSortable' in res and
                getattr(self.Meta, 'search_ordering_fields_map')):
            bl = self.Meta.search_ordering_fields_map.values()
            f = lambda x: x not in bl and x[1:] not in bl
            res['fieldsSortable'] = filter(f, res['fieldsSortable'])
        return res


class MultiFieldChoiceFilter(ChoicesFilter):
    """Allows filtering over a number of fields on an object that have a similar
    name pattern.

    Keyword arguments:
    choices -- (key, display_name) pairs as in ChoicesFilter
    filter_attr -- name of the filter on the SomeResource
    field_template -- template to format with choice key used for querying

    Why do this? Example:

    Imagine there is a database index with label_* fields. They don't have to
    be mapped at all to then index, just be there, but let's say it looks like:

    class SomeIndex(indexes.SearchIndex, indexes.Indexable)
        label_0 = indexes.IntegerField(..)
        label_1 = indexes.IntegerField(..)
        label_2 = indexes.IntegerField(..)

    Then, filtering over labels can can be defined the following way:

    class SomeResource(resources.ModelResource):
        ...
        class Meta:
            filters = (
                Group('Labels',
                    MultiFieldChoiceFilter(
                        Labels.display_choices,
                        'labels', 'label_{}__exact'
                    ),
                    join='or'
                ),
            )

    """

    def __init__(self, choices, filter_attr, field_template):
        self.choices = choices
        self.filter_attr = filter_attr
        self.field_template = field_template

    def filter_fields(self, request):
        for choice, choice_name in self.choices:
            query = Q(**{self.field_template.format(choice): unicode(choice)})
            field = {self.filter_attr: choice}
            yield Filter(choice_name, query=query, **field)


class InactiveFilterGroup(Group):
    """Group that will perform no queries regardless of Fields passed.

    Used to have the filteres rendered and included in the requests, but
    suppressing their normal behaviour to perform the queries elsewhere.

    """
    def apply_filters(self, request, query, filter_keys):
        return query


class FulltextSearchGroup(Group):
    """Filter group designed to contain a single FullTextSearch control to use
    for searching, that can be made aware of some other Filter containing names
    of the fields to search in.

    Currently, any filter contained by this group will have it's ``filters``
    property changed to reflect the selected search_in parameters (the selected
    or all if no selection is specified).

    """
    filter_query = '{}__icontains'
    """Query to use when searching in fields."""

    def __init__(self, name, *fields, **kwargs):
        self.name = name
        self.fields = fields
        # I don't think 'and' joiner will be of any use here, nor will it work
        # without extra work on the filter (FullTextSearch filter implies an OR
        # query by default.
        assert kwargs.get('join') is not 'and', 'And joiner is not implemented!'
        self.query_joiner = 'or'
        #self.query_joiner = kwargs.get('join', 'and')

        self.search_in_field = kwargs.get('search_in_field')
        self.search_in_values = kwargs.get('search_in_values')
        assert self.search_in_field, 'Please specify search_in kwargs.'
        assert self.search_in_values, 'Please specify a search_in_values kwarg.'

        if self.query_joiner not in ['and', 'or']:
            raise TypeError('Unknown query joiner: %s' % self.query_joiner)

    def __add_search_in_to_filters(self, filter_keys, filters):
        """Alters filter's default ``filters`` property."""
        # get search in field names
        search_in = [f.split(':') for f in filter_keys if ':' in f]
        search_in = [f[1] for f in search_in
            if f[0] == self.search_in_field and len(f) > 1]

        # apply search is all search_in_values if none is specified
        if not search_in:
            search_in = self.search_in_values

        # add search_in to filter's inner filters
        for fk in filters:
            fk[0].filters = [self.filter_query.format(si) for si in search_in]

        return filters

    def apply_filters(self, request, query, filter_keys):
        """This only differs from the original by __add_search_in_to_filters
        call.

        """
        filters = ((self.filter_by_key(key, request), key)
                   for key in filter_keys)
        filters = [(f, k) for f, k in filters if f]

        if not filters:
            return query

        # handle search_in
        self.__add_search_in_to_filters(filter_keys, filters)

        # filter using AND
        if self.query_joiner == 'and':
            for f, key in filters:
                query = query.filter(f.build_filters(key))
            return query

        # filter using OR
        elif self.query_joiner == 'or':
            q = None
            for f, key in filters:
                if q is None:
                    q = f.build_filters(key)
                else:
                    q |= f.build_filters(key)
            if q:
                query = query.filter(q)
            return query

        raise TypeError('Unknown query joiner: %s' % self.query_joiner)
