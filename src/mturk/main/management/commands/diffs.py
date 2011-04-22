'''
Copyright (c) 2009 Panagiotis G. Ipeirotis

Permission is hereby granted, free of charge, to any person
obtaining a copy of this software and associated documentation
files (the "Software"), to deal in the Software without
restriction, including without limitation the rights to use,
copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following
conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.

Initially designed and created by 10clouds.com, contact at 10clouds.com
'''
import sys
import time
import logging

from tenclouds.sql import execute_sql

log = logging.getLogger('__init__')


def hitgroups(cid):
    r = execute_sql("select distinct group_id from hits_mv where crawl_id = %s", cid)
    return [g[0] for g in r.fetchall()]



def last_crawlid():
    return execute_sql("select crawl_id from hits_mv order by crawl_id desc limit 1;").fetchall()[0][0]

def updatehitgroup(g, cid):
    prev = execute_sql("""select hits_available from hits_mv where crawl_id <
            %s and group_id = %s order by crawl_id desc limit 1;""", cid,
            g).fetchall()
    prev = prev[0] if prev else 0
    print "got, updating"
    st = time.time()
    execute_sql("""update hits_mv set hits_diff = hits_available - %s where
            group_id = %s and crawl_id = %s;""", prev, g, cid)
    print "updated in ", time.time() - st


def update_cid(cid):
    st = time.time()
    hgs = hitgroups(cid)
    l = float(len(hgs))
    for i, g in enumerate(hgs):
        print "processing", i / l
        updatehitgroup(g, cid)
    print "updated", time.time() - st


