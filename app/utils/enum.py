# -*- coding: utf-8 -*-

from django.template.defaultfilters import slugify


class EnumMetaclass(type):
    """Metaclass for enumerations.

    You must define the values having:
    * UPPERCASE names,
    * type in EnumMetaclass.ENUM_VALUE_TYPES (long, int or basestring).

    Generates:
    cls.names -- reverse dictionary mapping value to name
    cls.choices -- sorted list of (id, name) pairs suitable for model choices
    cls.display_choices -- as above, but with display_name instead of name
    cls.values -- list of values defined by the enumeration
    cls.trans_name -- reverse dictionary mapping value to string ready for
    translation
    cls.display_names -- cls.names items processed for display
    cls.slugs -- slugified versions of display_names
    cls.value_for_slug -- reverse mapping for the above
    cls.enum_dict -- dictionary containing all details for the value, this is:
    slug, name, display_name, trans_name and value,


    Overriding. To add additional fields use the following:
    EXTRA_FIELDS -- (plural_name, function(d)) pairs to add to the class
    ENUM_FIELDS -- fields to copy into enum_dict

    Example:
    class X(object):
        __metaclass__ = EnumMetaclass
        A = 1
        B = 2
        C = 3
        LONG_NAME = 4

    >>> X.names
    {1: 'A', 2: 'B', 3: 'C', 4: 'LONG_NAME'}

    >>> X.values
    [1, 2, 3, 4]

    >>> X.choices
    [(1, 'A'), (2, 'B'), (3, 'C'), (4, 'LONG_NAME')]

    >>> X.trans_names
    {1: 'X.A', 2: 'X.B', 3: 'X.C', 4: 'X.LONG_NAME'}

    >>> X.diplay_names
    {1: 'A', 2: 'B', 3: 'C', 4: 'Long name'}

    >>> X.diplay_choices
    [(1, 'A'), (2, 'B'), (3, 'C'), (4, 'Long name')]

    >>> X.slugs
    {1: 'a', 2: 'b', 3: 'c', 4: 'long-name'}

    >>> X.value_for_slug
    {'a': 1, 'b': 2, 'c': 3, 'long-name': 4}

    """

    ENUM_FIELDS = ['slugs', 'names', 'display_names', 'trans_names', 'urls']
    EXTRA_FIELDS = {}
    ENUM_VALUE_TYPES = [int, long, basestring]

    @classmethod
    def is_enum_variable(cls, name, val):
        """Decides if the given value should be considered an enum variable.

        By default this means the name is UPPERCASE_NAME and the type of the
        variable is one of the ENUM_VALUE_TYPES.

        """
        if not name.isupper():
            return False
        return any(isinstance(val, vtype) for vtype in cls.ENUM_VALUE_TYPES)

    def __new__(cls, name, bases, d):
        names = {}
        values = []
        trans_names = {}
        for x in d:
            if cls.is_enum_variable(x, d[x]):
                names[d[x]] = x
                values.append(d[x])
                trans_names[d[x]] = name + u"." + x
        d['names'] = names
        d['values'] = values
        d['trans_names'] = trans_names

        # create display names
        dn = lambda x: (x[0].title() + x[1:].lower()).replace('_', ' ')
        display_names = dict([(n[0], dn(n[1])) for n in d['names'].items()])
        # update with existing ones
        display_names.update(d.get('display_names', {}))
        d['display_names'] = display_names
        d['display_choices'] = map(lambda x: (x, d['display_names'][x]),
            sorted(d['values']))
        d['slugs'] = dict([(n[0], slugify(n[1]))
            for n in d['display_names'].items()])
        d['value_for_slug'] = dict([(n[1], n[0]) for n in d['slugs'].items()])

        # adding new fields
        for name, fun in d.get('EXTRA_FIELDS', cls.EXTRA_FIELDS).iteritems():
            d[name] = fun(d)

        d['enum_dict'] = dict([(v, {'value': v}) for v in values])
        for v in d['enum_dict']:
            for l in d.get('ENUM_FIELDS', cls.ENUM_FIELDS):
                if l in d and v in d[l]:
                    d['enum_dict'][v][l[:-1]] = d[l][v]

        return type.__new__(cls, name, bases, d)
