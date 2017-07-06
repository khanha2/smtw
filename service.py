import collections
import urllib
from rdflib import Literal, RDF, RDFS


def local_name(t):
    r = t[max(t.rfind('/'), t.rfind('#')) + 1:]
    r = r.replace('%2F', '_')
    return r


def quote(l):
    if isinstance(l, str):
        l = l.encode('utf-8')
    return l


def find_label(t, graph, label_props):
    if isinstance(t, Literal): return str(t)
    for l in label_props:
        try:
            return next(graph.objects(t, l))
        except StopIteration:
            pass
    try:
        return urllib.unquote(local_name(t))
    except:
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
            types[o] = quote(local_name(o))
        resource_types[s].add(o)
    for t in types:
        resource_types[t].add(RDFS.Class)
    return types, resource_types


def find_resources(graph, types):
    resources = collections.defaultdict(dict)
    for t in types:
        resources[t] = {}
        for x in graph.subjects(RDF.type, t):
            resources[t][x] = quote(local_name(x))
    resources[RDFS.Class].update(types.copy())
    return resources


def get_label(app, r):
    try:
        return app.config['labels'][r]
    except:
        try:
            l = urllib.unquote(local_name(r))
        except:
            l = r
        app.config['labels'][r] = l
        return l
