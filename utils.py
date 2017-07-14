from flask import make_response

JSON_MIME = "application/sparql-results+json"
XML_MIME = "application/sparql-results+xml"

HTML_MIME = "text/html"
N3_MIME = "text/n3"
TURTLE_MIME = "text/turtle"

RDFXML_MIME = "application/rdf+xml"
NTRIPLES_MIME = "text/plain"
JSONLD_MIME = "application/json"

FORMAT_MIMETYPE = {"rdf": RDFXML_MIME, "n3": N3_MIME, "nt": NTRIPLES_MIME, "turtle": TURTLE_MIME,
                   "json-ld": JSONLD_MIME}
MIMETYPE_FORMAT = dict(map(reversed, FORMAT_MIMETYPE.items()))


def mime_to_format(mimetype):
    if mimetype in MIMETYPE_FORMAT:
        return MIMETYPE_FORMAT[mimetype]
    return "rdf"


def format_to_mime(format_):
    if format_ == 'ttl':
        format_ = 'turtle'
    elif format_ == 'json':
        format_ = 'json-ld'
    if format_ in FORMAT_MIMETYPE:
        return format_, FORMAT_MIMETYPE[format_]
    return "xml", RDFXML_MIME


def resultformat_to_mime(format):
    if format == 'xml':
        return XML_MIME
    elif format == 'json':
        return JSON_MIME
    elif format == 'html':
        return HTML_MIME
    return "text/plain"


def best_match(mines, header):
    data = [x.lower() for x in header.split(',')]
    lowered_mines = [x.lower() for x in mines]
    for mine in lowered_mines:
        for item in data:
            if mine == item:
                return mine
    return None


def serialize(graph, format_):
    format_, mime_type = format_to_mime(format_)
    response = make_response(graph.serialize(format=format_))
    response.headers["Content-Type"] = mime_type
    return response
