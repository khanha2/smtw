from werkzeug.routing import BaseConverter
from werkzeug.urls import url_quote


class RDFUrlConverter(BaseConverter):
    def __init__(self, url_map):
        BaseConverter.__init__(self, url_map)
        self.regex = "[^/].*?"

    def to_url(self, value):
        return url_quote(value, self.map.charset, safe=":")
