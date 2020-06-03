from itertools import izip
from django.db import connection, transaction


def query_to_dicts(query_string, *query_args):
    """Run a simple query and produce a generator
    that returns the results as a bunch of dictionaries
    with keys for the column values selected.
    """
    cursor = connection.cursor()
    cursor.execute(query_string, query_args)
    col_names = [desc[0] for desc in cursor.description]
    while True:
        row = cursor.fetchone()
        if row is None:
            break
        row_dict = dict(izip(col_names, row))
        yield row_dict
    return


def query_to_tuples(query_string, *query_args):
    """Run a simple query and produce a generator
    that returns the results as a bunch of tuples
    column values selected as subsequent values.
    """
    cursor = connection.cursor()
    cursor.execute(query_string, query_args)
    while True:
        row = cursor.fetchone()
        if row is None:
            break
        yield row
    return


def query_to_lists(query_string, *query_args):
    cursor = connection.cursor()
    cursor.execute(query_string, query_args)
    while True:
        row = cursor.fetchone()
        if row is None:
            break
        yield list(row)
    return


def execute_sql(query_string, *query_args, **kwargs):
    """Executes given query providing positional args as query arguments.

    Keyword arguments:
    query_string -- query to execute
    query_args -- positional arguments are passed on as query arguments
    commit -- specify commit=True keyword argument if you want the commit to be
    called after query

    """
    cursor = connection.cursor()
    # empty tuple results in 'tuple index out of range'
    query_args = query_args if len(query_args) > 0 else None
    cursor.execute(query_string, query_args)

    if kwargs.get('commit'):
        transaction.commit_unless_managed()

    return cursor


def exists(query_string, *query_args):
    cursor = execute_sql(query_string, query_args)
    return cursor.fetchone() is not None


def get_table_columns(table_name, with_data_type=False):
    """Returns list or dictionary of column names of a table.

    Keyword arguments:
    table_name -- table to query for
    with_data_type -- should the data tyle be returned
    """

    qq = query_to_tuples("select column_name%s from "
        "information_schema.columns where table_name='%s'" % (
            ', data_type' if with_data_type else '',
            table_name))
    return dict(qq) if with_data_type else [q[0] for q in qq]


def table_exists(table_name):
    """Returns true if a table with the given name exists."""
    return exists("select * from pg_tables where tablename = '{0}';".format(
        table_name))


def add_table_columns(table_name, columns):
    """Adds columns to a table. Does not check their existence.

    Keyword arguments:
    table_name -- table to add columns to
    columns -- list of tuples (column_name, column_type)

    """
    for c in columns:
        q = 'alter table "{0}" add column "{1}" {2};'.format(
            table_name, *c)
        execute_sql(q)
    transaction.commit_unless_managed()
