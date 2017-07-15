from flask import Flask, render_template, redirect, request
from rdflib import URIRef, util, OWL

from converter import RDFUrlConverter
from service import *
from utils import *

app = Flask(__name__)

GRAPH_PATH = 'musicontology.rdf'

GRAPH_FORMAT = 'rdf'

LABEL_PROPERTIES = [RDFS.label,
                    URIRef("http://purl.org/dc/elements/1.1/title"),
                    URIRef("http://xmlns.com/foaf/0.1/name"),
                    URIRef("http://www.w3.org/2006/vcard/ns#fn"),
                    URIRef("http://www.w3.org/2006/vcard/ns#org")]

SECRET_KEY = 'WPjWg4OQHmPRWczygahhKfvadeD4mzaa'

graph = Graph()
graph.parse(GRAPH_PATH)

types, resource_types = find_types(graph)
resources = find_resources(graph, types)
reversed_types = reverse_types(types)
label_properties = LABEL_PROPERTIES
reversed_resources = reverse_resources(resources)

app.url_map.converters['rdf'] = RDFUrlConverter
app.config["labels"] = find_labels(graph, resources, LABEL_PROPERTIES)
app.secret_key = SECRET_KEY


@lfu_cache(200)
def app_resolve(r):
    return resolve(app, graph, types, resources, resource_types, r)


@app.route('/resource/<type_>/<rdf:label>')
@app.route('/resource/<rdf:label>')
def resource(label, type_=None):
    mime_type = best_match([RDFXML_MIME, N3_MIME, NTRIPLES_MIME, HTML_MIME], request.headers.get('accept'))
    if mime_type and mime_type != HTML_MIME:
        path = 'data'
        ext = '.' + mime_to_format(mime_type)
    else:
        path = 'page'
        ext = ''
    if type_:
        if ext != '':
            url = url_for(path, type_=type_, label=label, format_=ext)
        else:
            url = url_for(path, type_=type_, label=label)
    else:
        if ext != '':
            url = url_for(path, label=label, format_=ext)
        else:
            url = url_for(path, label=label)
    return redirect(url, 303)


@app.route('/data/<type_>/<rdf:label>.<format_>')
@app.route('/data/<rdf:label>.<format_>')
def data(label, format_, type_=None):
    r = get_resource(label, type_)
    if isinstance(r, tuple):  # 404
        return render_template('not_found.html', message=r[0])
    graph_ = get_resource_graph(graph, r, label_properties)
    return serialize(graph_, format_)


def get_resource(label, type_):
    if type_ and type_ not in reversed_types:
        return "No such type_ %s" % type_, 404
    try:
        t = reversed_types[type_]
        return reversed_resources[t][label]
    except Exception as e:
        print(e)
    return "No such resource %s" % label, 404


