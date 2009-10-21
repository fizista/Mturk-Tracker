# -*- coding: utf-8 -*-

from django import template

register = template.Library()

def row_formater(input):
    for cc in input:
        date = cc['date']
        row = "new Date(%s,%s,%s,%s,%s)," % (date.year, date.month-1, date.day, date.hour, date.minute)
        row += ",".join(cc['row'])
        yield "["+row+"]"


@register.simple_tag
def google_timeline(context, columns, data):
    '''
    http://code.google.com/apis/visualization/documentation/gallery/annotatedtimeline.html
    '''
    return {'data':row_formater(data), 'columns':columns}

register.inclusion_tag('graphs/google_timeline.html', takes_context=True)(google_timeline)