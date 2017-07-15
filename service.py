import codecs
import collections
import subprocess
import urllib
import warnings

import itertools

import functools
from heapq import nsmallest
from operator import itemgetter

from flask import url_for, request, Response
from rdflib import Literal, RDF, RDFS, Graph, term
from rdflib.tools import rdf2dot

GRAPH_TYPES = {"png": "image/png",
               "svg": "image/svg+xml",
               "dot": "text/x-graphviz",
               "pdf": "application/pdf"}

DOT = 'dot'


def local_name(t):
    r = t[max(t.rfind('/'), t.rfind('#')) + 1:]
    r = r.replace('%2F', '_')
    return r


def quote(l):
    if isinstance(l, str):
        l = l.encode('utf-8')
    return l


def find_label(t, graph, label_props):
    if isinstance(t, Literal):
        return str(t)
    for l in label_props:
        try:
            return next(graph.objects(t, l))
        except StopIteration:
            pass
    try:
        return local_name(t)
    except Exception as e:
        print(e)
        return t


def find_labels(graph, resources, label_props):
    labels = {}
    for t, res in resources.items():
        for r in res:
            if r not in labels:
                labels[r] = find_label(r, graph, label_props)
    return labels


def find_types(graph):
    types = {}
    resource_types = collections.defaultdict(set)
    types[RDFS.Class] = local_name(RDFS.Class)
    types[RDF.Property] = local_name(RDF.Property)
    for s, p, o in graph.triples((None, RDF.type, None)):
        if o not in types:
            types[o] = local_name(o)
        resource_types[s].add(o)
    for t in types:
        resource_types[t].add(RDFS.Class)
    return types, resource_types


def find_resources(graph, types):
    resources = collections.defaultdict(dict)
    for t in types:
        resources[t] = {}
        for x in graph.subjects(RDF.type, t):
            resources[t][x] = local_name(x)
    resources[RDFS.Class].update(types.copy())
    return resources


def get_label(app, r):
    try:
        return app.config['labels'][r]
    except:
        try:
            l = local_name(r)
        except:
            l = r
        app.config['labels'][r] = l
        return l


def reverse_types(types):
    """Generate cache of localname=>type mapping"""
    rtypes = {}
    for t, l in types.items():
        while l in rtypes:
            warnings.warn(u"Multiple types for label '%s': (%s) rewriting to '%s_'" % (l, rtypes[l], l))
            l += "_"
        rtypes[l] = t
    return rtypes


def reverse_resources(resources):
    rresources = {}
    for t, res in resources.items():
        rresources[t] = {}
        for r, l in res.items():
            while l in rresources[t]:
                l += "_"
            rresources[t][l] = r
        resources[t].clear()
        for l, r in rresources[t].items():
            resources[t][r] = l
    return rresources


def get_resource_graph(graph, r, label_properties):
    sub_graph = Graph()

    for p, ns in graph.namespaces():
        graph.bind(p, ns)

    sub_graph += graph.triples((r, None, None))
    sub_graph += graph.triples((None, None, r))

    if 'notypes' not in request.args:
        add_type_labels(sub_graph, graph, label_properties)

    return graph


def add_type_labels(sub_graph, graph, label_properties):
    add_me = []
    for o in itertools.chain(sub_graph.objects(None, None), sub_graph.subjects(None, None)):
        if not isinstance(o, term.Node): continue
        add_me += list(graph.triples((o, RDF.type, None)))
        for l in label_properties:
            if (o, l, None) in graph:
                add_me += list(graph.triples((o, l, None)))
                break
    sub_graph += add_me


def lfu_cache(maxsize=100):
    '''Least-frequenty-used cache decorator.

    Arguments to the cached function must be hashable.
    Cache performance statistics stored in f.hits and f.misses.
    Clear the cache with f.clear().
    http://en.wikipedia.org/wiki/Least_Frequently_Used

    '''

    def decorating_function(user_function):
        cache = {}  # mapping of args to results
        use_count = collections.defaultdict(int)
        # times each key has been accessed
        kwd_mark = object()  # separate positional and keyword args

        @functools.wraps(user_function)
        def wrapper(*args, **kwds):
            key = args
            if kwds:
                key += (kwd_mark,) + tuple(sorted(kwds.items()))
            use_count[key] += 1

            # get cache entry or compute if not found
            try:
                result = cache[key]
                wrapper.hits += 1
            except KeyError:
                result = user_function(*args, **kwds)
                cache[key] = result
                wrapper.misses += 1

                # purge least frequently used cache entry
                if len(cache) > maxsize:
                    for key, _ in nsmallest(maxsize // 10, use_count.items(), key=itemgetter(1)):
                        try:
                            del cache[key], use_count[key]
                        except:
                            pass
            return result

        def clear():
            cache.clear()
            use_count.clear()
            wrapper.hits = wrapper.misses = 0

        wrapper.hits = wrapper.misses = 0
        wrapper.clear = clear
        return wrapper

    return decorating_function


def resolve(app, graph, types, resources, resource_types, r):
    if r is None:
        return {'url': None, 'realurl': None, 'label': None}
    if isinstance(r, Literal):
        return {'url': None, 'realurl': None, 'label': str(r), 'lang': r.language}
    local_url = None
    if types == {None: None}:
        if resource_types[r] in graph:
            local_url = url_for('resource', label=resources[None][r])
    else:
        for t in resource_types[r]:
            if t in types:
                try:
                    l = resources[t][r]
                    local_url = url_for('resource', type_=types[t], label=l)
                    break
                except KeyError:
                    pass
    types_ = [resolve(app, graph, types, resources, resource_types, t) for t in resource_types[r] if t != r]
    return {'external': not local_url,
            'url': local_url or r,
            'realurl': r,
            'label': get_label(app, r),
            'type': types_}


def get_rdf_graph(graph, format_):
    return dot(lambda uw: rdf2dot.rdf2dot(graph, stream=uw), format_)


#
# def graphrdfs(graph, format_):
#     return dot(lambda uw: rdfs2dot.rdfs2dot(graph, stream=uw), format_)

def dot(inputgraph, format_):
    if format_ not in GRAPH_TYPES:
        return "format '%s' not supported, try %s" % (format_, ", ".join(GRAPH_TYPES)), 415

    rankdir = request.args.get('rankdir', 'BT')
    p = subprocess.Popen([DOT, "-Grankdir=%s" % rankdir, "-T%s" % format_], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE)
    uw = codecs.getwriter('utf8')(p.stdin)
    inputgraph(uw)
    p.stdin.close()

    def read_resource():
        s = p.stdout.read(1000)
        while s != "":
            yield s
            s = p.stdout.read(1000)

    return Response(read_resource(), mimetype=GRAPH_TYPES[format_])
