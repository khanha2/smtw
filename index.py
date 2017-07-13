import os

from rdflib import Graph, RDFS, URIRef, Literal, util, RDF

from flask import Flask, make_response, render_template, url_for, redirect, request

from service import find_labels, find_resources, find_types, get_label
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

app.config['graph'] = graph
types, resource_types = find_types(graph)
app.config['types'] = types
app.config['resource_types'] = resource_types
app.config["resources"] = find_resources(graph, app.config['types'])
app.config["label_properties"] = LABEL_PROPERTIES
app.config["labels"] = find_labels(graph, app.config["resources"], LABEL_PROPERTIES)
app.secret_key = SECRET_KEY


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/instance/<label>/<instance_type>')
def resource(label, instance_type=None):
    mime_type = best_match([RDFXML_MIME, N3_MIME, NTRIPLES_MIME, HTML_MIME], request.headers.get("Accept"))
    if mime_type and mime_type != HTML_MIME:
        path = "lod.data"
        ext = "." + mime_to_format(mime_type)
    else:
        path = "lod.page"
        ext = ""
    if instance_type is not None:
        if ext != '':
            url = url_for(path, type_=instance_type, label=label, format_=ext)
        else:
            url = url_for(path, type_=instance_type, label=label)
    else:
        if ext != '':
            url = url_for(path, label=label, format_=ext)
        else:
            url = url_for(path, label=label)
    return redirect(url, 303)


def resolve(r):
    if r is None:
        return {'url': None, 'realurl': None, 'label': None}
    if isinstance(r, Literal):
        return {'url': None, 'realurl': None, 'label': str(r), 'lang': r.language}
    local_url = None
    if app.config['types'] == {None: None}:
        graph = app.config['graph']
        if app.config['resource_types'][r] in graph:
            local_url = url_for('resource', label=app.config['resources'][None][r])
    else:
        for t in app.config['resource_types'][r]:
            if t in app.config['types']:
                try:
                    l = str(app.config['resources'][t][r])
                    local_url = url_for('resource', instance_type=app.config['types'][t], label=l)
                    break
                except KeyError:
                    pass
    types = [resolve(t) for t in app.config['resource_types'][r] if t != r]
    return {'external': not local_url,
            'url': local_url or r,
            'realurl': r,
            'label': get_label(app, r),
            'type': types}


@app.route('/instances')
def instances():
    types = sorted([resolve(x) for x in app.config["types"]], key=lambda x: x['label'].lower())
    resources = {}
    for t in types:
        turl = t["realurl"]
        resources[turl] = sorted([resolve(x) for x in app.config["resources"][turl]][:10],
                                 key=lambda x: x.get('label').lower())
        if len(app.config["resources"][turl]) > 10:
            resources[turl].append({'url': t["url"], 'external': False, 'label': "..."})
        t["count"] = len(app.config["resources"][turl])
    return render_template('instances.html', types=types, resources=resources)


@app.route('/query')
def query():
    return render_template('query.html')


@app.route('/query-sparql', methods=['POST'])
def query_sparql():
    results = None
    try:
        q = request.form['query']
        graph = app.config['graph']
        results = graph.query(q).serialize(format='json')
    except Exception as e:
        print(e)
    mime_type = resultformat_to_mime('json')
    response = make_response(results)
    response.headers["Content-Type"] = mime_type
    return response


@app.route('/classes')
def classes():
    graph = app.config['graph']
    # page for all classes
    roots = util.find_roots(graph, RDFS.subClassOf, set(app.config["types"]))
    roots = sorted(roots, key=lambda x: get_label(app, RDFS.Class).lower())
    _classes = [util.get_tree(graph, root, RDFS.subClassOf, resolve, sortkey=lambda x: x[0]['label'].lower())
                for root in roots]
    return render_template('classes.html', classes=_classes)


if __name__ == '__main__':
    app.run('0.0.0.0', debug=True)