@app.route('/page/<type_>/<rdf:label>')
@app.route('/page/<rdf:label>')
def page(label, type_=None):
    r = get_resource(label, type_)
    if isinstance(r, tuple):  # 404
        return render_template('not_found.html', message=r[0])

    special_props = (RDF.type, RDFS.comment, RDFS.label, RDFS.domain, RDFS.range, RDFS.subClassOf, RDFS.subPropertyOf)

    out_props = [(app_resolve(y[0]), app_resolve(y[1])) for y in
                 sorted([x for x in graph.predicate_objects(r) if x[0] not in special_props])]

    types_ = sorted([app_resolve(x) for x in resource_types[r]], key=lambda x: x['label'].lower())
    comments = list(graph.objects(r, RDFS.comment))

    in_props = [(app_resolve(y[0]), app_resolve(y[1])) for y in sorted([x for x in graph.subject_predicates(r)])]

    params = {"outprops": out_props,
              "inprops": in_props,
              "label": get_label(app, r),
              "urilabel": label,
              "comments": comments,
              "graph": graph,
              "type_": type_,
              "types": types_,
              "resource": r}
    viewer = "page.html"

    if r == RDF.Property:
        # page for all properties
        roots = util.find_roots(graph, RDFS.subPropertyOf, set(resources[r]))
        roots = sorted(roots, key=lambda x: get_label(app, x).lower())
        params["properties"] = [
            util.get_tree(graph, root, RDFS.subPropertyOf, app_resolve, lambda x: x[0]['label'].lower())
            for root in roots]

        for x in in_props[:]:
            if x[1]["url"] == RDF.type:
                in_props.remove(x)
        viewer = "properties.html"
    elif RDF.Property in resource_types[r]:
        # a single property
        params["properties"] = [util.get_tree(graph, r, RDFS.subPropertyOf, app_resolve)]

        super_prop = [app_resolve(x) for x in
                      graph.objects(r, RDFS.subPropertyOf)]
        if super_prop:
            params["properties"] = [(super_prop, params["properties"])]

        params["domain"] = [app_resolve(do) for do in
                            graph.objects(r, RDFS.domain)]
        params["range"] = [app_resolve(ra) for ra in
                           graph.objects(r, RDFS.range)]

        # show subclasses/instances only once
        for x in in_props[:]:
            if x[1]["url"] in (RDFS.subPropertyOf,):
                in_props.remove(x)

        viewer = "property.html"
    elif r == RDFS.Class or r == OWL.Class:
        # page for all classes
        roots = util.find_roots(graph, RDFS.subClassOf, set(types))
        roots = sorted(roots, key=lambda x: get_label(app, x).lower())
        params["classes"] = [
            util.get_tree(graph, root, RDFS.subClassOf, app_resolve, sortkey=lambda x: x[0]['label'].lower()) for root
            in
            roots]

        viewer = "classes.html"
        # show classes only once
        for x in in_props[:]:
            if x[1]["url"] == RDF.type:
                in_props.remove(x)

    elif RDFS.Class in resource_types[r] or OWL.Class in resource_types[r]:
        # page for a single class
        params['classes'] = [util.get_tree(graph, r, RDFS.subClassOf, app_resolve)]
        super_class = [app_resolve(x) for x in
                       graph.objects(r, RDFS.subClassOf)]
        if super_class:
            params["classes"] = [(super_class, params["classes"])]

        params["classoutprops"] = [(app_resolve(p),
                                    [resolve(pr) for pr in graph.objects(viewer, RDFS.range)]) for p in
                                   graph.subjects(RDFS.domain, r)]
        params["classinprops"] = [([app_resolve(pr) for pr in
                                    graph.objects(viewer, RDFS.domain)], app_resolve(p)) for p in
                                  graph.subjects(RDFS.range, r)]
        params["instances"] = []
        # show subclasses/instances only once
        for x in in_props[:]:
            if x[1]["url"] == RDF.type:
                in_props.remove(x)
                params["instances"].append(x[0])
            elif x[1]["url"] in (RDFS.subClassOf,
                                 RDFS.domain,
                                 RDFS.range):
                in_props.remove(x)
        viewer = "class.html"
    return render_template(viewer, **params)


@app.route("/rdfgraph/<type_>/<rdf:label>.<format_>")
@app.route("/rdfgraph/<rdf:label>.<format_>")
def rdfgraph(label, format_, type_=None):
    r = get_resource(label, type_)
    if isinstance(r, tuple):  # 404
        return r
    graph_ = get_resource_graph(graph, r, label_properties)
    return get_rdf_graph(graph_, format_)


def get_rdf_graph(graph, format_):
    return dot(lambda uw: rdf2dot.rdf2dot(graph, stream=uw), format_)


@app.route('/')
def index():
    types_ = sorted([app_resolve(x) for x in types], key=lambda x: x['label'].lower())
    resources_ = {}
    for t in types_:
        type_url = t['realurl']
        resources_[type_url] = sorted([app_resolve(x) for x in resources[type_url]][:10],
                                      key=lambda x: x.get('label').lower())
        if len(resources[type_url]) > 10:
            resources_[type_url].append({'url': t['url'], 'external': False, 'label': '...'})
        t['count'] = len(resources[type_url])
    return render_template('index.html', types=types_, resources=resources_)


@app.route('/query')
def query():
    return render_template('query.html')


@app.route('/query-sparql', methods=['POST'])
def query_sparql():
    results = None
    try:
        q = request.form['query']
        results = graph.query(q).serialize(format='json')
    except Exception as e:
        print(e)
    mime_type = resultformat_to_mime('json')
    response = make_response(results)
    response.headers['Content-Type'] = mime_type
    return response


if __name__ == '__main__':
    app.run('0.0.0.0', debug=True)
