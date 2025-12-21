import cherrypy
import json

class CatalogService:
    exposed = True

    def __init__(self, file_path):
        self.file_path = file_path

    def GET(self, *uri, **params):
        if len(uri) > 0 and uri[0] == "catalog":
            with open(self.file_path, 'r') as f:
                data = json.load(f)
            return json.dumps(data)
        return "Invalid URI"

if __name__ == '__main__':
    config = {
        "/": {
            "request.dispatch": cherrypy.dispatch.MethodDispatcher(),
            "tools.response_headers.on": True,
        }
    }

    cherrypy.config.update({'server.socket_port': 8080})
    cherrypy.tree.mount(CatalogService('catalog.json'), '/', config)
    cherrypy.engine.start()
    cherrypy.engine.block()
